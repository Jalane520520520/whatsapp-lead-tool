"""Which browser the Google Maps step (gosom) and the website step (find_wa) drive. PLAN E, boss 11-17.
Installer 1.1.0 no longer ships Chromium (694 of 1,350 MB). Order:
  1. Microsoft Edge - every Windows 10/11 has it. Client PC 11-17: maps 13 = 13 same places, website 11 vs 4 WhatsApp.
  2. Google Chrome.
  3. A Chromium already in PLAYWRIGHT_BROWSERS_PATH (installers up to 1.0.11 ship one) - keep the old behaviour.
  4. Download Chrome for Testing (same build gosom expects) from npmmirror once (client PC 11-16: npmmirror 5-6 MB/s).
The choice goes into env that every child reads: WAT_BROWSER_CHANNEL (gosom via the scrapemate patch, find_wa,
playwright_maps) or WAT_BROWSER_EXE. Set either by hand to override; WAT_BROWSER_CHANNEL=bundled = old behaviour."""
import glob, os, shutil, sys, tempfile, urllib.request, zipfile

CFT_VER = "149.0.7827.55"          # = chromium-1228, the build playwright-go 0.6100.0 (gosom 1.18.1) drives
CFT_URL = f"https://cdn.npmmirror.com/binaries/chrome-for-testing/{CFT_VER}/win64/chrome-win64.zip"
CFT_SIZE = 192511857               # registry.npmmirror.com/-/binary/chrome-for-testing/149.0.7827.55/win64/ (11-17)


def _installed(*rel):
    """Same places Playwright looks for channel msedge/chrome on Windows."""
    for env in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env)
        if root and os.path.isfile(os.path.join(root, *rel)):
            return os.path.join(root, *rel)
    return ""


def _bundled():
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or ""
    return bool(root) and bool(glob.glob(os.path.join(root, "chromium*-*", "*", "chrome*.exe")))


def _download(home, log):
    dest = os.path.join(home, "browsers", f"cft-{CFT_VER}")
    exe = os.path.join(dest, "chrome-win64", "chrome.exe")
    if os.path.isfile(exe):
        return exe
    log(f"[browser] 电脑上没有 Edge / Chrome，第一次运行下载 Chromium（{CFT_SIZE // 1048576} MB，国内镜像）")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="wat_cft_", dir=os.path.dirname(dest))
    try:
        zp = os.path.join(tmp, "chrome-win64.zip")
        with urllib.request.urlopen(CFT_URL, timeout=60) as r, open(zp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        got = os.path.getsize(zp)
        if got != CFT_SIZE:
            raise ValueError(f"size {got} != {CFT_SIZE}")
        with zipfile.ZipFile(zp) as z:
            z.extractall(os.path.join(tmp, "x"))
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(os.path.join(tmp, "x"), dest)          # only a complete download gets the real name
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return exe


def pick(home, log=print):
    """Set WAT_BROWSER_CHANNEL / WAT_BROWSER_EXE for this process and its children; return a one-line description."""
    ch, exe = os.environ.get("WAT_BROWSER_CHANNEL", ""), os.environ.get("WAT_BROWSER_EXE", "")
    if ch == "bundled":
        os.environ.pop("WAT_BROWSER_CHANNEL"); os.environ.pop("WAT_BROWSER_EXE", None)
        return "bundled Chromium (set by hand)"
    if ch or exe:
        return f"set by hand: {exe or ch}"
    if os.name != "nt":
        return "bundled Chromium (not Windows)"
    if _installed("Microsoft", "Edge", "Application", "msedge.exe"):
        os.environ["WAT_BROWSER_CHANNEL"] = "msedge"; return "Microsoft Edge"
    if _installed("Google", "Chrome", "Application", "chrome.exe"):
        os.environ["WAT_BROWSER_CHANNEL"] = "chrome"; return "Google Chrome"
    if _bundled():
        return "bundled Chromium"
    try:
        os.environ["WAT_BROWSER_EXE"] = _download(home, log)
        return f"Chromium {CFT_VER} (downloaded)"
    except Exception as e:
        return f"ERROR 没有 Edge / Chrome，下载 Chromium 失败（{type(e).__name__}: {e}）；请装 Microsoft Edge 后再开"


if __name__ == "__main__":
    print(pick(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()))
    print({k: v for k, v in os.environ.items() if k.startswith("WAT_BROWSER")})
