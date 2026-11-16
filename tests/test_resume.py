"""11-16 client: 「重新打开后没有接着上次的记录接着抓取」. Three causes found on his PC (PLAN 11-16 只读查证):
A 本次 went back to 3 on reopen; B closing the window left the crawl running, the reopened run collided with it;
3 an interrupted website step threw away the sites already checked.  Run: python3 -m unittest discover -s tests -v"""
import json, os, sys, tempfile, textwrap, time, unittest

TMP = tempfile.mkdtemp(prefix="wat_test_")
os.environ["WAT_HOME"] = TMP
os.environ["WAT_TABLES"] = os.path.join(TMP, "tables")
os.environ.pop("WAT_PROXY", None)
APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
sys.path.insert(0, APP)
import cells as C          # noqa: E402
import pipeline as P       # noqa: E402
import server              # noqa: E402

KWS = ["hot pot test"]


def run_pipeline(argv, stop_after=None):
    """pipeline.main() with the slow parts faked; stop_after=k: the process 'dies' while crawling cell k+1."""
    calls = {"n": 0}

    def crawl(cell, kws, args, d, ids):
        if stop_after is not None and calls["n"] >= stop_after: raise SystemExit("killed")
        calls["n"] += 1
        return "done", [], 0, ""
    saved = (P.crawl_cell, P.website_step, P.wa_step, P.build_excel, sys.argv)
    P.crawl_cell, P.website_step, P.wa_step = crawl, (lambda d, c: None), (lambda d, s: 0)
    P.build_excel = lambda *a: {}
    sys.argv = ["pipeline.py", "--keywords", ";".join(KWS), "--country", "GB"] + argv
    try:
        P.main()
    except SystemExit:
        pass
    finally:
        P.crawl_cell, P.website_step, P.wa_step, P.build_excel, sys.argv = saved
    return calls["n"]


class A_Resume(unittest.TestCase):
    """Choose 10 cells, die at cell 5 -> reopen shows 「上次 10 格跑到第 4 格，继续剩下 6 格」 and continues from cell 5."""

    def test_interrupted_batch_is_offered_and_continued(self):
        import shutil; shutil.rmtree(C.data_dir("GB", KWS), ignore_errors=True)
        self.assertEqual(run_pipeline(["--cells", "10"], stop_after=4), 4)
        c = server.app.test_client()
        r = c.get("/resume").get_json()
        self.assertEqual((r["want"], r["done"], r["left"], r["cc"], r["kws"]), (10, 4, 6, "GB", KWS))
        res = c.get("/results?country=GB&keywords=" + KWS[0]).get_json()
        self.assertEqual(res["batch"]["left"], 6)
        # the window's 继续 button -> pipeline gets the 6 remaining cells and keeps the same batch of 10
        seen = {}

        class FakeP:
            pid = 999999; stdout = iter(())
            def __init__(s, cmd, **k): seen["cmd"] = cmd
            def poll(s): return 0
            def wait(s, *a): return 0
        orig = server.subprocess.Popen; server.subprocess.Popen = FakeP
        try:
            j = c.post("/start", json={"keywords": KWS[0], "country": "GB", "cells": "6", "resume": True}).get_json()
        finally:
            server.subprocess.Popen = orig
        self.assertTrue(j["ok"], j)
        cmd = seen["cmd"]; self.assertEqual(cmd[cmd.index("--cells") + 1], "6"); self.assertIn("--keep-batch", cmd)
        time.sleep(0.3)
        with server.lock: server.S["state"] = "idle"
        self.assertEqual(run_pipeline(["--cells", "6", "--keep-batch"]), 6)
        prog = C.load_progress("GB", KWS)
        self.assertEqual(sum(c.get("status") == "done" for c in prog["cells"]), 10)
        self.assertEqual([x["n"] for x in prog["cells"][:10] if x.get("status") == "done"], list(range(1, 11)))
        self.assertIsNone(c.get("/resume").get_json().get("left"))      # batch finished: nothing to offer

    def test_last_count_remembered(self):
        c = server.app.test_client()
        orig = server.subprocess.Popen

        class FakeP:
            pid = 999999; stdout = iter(())
            def __init__(s, cmd, **k): pass
            def poll(s): return 0
            def wait(s, *a): return 0
        server.subprocess.Popen = FakeP
        try:
            with server.lock: server.S["state"] = "idle"
            c.post("/start", json={"keywords": "other kw", "country": "GB", "cells": "100"})
        finally:
            server.subprocess.Popen = orig
        time.sleep(0.3)
        with server.lock: server.S["state"] = "idle"
        self.assertEqual(c.get("/resume").get_json()["last_cells"], 100)


FAKE = textwrap.dedent("""
    import subprocess, sys, time
    kid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    print("10:00:00 this run: 10 cells", flush=True)
    print("10:00:00 KID", kid.pid, flush=True)
    for i in range(1, 11):
        print(f"10:00:0{i % 10} [maps {i}/10] cell", flush=True); time.sleep(float(sys.argv[1]))
""")


def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False


class B_CloseStopsCrawl(unittest.TestCase):
    def setUp(self):
        self.fake = os.path.join(TMP, "fake_pipeline.py"); open(self.fake, "w").write(FAKE)
        with server.lock: server.S.update(state="idle", proc=None)

    def _start(self, secs):
        server.PIPELINE = [self.fake, str(secs)]
        j = server.app.test_client().post("/start", json={"keywords": "b kw", "country": "GB", "cells": "10"}).get_json()
        self.assertTrue(j["ok"], j)
        for _ in range(50):
            kid = [l for l in server.S["log"] if " KID " in l]
            if kid: return server.S["proc"].pid, int(kid[0].split()[-1])
            time.sleep(0.1)
        self.fail("fake pipeline gave no output")

    def test_closing_window_kills_whole_tree(self):
        pid, kid = self._start(5)
        server.shutdown()                               # what main.py calls when the window closes
        time.sleep(0.5)
        self.assertFalse(alive(pid), "pipeline still running after the window closed")
        self.assertFalse(alive(kid), "pipeline's child (gosom/browser) still running")
        self.assertFalse(os.path.exists(server.RUNNING))

    def test_reopen_reattaches_instead_of_second_crawl(self):
        pid, kid = self._start(0.4)
        # the window died without cleanup (crash / Task Manager): forget the process, keep the record on disk
        old = server.S["proc"]
        with server.lock: server.S.update(state="idle", proc=None, log=[])
        import threading; threading.Thread(target=old.wait, daemon=True).start()   # the OS reaps an orphan
        server.recover()                                # what main.py calls when the window opens
        for _ in range(20):                             # the window polls every 2 s
            st = server.app.test_client().get("/status").get_json()
            if st["maps_n"]: break
            time.sleep(0.1)
        self.assertEqual(st["state"], "running"); self.assertEqual(st["maps_n"], 10)
        j = server.app.test_client().post("/start", json={"keywords": "b kw", "country": "GB", "cells": "3"}).get_json()
        self.assertFalse(j["ok"])                        # no second crawl on the same data
        for _ in range(100):
            if server.S["state"] != "running": break
            time.sleep(0.1)
        self.assertNotEqual(server.S["state"], "running")
        self.assertFalse(os.path.exists(server.RUNNING))
        try: os.kill(kid, 9)
        except OSError: pass


class C_WebsiteKeepsCheckedSites(unittest.TestCase):
    def test_interrupted_website_step_keeps_checked_sites(self):
        d = os.path.join(TMP, "webtest"); os.makedirs(d, exist_ok=True)
        rows = [{"place_id": f"p{i}", "name": f"n{i}", "website": f"https://s{i}.example"} for i in range(5)]
        P.append_rows(os.path.join(d, "master.csv"), P.MASTER_COLS, rows)
        seen = {}

        def tee_killed(cmd, cwd=None, quiet=False):      # find_wa wrote 3 sites, then the window was closed
            out = cmd[5]
            P.append_rows(out, P.MASTER_COLS + P.WEB_COLS[1:], [dict(r, site_status="ok") for r in rows[:3]])
            raise SystemExit("killed")

        def tee_ok(cmd, cwd=None, quiet=False):           # find_wa itself skips rows already in its out file
            out = cmd[5]
            seen["already"] = [r["place_id"] for r in P.read(out)] if os.path.exists(out) else []
            have = set(seen["already"])
            P.append_rows(out, P.MASTER_COLS + P.WEB_COLS[1:], [dict(r, site_status="ok") for r in rows if r["place_id"] not in have])
            return 0, 0
        orig = P.run_tee
        try:
            P.run_tee = tee_killed
            with self.assertRaises(SystemExit): P.website_step(d, "GB")
            P.run_tee = tee_ok
            P.website_step(d, "GB")
        finally:
            P.run_tee = orig
        self.assertEqual(seen["already"], ["p0", "p1", "p2"], "sites checked before the close were thrown away")
        self.assertEqual(sorted(r["place_id"] for r in P.read(os.path.join(d, "web_cache.csv"))), [f"p{i}" for i in range(5)])

    def test_progress_counts_resumed_sites(self):
        st = server.stage_info(["10:00:00 [website] 5 new businesses (slow, ~10 s per site)",
                                "10:00:00 [website] 3 already checked before the window closed",
                                "  9.0s https://s3.example -> ok"])
        self.assertEqual((st["web_i"], st["web_n"]), (4, 5))


if __name__ == "__main__":
    unittest.main()
