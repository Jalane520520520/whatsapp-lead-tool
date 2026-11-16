"""启动器（装进安装包，永远不热更新）。PLAN v1.4 第 2 步；做法照 live-id-grabber/loader.js（客户安卓机上实际跑过）：
远程（1.1.0 起：Gitee 签名清单 5 秒，不行再 GitHub API 5 秒）-> 本机缓存 -> 安装包内置。启动器不放业务逻辑，所以它永远不用更新。
这里多一步：一整包代码（app.zip），下载后检查该有的文件都在、版本号对得上，否则不换。"""
import json, os, shutil, sys, tempfile, threading, urllib.request, zipfile

REPO = "Jalane520520520/whatsapp-lead-tool"
INSTALL = os.path.dirname(os.path.abspath(__file__))                 # C:\Program Files\WhatsApp客户提取
HOME = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "WhatsApp客户提取")
APPS = os.path.join(HOME, "app")
BUILTIN = os.path.join(INSTALL, "app_builtin")                       # code shipped inside the installer
MUST_HAVE = ("app/server.py", "app/window.html", "app/main.py", "app/pipeline.py", "wa_check/check.js", "VERSION")


def log(msg):
    os.makedirs(HOME, exist_ok=True)
    with open(os.path.join(HOME, "launcher.log"), "a", encoding="utf-8") as f: f.write(msg + "\n")


def ver(s):
    try: return tuple(int(x) for x in s.strip().lstrip("v").split("."))
    except ValueError: return (0,)


def local():
    """(version, folder) of the code to run: cache if newer than built-in, else built-in."""
    bv = open(os.path.join(BUILTIN, "VERSION"), encoding="utf-8").read().strip()
    try:
        v = open(os.path.join(APPS, "current.txt"), encoding="utf-8").read().strip()
        if ver(v) > ver(bv) and os.path.exists(os.path.join(APPS, v, "app", "main.py")): return v, os.path.join(APPS, v)
    except OSError: pass
    return bv, BUILTIN


GITEE = "https://raw.giteeusercontent.com/Jalane/whatsapp-lead-update/raw/master/"   # PLAN E 11-17: 国内能直连
PUBKEY = "aTYJQu13U0NvufHXrG5eXkVO+RmiLMLwMANlAfLt0kY="   # Ed25519; private key only on our Mac (.env WAT_UPDATE_SIGNING_KEY)


def fetch(url, timeout, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "wat-launcher", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()


def install_zip(data, tag, tmp):
    """Unpack a downloaded app.zip into APPS/<tag> and switch to it - only after every check passed."""
    zp = os.path.join(tmp, "app.zip")
    with open(zp, "wb") as f: f.write(data)
    with zipfile.ZipFile(zp) as z:
        names = set(z.namelist())
        missing = [m for m in MUST_HAVE if m not in names]
        if missing: raise ValueError(f"app.zip 缺 {missing}")
        if any(n.startswith("/") or ".." in n.split("/") for n in names): raise ValueError("app.zip 路径不安全")
        stage = os.path.join(tmp, "x"); z.extractall(stage)
    if open(os.path.join(stage, "VERSION"), encoding="utf-8").read().strip() != tag: raise ValueError("VERSION 和标签不一致")
    dest = os.path.join(APPS, tag)
    shutil.rmtree(dest, ignore_errors=True); shutil.move(stage, dest)
    with open(os.path.join(APPS, "current.txt"), "w", encoding="utf-8") as f: f.write(tag)   # switch only after all checks
    return tag


def from_gitee(cur, tmp):
    """Signed manifest on Gitee (copied from 余彩益): current.json = {payload: base64(json), sig: base64(Ed25519)}.
    payload = {app, version, zip, sha256, size}. A wrong signature, app, size or sha256 is refused."""
    import base64, hashlib
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    m = json.loads(fetch(GITEE + "current.json", 5))
    payload = base64.b64decode(m["payload"])
    Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBKEY)).verify(base64.b64decode(m["sig"]), payload)
    p = json.loads(payload)
    if p.get("app") != "whatsapp-lead-tool": raise ValueError("清单不是本软件的")
    tag = p["version"]
    if ver(tag) <= ver(cur): return None
    if "/" in p["zip"] or ".." in p["zip"]: raise ValueError("清单里的文件名不安全")
    data = fetch(GITEE + p["zip"], 60)
    if len(data) != p["size"] or hashlib.sha256(data).hexdigest() != p["sha256"]: raise ValueError("app.zip 和清单对不上")
    return install_zip(data, tag, tmp)


def from_github(cur, tmp):
    """GitHub API (instant; raw.githubusercontent.com caches for minutes - live-id-grabber 实测). Needs the client's VPN."""
    rel = json.loads(fetch(f"https://api.github.com/repos/{REPO}/releases/latest", 5, {"Accept": "application/vnd.github+json"}))
    tag = rel["tag_name"].lstrip("v")
    if ver(tag) <= ver(cur): return None
    asset = next(a for a in rel["assets"] if a["name"] == "app.zip")
    return install_zip(fetch(asset["browser_download_url"], 60), tag, tmp)


def update(cur):
    """Gitee first (国内直连), GitHub second. Returns (new_tag or None, source, problems)."""
    problems = []
    for name, fn in (("gitee", from_gitee), ("github", from_github)):
        tmp = tempfile.mkdtemp(prefix="wat_")
        try:
            return fn(cur, tmp), name, problems
        except Exception as e:
            problems.append(f"{name}: {type(e).__name__}: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    raise RuntimeError("; ".join(problems))


def main():
    os.makedirs(APPS, exist_ok=True)
    cur, _ = local()
    box = {}
    def job():
        try: box["new"], box["src"], box["problems"] = update(cur)
        except Exception as e: box["err"] = f"{type(e).__name__}: {e}"
    t = threading.Thread(target=job, daemon=True); t.start(); t.join(75)   # 5 s to ask; a found update may take longer to download
    if "err" in box: log(f"update skipped ({box['err']}); running {cur}")
    elif box.get("new"): log(f"update: {cur} -> {box['new']} (from {box['src']})")
    elif t.is_alive(): log(f"update timed out; running {cur}")
    else: log(f"up to date {cur} (checked {box['src']})")
    if box.get("problems"): log("  " + "; ".join(box["problems"]))
    v, code = local()
    os.environ.update(
        WAT_HOME=HOME,
        WAT_NODE=os.path.join(INSTALL, "node", "node.exe"),
        WAT_NODE_MODULES=os.path.join(INSTALL, "node_modules"),
        WAT_GOSOM=os.path.join(INSTALL, "gosom", "gosom-1.18.1-winargs-edge.exe"),   # 1.1.0: can drive Edge (PLAN E)
        PLAYWRIGHT_BROWSERS_PATH=os.path.join(HOME, "browsers"),   # 1.1.0 ships no Chromium; app/browser.py picks Edge
        PLAYWRIGHT_DRIVER_PATH=os.path.join(INSTALL, "pw-driver"),    # gosom 的驱动，打包时已装好
        WAT_VERSION=v)
    sys.path.insert(0, os.path.join(code, "app"))
    sys.argv = [os.path.join(code, "app", "main.py")]
    import runpy
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
