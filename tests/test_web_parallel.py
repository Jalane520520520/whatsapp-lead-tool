"""11-24 client 「七八个小时还没有抓取完100个」: after the maps step their run sat in the website step for an hour —
165 sites, 68 of them each burning a 30 s page timeout, one after another. Sites must run a few at a time.
Run: python3 -m unittest tests.test_web_parallel -v"""
import asyncio, csv, os, sys, tempfile, time, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))
try:                                                  # this Mac has no crawl4ai; CI installs it for real
    import crawl4ai  # noqa: F401
except ImportError:
    for _n in ("crawl4ai", "crawl4ai.async_configs", "phonenumbers"):
        sys.modules[_n] = mock.MagicMock(name=_n)
import find_wa as F  # noqa: E402


def write_in(path, n):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["place_id", "website"])
        w.writeheader()
        for i in range(n):
            w.writerow({"place_id": f"p{i}", "website": f"https://site{i}.example"})


class A_ManySitesAtOnce(unittest.TestCase):
    def run_main(self, n, conc):
        d = tempfile.mkdtemp(prefix="wat_web_")
        inp, out = os.path.join(d, "in.csv"), os.path.join(d, "out.csv")
        write_in(inp, n)
        peak = {"now": 0, "max": 0}
        async def fake_process(crawler, url, region):
            peak["now"] += 1; peak["max"] = max(peak["max"], peak["now"])
            await asyncio.sleep(0.3)                       # a page load that takes a while
            peak["now"] -= 1
            return {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "ok"}
        class FakeCrawler:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
        patches = [mock.patch.object(F, "AsyncWebCrawler", lambda config=None: FakeCrawler()),
                   mock.patch.object(F, "process", fake_process),
                   mock.patch.dict(os.environ, {"WAT_WEB_CONCURRENCY": str(conc), "WAT_BROWSER_CHANNEL": "msedge"})]
        for p in patches: p.start()
        try:
            t0 = time.time()
            asyncio.run(F.main(inp, out, "GB"))
            took = time.time() - t0
            rows = list(csv.DictReader(open(out, encoding="utf-8")))
        finally:
            for p in patches: p.stop()
        return peak, took, rows

    def test_five_sites_run_at_the_same_time(self):
        peak, took, rows = self.run_main(10, 5)
        self.assertEqual(len(rows), 10)                    # every site still gets its row
        self.assertEqual(peak["max"], 5)                   # never more than asked
        self.assertLess(took, 1.6)                         # 10 x 0.3 s one after another = 3 s

    def test_one_at_a_time_still_works(self):
        peak, took, rows = self.run_main(4, 1)
        self.assertEqual((len(rows), peak["max"]), (4, 1))
        self.assertGreaterEqual(took, 1.1)

    def test_sites_already_checked_are_kept_and_not_fetched_again(self):
        d = tempfile.mkdtemp(prefix="wat_web2_")
        inp, out = os.path.join(d, "in.csv"), os.path.join(d, "out.csv")
        write_in(inp, 3)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["place_id", "website", "wa_number_e164", "wa_source_url", "wa_evidence", "site_status"])
            w.writeheader(); w.writerow({"place_id": "p0", "website": "https://site0.example", "wa_number_e164": "+441234567890",
                                         "wa_source_url": "", "wa_evidence": "", "site_status": "ok"})
        seen = []
        async def fake_process(crawler, url, region):
            seen.append(url); return {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "ok"}
        class FakeCrawler:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
        with mock.patch.object(F, "AsyncWebCrawler", lambda config=None: FakeCrawler()), \
             mock.patch.object(F, "process", fake_process), \
             mock.patch.dict(os.environ, {"WAT_BROWSER_CHANNEL": "msedge"}):
            asyncio.run(F.main(inp, out, "GB"))
        self.assertNotIn("https://site0.example", seen)     # the number found last time is not lost or re-fetched
        rows = {r["place_id"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}
        self.assertEqual(rows["p0"]["wa_number_e164"], "+441234567890")
        self.assertEqual(len(rows), 3)


    def test_one_site_raising_does_not_kill_the_others(self):
        d = tempfile.mkdtemp(prefix="wat_web3_")
        inp, out = os.path.join(d, "in.csv"), os.path.join(d, "out.csv")
        write_in(inp, 4)
        async def fake_process(crawler, url, region):
            if url.endswith("site1.example"):
                raise RuntimeError("browser page died")
            return {"wa_number_e164": "", "wa_source_url": "", "wa_evidence": "", "site_status": "ok"}
        class FakeCrawler:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
        with mock.patch.object(F, "AsyncWebCrawler", lambda config=None: FakeCrawler()), \
             mock.patch.object(F, "process", fake_process), \
             mock.patch.dict(os.environ, {"WAT_BROWSER_CHANNEL": "msedge"}):
            asyncio.run(F.main(inp, out, "GB"))
        rows = {r["place_id"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}
        self.assertEqual(len(rows), 4)                      # every business still gets a row
        self.assertIn("browser page died", rows["p1"]["site_status"])
        self.assertEqual(rows["p2"]["site_status"], "ok")


if __name__ == "__main__":
    unittest.main()
