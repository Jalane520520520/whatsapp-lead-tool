// WhatsApp number checker (read-only: uses onWhatsApp lookup only; NEVER sends messages).
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import http from 'node:http'
import https from 'node:https'
import tls from 'node:tls'

const HERE = path.dirname(fileURLToPath(import.meta.url))
// Libraries load by absolute path: after a hot update this file sits in %LOCALAPPDATA%\...\app\<ver>\ while node_modules
// stays in the install folder, and ES-module imports ignore NODE_PATH.
const NM = process.env.WAT_NODE_MODULES || path.join(HERE, 'node_modules')
const req = createRequire(path.join(NM, '_.js'))
const mod = async name => import(pathToFileURL(req.resolve(name)).href)

// WhatsApp is blocked in mainland China. Clients' VPNs usually only set the Windows *system proxy*, which
// browsers follow but Node does not. WAT_PROXY (read from the system proxy by the Python side) routes both
// WhatsApp connections through it: an HTTP CONNECT tunnel, Node built-ins only (no new library).
const PROXY = (() => {
  const raw = process.env.WAT_PROXY || ''
  const m = raw.match(/^(?:https?:\/\/)?([^/:]+):(\d+)/)
  return m ? { host: m[1], port: Number(m[2]) } : null
})()
class TunnelAgent extends https.Agent {
  createConnection(opts, cb) {
    const host = opts.host || opts.hostname, port = opts.port || 443
    const r = http.request({ host: PROXY.host, port: PROXY.port, method: 'CONNECT', path: `${host}:${port}`, headers: { Host: `${host}:${port}` } })
    r.once('connect', (res, socket) => {
      if (res.statusCode !== 200) { socket.destroy(); return cb(new Error(`proxy CONNECT ${res.statusCode}`)) }
      cb(null, tls.connect({ socket, servername: opts.servername || host, ALPNProtocols: opts.ALPNProtocols }))
    })
    r.once('error', cb)
    r.end()
  }
}
const AGENT = PROXY ? new TunnelAgent({ keepAlive: false }) : undefined

// Same request Baileys makes (web.whatsapp.com/sw.js -> client_revision), but through the proxy.
// Baileys' own fetch ignores proxies and silently falls back to an old version, which WhatsApp refuses to link.
function webVersion() {
  return new Promise(resolve => {
    const r = https.get('https://web.whatsapp.com/sw.js', { agent: AGENT, timeout: 15000,
      headers: { 'sec-fetch-site': 'none', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' } }, res => {
      let d = ''; res.on('data', c => { d += c }); res.on('end', () => {
        const m = d.match(/\\?"client_revision\\?":\s*(\d+)/); resolve(m ? [2, 3000, Number(m[1])] : null) })
    })
    r.on('timeout', () => r.destroy()); r.on('error', () => resolve(null))
  })
}
const STATE = process.env.WA_STATE || HERE  // installed: %LOCALAPPDATA%\\WhatsApp客户提取\\wa_auth
fs.mkdirSync(STATE, { recursive: true })
const AUTH_DIR = path.join(STATE, 'auth')
const CACHE_FILE = path.join(STATE, 'cache.jsonl')
const QR_PNG = path.join(STATE, 'qr.png')
const PAIR_TXT = path.join(STATE, 'pair_code.txt')
const LOGIN_LOG = path.join(STATE, 'login.log')
const llog = m => { try { fs.appendFileSync(LOGIN_LOG, `${new Date().toISOString()} ${m}\n`) } catch {} }

// ---- limits (Evolution API defaults, PR #2581) ----
const PER_CALL = 10          // max numbers per onWhatsApp call
const MIN_CALL_GAP_MS = 1000 // min gap between calls
const PER_BATCH = 50         // numbers per batch
const STOP_CODES = new Set([401, 402, 403, 440]) // loggedOut, payment/ban-like, forbidden, connectionReplaced

function parseArgs(argv) {
  const a = { batchPause: 30, dryRun: false }
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i]
    if (k === '--in') a.in = argv[++i]
    else if (k === '--out') a.out = argv[++i]
    else if (k === '--dry-run') a.dryRun = true
    else if (k === '--batch-pause') a.batchPause = Number(argv[++i])
    else if (k === '--login-only') a.loginOnly = true
    else if (k === '--require-login') a.requireLogin = true
    else if (k === '--pair') a.pair = String(argv[++i] || '').replace(/\D/g, '') // link by 8-char code instead of QR
    else { console.error(`Unknown argument ${k}`); process.exit(2) }
  }
  if (!a.loginOnly && (!a.in || !a.out || !(a.batchPause >= 0))) {
    console.error('Usage: node check.js --in numbers.csv --out results.csv [--batch-pause 30] [--dry-run]')
    process.exit(2)
  }
  return a
}

function splitCsvLine(l) {
  const out = []; let cur = '', q = false
  for (const ch of l) {
    if (ch === '"') q = !q
    else if (ch === ',' && !q) { out.push(cur); cur = '' }
    else cur += ch
  }
  out.push(cur); return out.map(s => s.trim())
}

function readNumbers(file) {
  const lines = fs.readFileSync(file, 'utf8').replace(/^﻿/, '').split(/\r?\n/).filter(l => l.trim())
  const head = splitCsvLine(lines[0]).map(s => s.toLowerCase())
  const col = head.indexOf('phone_e164')
  if (col < 0) throw new Error('Input CSV needs a phone_e164 column')
  const seen = new Set(), nums = [], bad = []
  for (const l of lines.slice(1)) {
    const v = (splitCsvLine(l)[col] || '').replace(/[\s\-()]/g, '')
    if (!/^\+[1-9]\d{6,14}$/.test(v)) { if (v) bad.push(v); continue }
    if (!seen.has(v)) { seen.add(v); nums.push(v) }
  }
  return { nums, bad }
}

function loadCache() {
  const m = new Map()
  if (!fs.existsSync(CACHE_FILE)) return m
  for (const l of fs.readFileSync(CACHE_FILE, 'utf8').split('\n')) {
    if (!l.trim()) continue
    try { const r = JSON.parse(l); m.set(r.number, r) } catch { /* torn last line after a crash: ignore */ }
  }
  return m
}
const cacheWrite = r => fs.appendFileSync(CACHE_FILE, JSON.stringify(r) + '\n')

function writeResults(file, nums, cache) {
  const rows = ['phone_e164,on_whatsapp,jid,checked_at']
  for (const n of nums) {
    const r = cache.get(n)
    if (r) rows.push([n, r.exists ? 'yes' : 'no', r.jid || '', r.checked_at].join(','))
  }
  fs.writeFileSync(file, rows.join('\n') + '\n')
}

const sleep = ms => new Promise(r => setTimeout(r, ms))
const chunk = (a, n) => { const o = []; for (let i = 0; i < a.length; i += n) o.push(a.slice(i, i + n)); return o }

function plan(todo, batchPauseS) {
  const batches = chunk(todo, PER_BATCH)
  let t = 0
  console.log(`Plan: ${todo.length} numbers -> ${batches.length} batch(es) of <= ${PER_BATCH}, calls of <= ${PER_CALL}, >= ${MIN_CALL_GAP_MS} ms between calls, ${batchPauseS} s between batches`)
  batches.forEach((b, i) => {
    const calls = chunk(b, PER_CALL)
    console.log(`  batch ${i + 1}: ${b.length} numbers, ${calls.length} calls [${calls.map(c => c.length).join(',')}], starts at ~t+${t.toFixed(0)} s`)
    t += (calls.length - 1) * MIN_CALL_GAP_MS / 1000
    if (i < batches.length - 1) t += batchPauseS
  })
  console.log(`Estimated minimum time (excluding network + jitter): ~${t.toFixed(0)} s`)
}

async function main() {
  const args = parseArgs(process.argv)
  if (args.loginOnly) { args.in = null; args.out = null }
  const { nums, bad } = args.loginOnly ? { nums: [], bad: [] } : readNumbers(args.in)
  if (bad.length) console.warn(`Skipping ${bad.length} invalid number(s): ${bad.slice(0, 5).join(', ')}${bad.length > 5 ? ' ...' : ''}`)
  const cache = loadCache()
  const todo = nums.filter(n => !cache.has(n))
  console.log(`${nums.length} unique valid numbers, ${nums.length - todo.length} already in cache, ${todo.length} to check`)

  if (args.dryRun) {
    plan(todo, args.batchPause)
    writeResults(args.out, nums, cache)
    console.log(`DRY RUN: no connection made. Wrote ${args.out} with cached rows only.`)
    return
  }

  // Heavy imports only when really connecting
  const baileys = await mod('baileys')
  const makeWASocket = baileys.default?.default ?? baileys.default ?? baileys.makeWASocket
  const { useMultiFileAuthState, fetchLatestBaileysVersion, DisconnectReason } = baileys
  const QRT = (await mod('qrcode-terminal')).default
  const QRCode = (await mod('qrcode')).default

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const pino = (await mod('pino')).default
  const logger = pino({ level: 'silent' })
  let sock = null, open = false, fatal = null, attempt = 0
  let waiters = []

  const stop = msg => { fatal = msg; waiters.forEach(w => w()); waiters = [] }

  async function connect() {
    // WhatsApp rejects links from an old web version ("check your connection"); ask web.whatsapp.com first
    let version = await webVersion(), source = 'live'
    if (!version) { source = 'fallback'; ({ version } = await fetchLatestBaileysVersion().catch(() => ({}))) }
    if (!version) source = 'default'
    // source= is read by server.py /status: anything but live means the phone may refuse the scan
    llog(`connect, proxy ${PROXY ? PROXY.host + ':' + PROXY.port : 'none'}, wa version ${version ? version.join('.') : 'default'} source=${source}`)
    sock = makeWASocket({ version, auth: state, logger, agent: AGENT, printQRInTerminal: false, markOnlineOnConnect: false, syncFullHistory: false })
    sock.ev.on('creds.update', saveCreds)
    sock.ev.on('connection.update', async u => {
      llog(`update connection=${u.connection ?? '-'} qr=${u.qr ? 'yes' : '-'} isNewLogin=${u.isNewLogin ?? '-'} status=${u.lastDisconnect?.error?.output?.statusCode ?? '-'} ${u.lastDisconnect?.error?.message ?? ''}`)
      if (u.qr) {
        // --require-login: never wait for a scan; the run goes on without the check (exit 3)
        if (args.requireLogin) { console.log('NOT_LOGGED_IN: WhatsApp not logged in, check skipped'); try { writeResults(args.out, nums, cache) } catch {} process.exit(3) }
        if (args.pair) {
          // one code per connection; a reconnect after timeout gets a fresh code
          if (sock.__paired) return
          sock.__paired = true
          try {
            const code = await sock.requestPairingCode(args.pair)
            fs.writeFileSync(PAIR_TXT, code + '\n')
            console.log(`PAIRING_CODE ${code.slice(0, 4)}-${code.slice(4)}  (WhatsApp > Linked devices > Link a device > Link with phone number instead)`)
          } catch (e) { console.error('pairing code error', e.message) }
          return
        }
        console.log('Scan the QR on the page (WhatsApp > Linked devices), saved as qr.png')
        QRCode.toFile(QR_PNG, u.qr, { width: 400 }).catch(() => {})
      }
      if (u.connection === 'open') { open = true; attempt = 0; try { fs.rmSync(QR_PNG, { force: true }); fs.rmSync(PAIR_TXT, { force: true }) } catch {} console.log('Connected.'); waiters.forEach(w => w()); waiters = [] }
      if (u.connection === 'close') {
        open = false
        const code = u.lastDisconnect?.error?.output?.statusCode
        if (code === DisconnectReason.loggedOut || STOP_CODES.has(code) ) return stop(`STOPPED: account restricted or logged out (status ${code})`)
        const delay = Math.min(60000, 2000 * 2 ** attempt++)
        console.log(`Disconnected (status ${code}). Reconnecting in ${delay / 1000} s...`)
        await sleep(delay)
        if (!fatal) connect().catch(e => console.error('reconnect error', e.message))
      }
    })
  }
  const ready = () => new Promise(res => { if (open || fatal) return res(); waiters.push(res) })

  const finish = (code) => { writeResults(args.out, nums, cache); if (fatal) console.error(fatal); process.exit(code) }
  if (args.loginOnly) setTimeout(() => {   // network blocked: stop retrying and say why instead of spinning forever
    if (!open && !fs.existsSync(QR_PNG) && !fs.existsSync(PAIR_TXT)) {
      llog(`连不上 WhatsApp：90 秒没拿到二维码（代理 ${PROXY ? PROXY.host + ':' + PROXY.port : '无'}）`); process.exit(4) }
  }, 90000).unref()
  await connect()
  await ready()
  if (fatal) return args.loginOnly ? (console.error(fatal), process.exit(1)) : finish(1)
  if (args.loginOnly) { console.log('LOGGED_IN'); await sleep(3000); try { sock.end(undefined) } catch {} process.exit(0) }

  const batches = chunk(todo, PER_BATCH)
  for (let bi = 0; bi < batches.length; bi++) {
    for (const group of chunk(batches[bi], PER_CALL)) {
      let done = false
      while (!done) {
        await ready()
        if (fatal) return finish(1)
        try {
          const res = await sock.onWhatsApp(...group.map(n => n.replace('+', '')))
          const byNum = new Map((res || []).map(r => [r.jid.split('@')[0].split(':')[0], r]))
          const now = new Date().toISOString()
          for (const n of group) {
            const hit = byNum.get(n.replace('+', ''))
            const rec = { number: n, exists: !!(hit && hit.exists), jid: hit && hit.exists ? hit.jid : '', checked_at: now }
            cache.set(n, rec); cacheWrite(rec)
          }
          console.log(`Checked ${group.length} (${cache.size} cached total)`)
          done = true
        } catch (e) {
          if (fatal) return finish(1)
          console.error(`Query failed (${e.message}); waiting 15 s and retrying (not cached)`)
          await sleep(15000)
        }
      }
      await sleep(MIN_CALL_GAP_MS + Math.floor(Math.random() * 500))
    }
    if (bi < batches.length - 1) { console.log(`Batch ${bi + 1} done, pausing ${args.batchPause} s`); await sleep(args.batchPause * 1000) }
  }
  console.log('All done.')
  try { sock.end(undefined) } catch {}
  finish(0)
}

main().catch(e => { console.error(e); process.exit(1) })
