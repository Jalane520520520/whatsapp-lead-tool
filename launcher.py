"""启动器（装进安装包，永远不热更新）。PLAN v1.4 第 2 步；做法照 live-id-grabber/loader.js（客户安卓机上实际跑过）：
远程（GitHub API，5 秒）-> 本机缓存 -> 安装包内置。启动器不放业务逻辑，所以它永远不用更新。
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


def update(cur):
    """Ask GitHub API (instant; raw.githubusercontent.com caches for minutes - live-id-grabber 实测)."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "wat-launcher"})
    rel = json.load(urllib.request.urlopen(req, timeout=5))
    tag = rel["tag_name"].lstrip("v")
    if ver(tag) <= ver(cur): return None
    asset = next(a for a in rel["assets"] if a["name"] == "app.zip")
    tmp = tempfile.mkdtemp(prefix="wat_")
    try:
        zp = os.path.join(tmp, "app.zip")
        with urllib.request.urlopen(asset["browser_download_url"], timeout=60) as r, open(zp, "wb") as f: shutil.copyfileobj(r, f)
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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    os.makedirs(APPS, exist_ok=True)
    cur, _ = local()
    box = {}
    def job():
        try: box["new"] = update(cur)
        except Exception as e: box["err"] = f"{type(e).__name__}: {e}"
    t = threading.Thread(target=job, daemon=True); t.start(); t.join(75)   # 5 s to ask; a found update may take longer to download
    if "err" in box: log(f"update skipped ({box['err']}); running {cur}")
    elif box.get("new"): log(f"update: {cur} -> {box['new']}")
    elif t.is_alive(): log(f"update timed out; running {cur}")
    v, code = local()
    os.environ.update(
        WAT_HOME=HOME,
        WAT_NODE=os.path.join(INSTALL, "node", "node.exe"),
        WAT_NODE_MODULES=os.path.join(INSTALL, "node_modules"),
        WAT_GOSOM=os.path.join(INSTALL, "gosom", "gosom-1.18.1-winargs.exe"),
        PLAYWRIGHT_BROWSERS_PATH=os.path.join(INSTALL, "browsers"),
        PLAYWRIGHT_DRIVER_PATH=os.path.join(INSTALL, "pw-driver"),    # gosom 的驱动，打包时已装好
        WAT_VERSION=v)
    sys.path.insert(0, os.path.join(code, "app"))
    sys.argv = [os.path.join(code, "app", "main.py")]
    import runpy
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
