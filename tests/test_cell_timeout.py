"""11-24 client 「七八个小时还没有抓取完100个」: their own progress.json says the normal cell takes 34 s, but 12 cells
hung for 3–254 minutes and ate 10 of 12.5 h. One cell must never hold the run: a hard time limit, partial rows kept,
and three stalled cells in a row stop the run instead of burning the afternoon.
Run: python3 -m unittest discover -s tests -v"""
import csv, os, sys, tempfile, time, unittest
from unittest import mock

TMP = tempfile.mkdtemp(prefix="wat_celltimeout_")
os.environ["WAT_HOME"] = TMP
os.environ["WAT_TABLES"] = os.path.join(TMP, "tables")
APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
sys.path.insert(0, APP)
import pipeline as P  # noqa: E402


class A_RunTee(unittest.TestCase):
    def test_timeout_kills_a_hung_child(self):
        t0 = time.time()
        rc, _ = P.run_tee([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
        self.assertEqual(rc, -9)
        self.assertLess(time.time() - t0, 15)

    def test_a_quick_child_is_not_killed(self):
        self.assertEqual(P.run_tee([sys.executable, "-c", "pass"], timeout=30)[0], 0)

    def test_no_timeout_keeps_old_behaviour(self):
        self.assertEqual(P.run_tee([sys.executable, "-c", "pass"])[0], 0)


ROWS = [{"place_id": "1", "maps_link": "l1", "name": "n1"}, {"place_id": "2", "maps_link": "l2", "name": "n2"}]


class B_CrawlCell(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="wat_cell_", dir=TMP)
        self.args = mock.Mock(country="GB")
        self.cell = {"id": "London#1", "city": "London", "bbox": [51.4, -0.2, 51.41, -0.19]}
        self.calls = []

    def fake_run(self, rc, write=None):
        def run(cmd, cwd=None, quiet=False, timeout=None):
            self.calls.append(timeout)
            out = cmd[cmd.index("--out") + 1]
            if write is not None:
                with open(out, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, ["place_id", "maps_link", "name"]); w.writeheader(); w.writerows(write)
            return rc, 0
        return run

    def test_partial_rows_survive_a_stall(self):
        with mock.patch.object(P, "run_tee", self.fake_run(-9, ROWS)):
            status, new, n, warn, stalled = P.crawl_cell(self.cell, ["kw"], self.args, self.d, set())
        self.assertEqual((status, n, stalled), ("done", 2, True))
        self.assertIn(str(P.CELL_TIMEOUT), warn)          # tells the client this cell was cut short
        self.assertEqual(len(new), 2)

    def test_stall_with_nothing_stays_pending_for_a_later_run(self):
        with mock.patch.object(P, "run_tee", self.fake_run(-9)):
            status, new, n, warn, stalled = P.crawl_cell(self.cell, ["kw"], self.args, self.d, set())
        self.assertEqual((status, n, stalled), ("failed", 0, True))
        self.assertEqual(len(self.calls), 2)             # one more try, not three

    def test_timeout_is_passed_to_every_attempt(self):
        with mock.patch.object(P, "run_tee", self.fake_run(0, ROWS)):
            P.crawl_cell(self.cell, ["kw"], self.args, self.d, set())
        self.assertEqual(self.calls, [P.CELL_TIMEOUT])

    def test_empty_cell_without_a_stall_is_done(self):
        with mock.patch.object(P, "run_tee", self.fake_run(0, [])):   # run_maps always writes the header
            status, new, n, warn, stalled = P.crawl_cell(self.cell, ["kw"], self.args, self.d, set())
        self.assertEqual((status, n, stalled, warn), ("done", 0, False, ""))


class C_RunStopsWhenTheNetworkIsGone(unittest.TestCase):
    def test_three_stalled_cells_end_the_run_and_still_export(self):
        import json, shutil
        d = P.C.data_dir("GB", ["kw"])
        shutil.rmtree(d, ignore_errors=True)             # /resume scans every data folder: leave nothing behind
        calls, after = [], []
        def crawl(cell, kws, args, d, ids):
            calls.append(cell["id"])
            return "failed", [], 0, f"超过 {P.CELL_TIMEOUT} 秒没抓到", True
        saved = (P.crawl_cell, P.website_step, P.wa_step, P.build_excel, sys.argv)
        P.crawl_cell = crawl
        P.website_step = lambda d, c: after.append("web")
        P.wa_step = lambda d, s: 0
        P.build_excel = lambda *a: {}
        sys.argv = ["pipeline.py", "--keywords", "kw", "--country", "GB", "--cells", "8"]
        try:
            with self.assertRaises(SystemExit):
                P.main()
            b = json.load(open(os.path.join(d, "batch.json"), encoding="utf-8"))
        finally:
            P.crawl_cell, P.website_step, P.wa_step, P.build_excel, sys.argv = saved
            shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(len(calls), P.STALL_LIMIT)      # 8 asked, stopped after 3
        self.assertEqual(after, ["web"])                 # still exports what it has
        self.assertFalse(b["maps_finished"])             # window offers 「继续抓取」 next time
        self.assertIn("超过", b["note"])                  # ... and says why it stopped


if __name__ == "__main__":
    unittest.main()
