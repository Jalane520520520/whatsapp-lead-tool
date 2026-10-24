"""Where everything lives. Dev (this Mac): the old places inside tool/. Installed (Windows): the launcher sets
WAT_HOME (%LOCALAPPDATA%\\WhatsApp客户提取) and the program folders; see PLAN v1.4 第 1 步."""
import os

APP = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(APP)                       # app/ maps/ web/ wa_check/ live here (dev tool/, or the hot-update folder)
HOME = os.environ.get("WAT_HOME") or CODE         # things that change: data, runs, WhatsApp login
DATA = os.path.join(HOME, "data")
RUNS = os.path.join(HOME, "runs")
WA_STATE = os.path.join(HOME, "wa_auth") if os.environ.get("WAT_HOME") else os.path.join(CODE, "wa_check")
TABLES = os.environ.get("WAT_TABLES") or (
    os.path.join(os.path.expanduser("~"), "Documents", "WhatsApp客户提取", "表格") if os.environ.get("WAT_HOME")
    else os.path.join(CODE, "表格"))
NODE = os.environ.get("WAT_NODE") or "node"       # installed: <install>\node\node.exe
GOSOM = os.environ.get("WAT_GOSOM") or ""          # installed: <install>\gosom\google_maps_scraper-...exe
NODE_MODULES = os.environ.get("WAT_NODE_MODULES") or os.path.join(CODE, "wa_check", "node_modules")


def system_proxy():
    """The proxy the client's VPN set (Windows: registry 'Internet Settings', read by urllib). Browsers follow it,
    Node does not, so check.js gets it as WAT_PROXY. WhatsApp is blocked in mainland China (10-23: no QR)."""
    import urllib.request
    p = urllib.request.getproxies()
    for k in ("https", "http"):
        v = p.get(k, "")
        if v and not v.startswith("socks"):
            return v
    return ""


def child_env():
    """Env for child programs (check.js reads WA_STATE and WAT_PROXY)."""
    e = dict(os.environ, WA_STATE=WA_STATE)
    if not e.get("WAT_PROXY"):
        e["WAT_PROXY"] = system_proxy()
    if os.environ.get("WAT_HOME"): e["NODE_PATH"] = NODE_MODULES
    return e
