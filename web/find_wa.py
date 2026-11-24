"""Find WhatsApp numbers a business publishes on its own website (real browser via crawl4ai).
Usage: python find_wa.py IN.csv OUT.csv [--region GB]
Pages are rendered a few at a time (WAT_WEB_CONCURRENCY, default 5) so one slow site cannot hold the rest.
Resume-safe: rows already in OUT.csv are skipped."""
import asyncio, csv, os, re, sys, time, html as htmlmod
from urllib.parse import urlparse, urljoin, unquote
import phonenumbers
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

SKIP_PLATFORMS = ("ubereats.", "deliveroo.", "just-eat.", "justeat.", "doordash.", "grubhub.",
                  "google.", "goo.gl", "facebook.com", "fb.com", "instagram.com")
PAGE_TIMEOUT_MS = 30000
CONTACT_RE = re.compile(r"contact|about|联系|聯絡", re.I)
LINK_PATTERNS = [
    re.compile(r"wa\.me/(?:message/)?\+?(\d{6,15})", re.I),
    re.compile(r"api\.whatsapp\.com/send/?\?[^\"'\s<>]*?phone=(?:%2B|\+)?(\d{6,15})", re.I),
    re.compile(r"web\.whatsapp\.com/send/?\?[^\"'\s<>]*?phone=(?:%2B|\+)?(\d{6,15})", re.I),
    re.compile(r"whatsapp://send/?\?[^\"'\s<>]*?phone=(?:%2B|\+)?(\d{6,15})", re.I),
]
NEW_COLS = ["wa_number_e164", "wa_source_url", "wa_evidence", "site_status"]

def is_platform(url):
    host = urlparse(url).netloc.lower()
    return any(p in host for p in SKIP_PLATFORMS)

def norm_digits(d, region):
    try:
        n = phonenumbers.parse("+" + d, None)
        if phonenumbers.is_valid_number(n):
            return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    try:  # national format like 07700900123
        n = phonenumbers.parse(d, region)
        if phonenumbers.is_valid_number(n):
            return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    return None

def extract(raw_html, text, region="GB"):
    """returns list of (e164, evidence)"""
    found, seen = [], set()
    blob = unquote(htmlmod.unescape(raw_html or ""))
    for pat in LINK_PATTERNS:
        for m in pat.finditer(blob):
            e = norm_digits(m.group(1), region)
            if e and e not in seen:
                seen.add(e); found.append((e, blob[max(0, m.start()-10):m.end()][:120]))
    text = text or ""
    for m in re.finditer(r"whats\s?app", text, re.I):
        after = text[m.end():m.end()+40]
        before = text[max(0, m.start()-40):m.start()]
        for win in (after, before):  # prefer the number written right after the word
            pms = [p for p in phonenumbers.PhoneNumberMatcher(win, region) if phonenumbers.is_valid_number(p.number)]
            if win is before and pms: pms = pms[-1:]
            if win is after and pms: pms = pms[:1]
            for pm in pms:
                e = phonenumbers.format_number(pm.number, phonenumbers.PhoneNumberFormat.E164)
                if e not in seen:
                    seen.add(e); found.append((e, " ".join(text[max(0, m.start()-40):m.end()+40].split())[:120]))
            if pms: break
    return found

async def render(crawler, url):
    cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=PAGE_TIMEOUT_MS,
                           delay_before_return_html=2.5, wait_until="domcontentloaded",
                           verbose=False)
    r = await crawler.arun(url=url, config=cfg)
    if not r.success:
        raise RuntimeError(r.error_message or "crawl failed")
    md = r.markdown
    text = getattr(md, "raw_markdown", None) or str(md or "")
    return r, r.html or "", text

def contact_link(result, base):
    host = urlparse(base).netloc.replace("www.", "")
    links = (result.links or {}).get("internal", [])
    for l in links:
        href = l.get("href", "")
        if urlparse(href).netloc.replace("www.", "") == host and href.rstrip("/") != base.rstrip("/") \
           and CONTACT_RE.search(urlparse(href).path + " " + (l.get("text") or "")):
            return href
    return None

async def process(crawler, url, region):
    res = {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "ok"}
    nums = {}
    try:
        r, h, t = await render(crawler, url)
        for e, ev in extract(h, t, region):
            nums.setdefault(e, (url, ev))
        c = contact_link(r, r.url or url)
        if c:
            try:
                r2, h2, t2 = await render(crawler, c)
                for e, ev in extract(h2, t2, region):
                    nums.setdefault(e, (c, ev))
            except Exception:
                pass
    except Exception as ex:
        res["site_status"] = "error: " + str(ex)[:80].replace("\n", " ")
        return res
    if nums:
        res["wa_number_e164"] = ";".join(nums)
        res["wa_source_url"] = ";".join(v[0] for v in nums.values())
        res["wa_evidence"] = " | ".join(v[1] for v in nums.values())[:120]
    return res

def _fallback_exe():
    """A Chromium that is really on disk: headless shell first, then full Chromium, newest build first."""
    import glob
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright") if os.name == "nt"
        else os.path.expanduser("~/Library/Caches/ms-playwright") if sys.platform == "darwin" else os.path.expanduser("~/.cache/ms-playwright"))
    pats = ["chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell.exe", "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
            "chromium-*/chrome-win64/chrome.exe", "chromium-*/chrome-mac*/*.app/Contents/MacOS/*", "chromium-*/chrome-linux*/chrome"]
    for pat in pats:
        hits = sorted(glob.glob(os.path.join(root, pat)), reverse=True)
        if hits: return hits[0]
    return ""


def _use_installed_browser(exe_given=""):
    """11-14 client: the installer ships chromium(_headless_shell)-1228 but Playwright 1.63 looks for headless_shell-1243,
    so the website step crashed with "Executable doesn't exist". When the expected browser is missing, launch the one we have.
    exe_given (WAT_BROWSER_EXE, app/browser.py): always launch that one."""
    from playwright.async_api._generated import BrowserType
    orig = BrowserType.launch
    async def launch(self, *a, **k):
        if not k.get("executable_path") and self.name == "chromium" and (exe_given or not os.path.exists(self.executable_path)):
            exe = exe_given or _fallback_exe()
            if exe:
                k["executable_path"] = exe
                print(f"[website] browser {os.path.basename(os.path.dirname(os.path.dirname(exe)))} (expected one missing)", flush=True)
        return await orig(self, *a, **k)
    BrowserType.launch = launch


async def main(inp, out, region="GB"):
    rows = list(csv.DictReader(open(inp, encoding="utf-8")))
    done = {}
    if os.path.exists(out):
        for r in csv.DictReader(open(out, encoding="utf-8")):
            done[r["place_id"]] = r
    fields = list(rows[0].keys()) + NEW_COLS
    t0 = time.time(); timings = []
    channel, exe = os.environ.get("WAT_BROWSER_CHANNEL", ""), os.environ.get("WAT_BROWSER_EXE", "")
    if channel and not exe:   # app/browser.py picked Edge / Chrome (11-17 client: Edge found 11 WhatsApp vs 4)
        bc = BrowserConfig(headless=True, verbose=False, chrome_channel=channel)
        print(f"[website] browser {channel}", flush=True)
    else:
        _use_installed_browser(exe)
        bc = BrowserConfig(headless=True, verbose=False)
    # 11-24 客户：165 个网站 1 小时（68 个死在 30 秒超时上）。几个网站同时开，一个卡住不拖住后面。
    conc = max(1, int(os.environ.get("WAT_WEB_CONCURRENCY", "5")))
    sem = asyncio.Semaphore(conc)
    todo = [r for r in rows if r["place_id"] not in done]
    print(f"[website] {len(todo)} sites, {conc} at a time", flush=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in rows:                                       # already-checked sites keep their place in the file
            if row["place_id"] in done:
                w.writerow({k: done[row["place_id"]].get(k, "") for k in fields})
        f.flush()
        async with AsyncWebCrawler(config=bc) as crawler:
            async def one(row):
                url = (row.get("website") or "").strip()
                try:
                    if not url:
                        res = {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "no_site"}
                    elif is_platform(url):
                        res = {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "skipped_platform"}
                    else:
                        async with sem:
                            s = time.time(); res = await process(crawler, url, region); timings.append(time.time()-s)
                        print(f"{time.time()-s:5.1f}s {url[:50]} -> {res['site_status'][:30]} {res['wa_number_e164']}", flush=True)
                except Exception as ex:                        # one bad site must not kill the other four
                    res = {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "error: " + str(ex)[:80].replace("\n", " ")}
                w.writerow({**row, **res}); f.flush()          # 每查完一个就写盘：中途停了不白查
            await asyncio.gather(*(one(r) for r in todo))
    print(f"own-site crawled: {len(timings)}, total {time.time()-t0:.0f}s, avg {sum(timings)/max(1,len(timings)):.1f}s/site")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], "GB"))
