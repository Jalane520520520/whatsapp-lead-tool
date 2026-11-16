"""Is a process alive / stop a whole process tree, on Windows (client) and Mac (dev). 11-16: closing the window left
pipeline.py + gosom + Chromium running; the reopened window started a second crawl on the same files."""
import os, subprocess, sys, time

WIN = sys.platform.startswith("win")


def alive(pid):
    if not pid: return False
    if WIN:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h: return False
        try:
            code = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(int(pid), 0); return True
    except PermissionError:
        return True
    except OSError:
        return False


def exe(pid):
    """Full path of the program a process runs ('' if unknown); guards against a reused PID."""
    if not WIN: return ""
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))
    if not h: return ""
    try:
        buf = ctypes.create_unicode_buffer(1024); n = ctypes.c_ulong(1024)
        return buf.value if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally:
        k.CloseHandle(h)


def ours(pid):
    """Alive and (on Windows) running the same Python as this program."""
    if not alive(pid): return False
    p = exe(pid)
    return not WIN or not p or os.path.dirname(p).lower() == os.path.dirname(sys.executable).lower()


def kill_tree(pid):
    """pipeline.py and everything it started (run_maps -> gosom -> Chromium, find_wa -> Chromium)."""
    if not pid: return
    if WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=0x08000000)             # CREATE_NO_WINDOW
    else:
        import signal
        try: pg = os.getpgid(int(pid))
        except OSError: pg = None
        try:                                                  # pipeline's SIGTERM handler kills its child's group
            os.kill(int(pid), signal.SIGTERM)
            for _ in range(20):
                if not alive(pid): break
                time.sleep(0.1)
        except OSError: pass
        if pg and pg != os.getpgid(0):
            try: os.killpg(pg, signal.SIGKILL)
            except OSError: pass
    for _ in range(50):
        if not alive(pid): return
        time.sleep(0.1)
