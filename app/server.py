#!/usr/bin/env python3
"""The tool's window (final.html design, 10-21): search box + chips, WhatsApp login card, 4-step progress,
WhatsApp result list, search history (one table per keyword+country, opened in place)."""
import json, os, re, shutil, subprocess, sys, threading, time
from flask import Flask, jsonify, request, send_file, abort, Response

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cells as C
import pipeline as P
import paths
WA = os.path.join(TOOL, "wa_check")
QR, PAIR, CREDS = os.path.join(paths.WA_STATE, "qr.png"), os.path.join(paths.WA_STATE, "pair_code.txt"), os.path.join(paths.WA_STATE, "auth", "creds.json")
HIDDEN = os.path.join(C.DATA, "_hidden.json")
CN = C.CN
COUNTRIES = json.load(open(os.path.join(TOOL, "maps", "countries.json"), encoding="utf-8"))
app = Flask(__name__)
S = {"state": "idle", "proc": None, "log": [], "kws": None, "cc": None, "excel": None}
L = {"proc": None}
lock = threading.Lock()


def kw_list(s):
    return [k.strip() for k in re.split(r"[;；\n]", s or "") if k.strip()]


def me():
    """Logged-in number like +8613800000000, or ''."""
    try:
        c = json.load(open(CREDS, encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    m = (c.get("me") or {}).get("id", "")
    return "+" + m.split(":")[0].split("@")[0] if m and c.get("account") else ""  # "account" only after a finished link


def stage_info(lines):
    """Read the pipeline log into the 4 steps the window shows."""
    st = {"step": 0, "maps_i": 0, "maps_n": 0, "new": 0, "web_i": 0, "web_n": 0, "web_secs": [], "wa_i": 0, "wa_n": 0,
          "wa_note": "", "locked": ""}
    for l in lines:
        if m := re.search(r"this run: (\d+) cells", l): st["maps_n"] = int(m[1]); st["step"] = 1
        elif m := re.search(r"\[maps (\d+)/(\d+)\]", l): st["maps_i"] = int(m[1]) - 1; st["step"] = 1
        elif m := re.search(r"-> \w+: \d+ places, (\d+) new", l): st["new"] += int(m[1]); st["maps_i"] += 1
        elif m := re.search(r"\[website\] (\d+) new businesses", l): st["web_n"] = int(m[1]); st["step"] = 2
        elif "[website] nothing new" in l: st["step"] = 2
        elif m := re.match(r"\s*([\d.]+)s https?://", l): st["web_i"] += 1; st["web_secs"].append(float(m[1]))
        elif m := re.search(r"\[whatsapp\] checking (\d+)", l): st["wa_n"] = int(m[1]); st["step"] = 3
        elif "[whatsapp]" in l: st["step"] = 3; st["wa_note"] = "未登录，跳过" if "未登录" in l else "没有新号码"
        elif m := re.match(r"Checked (\d+)", l): st["wa_i"] += int(m[1])
        elif "EXCEL_LOCKED" in l: st["locked"] = l.split("另存为", 1)[-1].strip()
        elif re.search(r"\bDONE\b", l): st["step"] = 4
    secs = st.pop("web_secs")
    st["web_left"] = round(sum(secs) / len(secs) * max(0, st["web_n"] - st["web_i"])) if secs else None
    return st


def table_summary(cc, kws):
    d = C.data_dir(cc, kws)
    rows = P.table_rows(d) if os.path.exists(os.path.join(d, "master.csv")) else []
    sm = C.summary(C.load_progress(cc, kws)) if os.path.exists(os.path.join(d, "progress.json")) else None
    return d, rows, sm


def open_path(p):
    if sys.platform.startswith("win"): os.startfile(p)  # noqa
    else: subprocess.Popen(["open", p])


def PAGE():
    return open(os.path.join(HERE, "window.html"), encoding="utf-8").read()


@app.get("/")
def index():
    opts = json.dumps([[c, CN.get(c, v["name"]), v["name"]] for c, v in COUNTRIES.items() if not c.startswith("_")], ensure_ascii=False)
    return Response(PAGE().replace("__OPTS__", opts), mimetype="text/html")


def watch(p, logf):
    for line in p.stdout:
        with lock:
            S["log"].append(line.rstrip()); S["log"] = S["log"][-600:]
            if line.startswith(tuple("0123456789")) and "EXCEL:" in line: S["excel"] = line.split("EXCEL:", 1)[1].strip()
        logf.write(line); logf.flush()
    rc = p.wait(); logf.close()
    with lock: S["state"] = "done" if rc in (0, 2) and S["excel"] else "error"


@app.post("/start")
def start():
    d = request.get_json(force=True)
    kws, cc = kw_list(d.get("keywords")), d.get("country", "")
    if not kws: return jsonify(ok=False, error="请填写产品关键词")
    if cc not in COUNTRIES: return jsonify(ok=False, error="国家无效")
    try: n = max(1, min(int(d.get("cells") or 3), 5000))
    except ValueError: return jsonify(ok=False, error="格数要填数字")
    city = (d.get("city") or "").strip()
    with lock:
        if S["state"] == "running": return jsonify(ok=False, error="已有任务在运行")
        run_dir = os.path.join(paths.RUNS, time.strftime("%Y%m%d_%H%M%S") + "_" + cc); os.makedirs(run_dir, exist_ok=True)
        cmd = [sys.executable, os.path.join(HERE, "pipeline.py"), "--keywords", ";".join(kws), "--country", cc,
               "--cells", str(n), "--run-dir", run_dir]           # Excel always goes to the one table of this keyword+country
        if city: cmd += ["--city", city]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding="utf-8")
        S.update(state="running", proc=p, log=[], kws=kws, cc=cc, excel=None)
        threading.Thread(target=watch, args=(p, open(os.path.join(run_dir, "log.txt"), "w", encoding="utf-8")), daemon=True).start()
    hid = _hidden(); key = C.slug_for(cc, kws)
    if key in hid: hid.remove(key); _save_hidden(hid)
    return jsonify(ok=True)


def wa_source():
    """'live' / 'fallback' / 'default' from the last connect line check.js wrote; '' before the first connect."""
    try: lines = open(os.path.join(paths.WA_STATE, "login.log"), encoding="utf-8").read().splitlines()
    except OSError: return ""
    for l in reversed(lines):
        m = re.search(r" connect, .* source=(\w+)", l)
        if m: return m.group(1)
    return ""


@app.get("/status")
def status():
    with lock:
        lr = L["proc"] is not None and L["proc"].poll() is None
        st = {"state": S["state"], "kws": S["kws"], "cc": S["cc"], "excel": S["excel"], **stage_info(S["log"])}
    pair = open(PAIR, encoding="utf-8").read().strip() if lr and os.path.exists(PAIR) else ""
    err = ""
    if L["proc"] is not None and not lr and not me():          # login ended without a link: show why on the page
        try: err = open(os.path.join(paths.WA_STATE, "login.log"), encoding="utf-8").read().strip().splitlines()[-1][25:200]
        except (OSError, IndexError): err = "登录程序没有启动"
    return jsonify(**st, login_error=err, wa_source=wa_source(), proxy=paths.system_proxy(), version=os.environ.get("WAT_VERSION") or open(os.path.join(TOOL, "VERSION"), encoding="utf-8").read().strip(), me=me(), login_running=lr, qr=lr and os.path.exists(QR) and not pair, pair=pair)


@app.get("/results")
def results():
    cc, kws = request.args.get("country", "").upper(), kw_list(request.args.get("keywords"))
    if cc not in COUNTRIES or not kws: return jsonify(total=0, wa=[], sm=None)
    _, rows, sm = table_summary(cc, kws)
    return jsonify(total=len(rows), sm=sm, wa=[{k: r[k] for k in ("name", "wa", "src", "city", "category")} for r in rows if r["wa"]])


def _hidden():
    try: return json.load(open(HIDDEN, encoding="utf-8"))
    except (OSError, ValueError): return []


def _save_hidden(h):
    os.makedirs(C.DATA, exist_ok=True); json.dump(h, open(HIDDEN, "w", encoding="utf-8"))


@app.get("/history")
def history():
    out, hid = [], _hidden()
    for name in os.listdir(C.DATA) if os.path.isdir(C.DATA) else []:
        pj = os.path.join(C.DATA, name, "progress.json")
        if name in hid or not os.path.exists(pj): continue
        prog = json.load(open(pj, encoding="utf-8"))
        rows = P.table_rows(os.path.join(C.DATA, name)); sm = C.summary(prog)
        out.append({"key": name, "keywords": "; ".join(prog["keywords"]), "cc": prog["country"],
                    "country": CN.get(prog["country"], prog["country"]), "wa": sum(1 for r in rows if r["wa"]), "total": len(rows),
                    "done": sm["done"], "cells": sm["total"], "mtime": os.path.getmtime(pj)})
    out.sort(key=lambda x: -x["mtime"])
    return jsonify(out)


@app.post("/hide")
def hide():
    k = request.get_json(force=True).get("key", "")
    h = _hidden()
    if k and k not in h: h.append(k); _save_hidden(h)
    return jsonify(ok=True)


@app.post("/open")
def open_():
    d = request.get_json(force=True)
    if d.get("what") == "folder":
        os.makedirs(C.TABLES, exist_ok=True); open_path(C.TABLES); return jsonify(ok=True)
    pj = os.path.join(C.DATA, os.path.basename(d.get("key", "")), "progress.json")
    if not os.path.exists(pj): return jsonify(ok=False, error="这张表还没有 Excel，先抓一次")
    prog = json.load(open(pj, encoding="utf-8")); x = C.excel_path(prog["country"], prog["keywords"])
    for f in (x[:-5] + " (新).xlsx", x) if d.get("newest") else (x,):
        if os.path.exists(f): open_path(f); return jsonify(ok=True)
    return jsonify(ok=False, error="这张表还没有 Excel，先抓一次")


@app.post("/download")
def download():
    """Copy the newest Excel of this search to Downloads as <国家>_<关键词>_<日期>.xlsx and show it in the folder."""
    pj = os.path.join(C.DATA, os.path.basename((request.get_json(force=True) or {}).get("key", "")), "progress.json")
    if not os.path.exists(pj): return jsonify(ok=False, error="这张表还没有 Excel，先抓一次")
    prog = json.load(open(pj, encoding="utf-8")); x = C.excel_path(prog["country"], prog["keywords"])
    src = next((f for f in (x[:-5] + " (新).xlsx", x) if os.path.exists(f)), None)
    if not src: return jsonify(ok=False, error="这张表还没有 Excel，先抓一次")
    kws = sorted({k.strip() for k in prog["keywords"] if k.strip()}, key=str.lower)
    name = re.sub(r'[\\/:*?"<>|]+', " ", f"{CN.get(prog['country'].upper(), prog['country'].upper())}_{'+'.join(kws)}")[:100].strip()
    dl = os.environ.get("WAT_DOWNLOADS") or os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(dl, exist_ok=True)
    dst = os.path.join(dl, f"{name}_{time.strftime('%Y-%m-%d')}.xlsx")
    shutil.copyfile(src, dst)
    if not os.environ.get("WAT_DOWNLOADS"): open_path(dl)
    return jsonify(ok=True, file=dst)


@app.get("/key")
def key():
    return jsonify(key=C.slug_for(request.args.get("country", "").upper(), kw_list(request.args.get("keywords"))))


@app.get("/cities")
def cities():
    return jsonify(list(dict.fromkeys(c["city"] for c in C.build_cells(request.args.get("country", "GB").upper()))))


@app.post("/login")
def login():
    phone = re.sub(r"\D", "", (request.get_json(silent=True) or {}).get("phone", ""))
    with lock:
        if me(): return jsonify(ok=False, error="已经登录了")
        if L["proc"] is not None and L["proc"].poll() is None: L["proc"].terminate(); L["proc"].wait(5)
        for f in (QR, PAIR):
            try: os.remove(f)
            except OSError: pass
        cmd = [paths.NODE, "check.js", "--login-only"] + (["--pair", phone] if phone else [])
        L["proc"] = subprocess.Popen(cmd, cwd=WA, env=paths.child_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return jsonify(ok=True)


@app.get("/qr.png")
def qr():
    if not os.path.exists(QR): abort(404)
    return send_file(QR, mimetype="image/png", max_age=0)


if __name__ == "__main__":
    app.run("127.0.0.1", int(os.environ.get("PORT", 8765)))
