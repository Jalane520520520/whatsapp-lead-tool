"""11-16 boss: 「when it was started, the terminal was pop out and run. Can we hide that?」 The window runs under pythonw
(no console of its own); every console program it starts - gosom.exe (maps), node.exe (WhatsApp login / switch / check),
python - got a new black console window from Windows. Fix: start each child with CREATE_NO_WINDOW (0x08000000); what
those children start (gosom's Chromium/driver) shares the hidden console. Playwright already hides its driver (SW_HIDE).
Run: python -m unittest tests.test_no_window -v"""
import ast, glob, os, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="wat_nowin_")
os.environ["WAT_HOME"] = TMP
os.environ["WAT_TABLES"] = os.path.join(TMP, "tables")
sys.path.insert(0, os.path.join(ROOT, "app"))
import pipeline as P      # noqa: E402
import proc               # noqa: E402
import server             # noqa: E402

SPAWN = {"subprocess": {"Popen", "run", "call", "check_call", "check_output"},
         "asyncio": {"create_subprocess_exec", "create_subprocess_shell"}}
NO_WINDOW = 0x08000000


def spawns(path):
    """Every subprocess/asyncio call in a file that starts a program, with whether it passes creationflags."""
    with open(path, encoding="utf-8") as f: tree = ast.parse(f.read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                and n.func.attr in SPAWN.get(n.func.value.id, ()):
            yield n.lineno, any(k.arg == "creationflags" for k in n.keywords)


class A_EverySpawnHidesItsWindow(unittest.TestCase):
    def test_source(self):
        files = [os.path.join(ROOT, "launcher.py")] + [f for d in ("app", "maps", "web") for f in glob.glob(os.path.join(ROOT, d, "*.py"))]
        missing = [f"{os.path.relpath(f, ROOT)}:{ln}" for f in files for ln, ok in spawns(f) if not ok]
        self.assertEqual(missing, [], "these start a program without CREATE_NO_WINDOW -> black window on the client")

    def test_flag_value_on_windows(self):
        self.assertEqual(getattr(proc, "NO_WINDOW", None), NO_WINDOW if proc.WIN else 0)


class B_RealCallsPassTheFlag(unittest.TestCase):
    """Run the real /start, /login and the pipeline's run_tee with Popen faked; on Windows they must pass 0x08000000."""

    def setUp(self):
        self.seen = seen = []

        class FakeP:
            pid = 999999; stdout = iter(()); returncode = 0
            def __init__(s, cmd, **k): seen.append((os.path.basename(cmd[0]), k.get("creationflags")))
            def poll(s): return 0
            def wait(s, *a): return 0
            def terminate(s): pass
        self.orig = (server.subprocess.Popen, getattr(proc, "NO_WINDOW", None))
        server.subprocess.Popen = P.subprocess.Popen = FakeP
        proc.NO_WINDOW = NO_WINDOW                   # what it is on the client

    def tearDown(self):
        server.subprocess.Popen = P.subprocess.Popen = self.orig[0]
        proc.NO_WINDOW = self.orig[1]
        with server.lock: server.S["state"] = "idle"

    def test_search_login_and_children(self):
        c = server.app.test_client()
        with server.lock: server.S["state"] = "idle"
        self.assertTrue(c.post("/start", json={"keywords": "nowin test", "country": "GB", "cells": "1"}).get_json()["ok"])
        time.sleep(0.2)
        self.assertTrue(c.post("/login", json={}).get_json()["ok"])
        P.run_tee(["node", "check.js"])
        self.assertEqual(len(self.seen), 3, self.seen)
        self.assertTrue(all(f == NO_WINDOW for _, f in self.seen), self.seen)


if __name__ == "__main__":
    unittest.main()
