"""11-16 client: WhatsApp refused every connect with 403 since 11-15 04:46. Evidence (evidence/1116_403/): 1539 lookups in a
day on a day-old link, 300 of them in 3.5 minutes, 87% UK landlines (2.5% on WhatsApp) -> WhatsApp locked the link (403 =
LOCKED / main device gone, whatsmeow events.go). And the tool kept the dead login: window said 已登录, no way to rescan.
Run: python3 -m unittest tests.test_wa_pace -v   (node + the fake Baileys in tests/fake_wa/node_modules)"""
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, "wa_check", "check.js")
FAKE_NM = os.path.join(ROOT, "tests", "fake_wa", "node_modules")
SCALE = 0.01                                  # check.js waits 30-60 s between lookups; tests run it 100x faster

TMP = tempfile.mkdtemp(prefix="wat_wa_")
os.environ["WAT_HOME"] = TMP
os.environ["WAT_TABLES"] = os.path.join(TMP, "tables")
sys.path.insert(0, os.path.join(ROOT, "app"))
import pipeline as P      # noqa: E402
import server             # noqa: E402

STATE = server.paths.WA_STATE


def iso(ago_s):
    return (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).isoformat().replace("+00:00", "Z")


def fresh_state(logged_in=True, cache=()):
    shutil.rmtree(STATE, ignore_errors=True)
    os.makedirs(os.path.join(STATE, "auth"))
    if logged_in:
        with open(os.path.join(STATE, "auth", "creds.json"), "w") as f: json.dump({"me": {"id": "8618600000000:1@s.whatsapp.net"}}, f)
    with open(os.path.join(STATE, "cache.jsonl"), "w") as f:
        for r in cache: f.write(json.dumps(r) + "\n")


def run_check(nums, mode="ok"):
    """Run the real check.js against the fake Baileys; returns (rc, output, lookups[{call, nums}], connects)."""
    d = tempfile.mkdtemp(dir=TMP)
    nin, nout, calls = os.path.join(d, "in.csv"), os.path.join(d, "out.csv"), os.path.join(d, "calls.jsonl")
    with open(nin, "w") as f: f.write("phone_e164\n" + "\n".join(nums) + "\n")
    env = dict(os.environ, WA_STATE=STATE, WAT_NODE_MODULES=FAKE_NM, WAT_PROXY="", FAKE_WA=mode, FAKE_CALLS=calls,
               WAT_PACE_SCALE=str(SCALE), WAT_WA_VERSION="2.3000.1")
    p = subprocess.run(["node", CHECK, "--in", nin, "--out", nout, "--require-login"], env=env, capture_output=True,
                       text=True, timeout=120)
    ev = []
    if os.path.exists(calls):
        with open(calls) as f: ev = [json.loads(l) for l in f]
    return p.returncode, p.stdout + p.stderr, [e for e in ev if "call" in e], sum("connect" in e for e in ev)


NUMS = [f"+44770090{i:04d}" for i in range(12)]


class A_DeadLoginIsDropped(unittest.TestCase):
    def test_403_forgets_login_and_says_why(self):
        fresh_state()
        rc, out, calls, _ = run_check(NUMS, "403")
        self.assertEqual(calls, [])
        self.assertFalse(os.path.exists(os.path.join(STATE, "auth", "creds.json")), "dead login kept -> window still says 已登录")
        with open(os.path.join(STATE, "blocked.json")) as f: b = json.load(f)
        self.assertEqual(b["code"], 403)
        self.assertEqual(rc, 6, out)
        st = server.app.test_client().get("/status").get_json()
        self.assertEqual((st["me"], st["wa_blocked"]), ("", 403))         # login card: rescan + the reason

    def test_successful_login_clears_the_reason(self):
        fresh_state()
        with open(os.path.join(STATE, "blocked.json"), "w") as f: json.dump({"code": 403, "at": iso(60)}, f)
        rc, out, calls, _ = run_check(NUMS[:1])
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(STATE, "blocked.json")))


class B_Pace(unittest.TestCase):
    def test_small_calls_with_long_gaps(self):
        fresh_state()
        rc, out, calls, _ = run_check(NUMS)
        self.assertEqual(rc, 0, out)
        self.assertEqual(sum(len(c["nums"]) for c in calls), 12)
        self.assertTrue(all(len(c["nums"]) <= 5 for c in calls), [len(c["nums"]) for c in calls])
        gaps = [b["call"] - a["call"] for a, b in zip(calls, calls[1:])]
        self.assertTrue(all(g >= 30000 * SCALE for g in gaps), gaps)

    def test_daily_limit_counts_earlier_runs(self):
        fresh_state(cache=[{"number": f"+4420000{i:05d}", "exists": False, "jid": "", "checked_at": iso(7200)} for i in range(598)])
        rc, out, calls, _ = run_check(NUMS)
        self.assertEqual(rc, 0, out)
        self.assertEqual(sum(len(c["nums"]) for c in calls), 2, out)
        self.assertIn("Pace: checking 2 now", out)

    def test_hourly_limit(self):
        fresh_state(cache=[{"number": f"+4420000{i:05d}", "exists": False, "jid": "", "checked_at": iso(600)} for i in range(199)])
        rc, out, calls, _ = run_check(NUMS)
        self.assertEqual(sum(len(c["nums"]) for c in calls), 1, out)

    def test_limit_reached_does_not_connect(self):
        fresh_state(cache=[{"number": f"+4420000{i:05d}", "exists": False, "jid": "", "checked_at": iso(7200)} for i in range(600)])
        rc, out, calls, connects = run_check(NUMS)
        self.assertEqual((rc, calls, connects), (0, [], 0), out)

    def test_disconnect_mid_check_stops_instead_of_reconnecting(self):
        fresh_state()
        rc, out, calls, connects = run_check(NUMS, "503after1")
        self.assertEqual((len(calls), connects), (1, 1), out)       # 04:46: 503, reconnected 17 s later -> 403 ever since
        self.assertEqual(rc, 5, out)


class C_PipelineOrderAndWords(unittest.TestCase):
    def _wa_step(self, rc, out_rows):
        d = os.path.join(TMP, "pipe"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        rows = [{"place_id": "a", "name": "A", "phone_e164": "+442071230000", "phone_type": "fixed_line"},
                {"place_id": "b", "name": "B", "phone_e164": "+447700900001", "phone_type": "mobile"},
                {"place_id": "c", "name": "C", "phone_e164": "+441611230000", "phone_type": "fixed_line"},
                {"place_id": "d", "name": "D", "phone_e164": "+447700900002", "phone_type": "mobile"}]
        P.append_rows(os.path.join(d, "master.csv"), P.MASTER_COLS, rows)
        seen, logs = {}, []

        def tee(cmd, cwd=None, quiet=False):
            seen["in"] = [r["phone_e164"] for r in P.read(cmd[cmd.index("--in") + 1])]
            P.append_rows(cmd[cmd.index("--out") + 1], ["phone_e164", "on_whatsapp"], out_rows)
            return rc, 0
        orig, olog = P.run_tee, P.log
        P.run_tee, P.log = tee, lambda *a: logs.append(" ".join(map(str, a)))
        try: got = P.wa_step(d, False)
        finally: P.run_tee, P.log = orig, olog
        return got, seen["in"], logs

    def test_mobiles_checked_first(self):
        _, order, _ = self._wa_step(0, [])
        self.assertEqual(order[:2], ["+447700900001", "+447700900002"])   # mobiles 78% on WhatsApp, landlines 2.5%

    def test_locked_number_is_explained(self):
        rc, _, logs = self._wa_step(6, [])
        self.assertEqual(rc, 6)
        line = [l for l in logs if "403" in l]
        self.assertTrue(line and "重新扫码" in line[0], logs)
        self.assertNotIn("STOPPED", " ".join(logs))
        self.assertEqual(server.stage_info(logs)["wa_note"], "WhatsApp 断开了这个号")

    def test_left_for_next_run_is_said(self):
        rc, _, logs = self._wa_step(0, [{"phone_e164": "+447700900001", "on_whatsapp": "yes"}])
        self.assertEqual(rc, 0)
        line = [l for l in logs if "下次" in l]
        self.assertTrue(line and "3" in line[0], logs)
        self.assertEqual(server.stage_info(logs)["wa_note"], "剩 3 个下次查")

    def test_progress_uses_numbers_checked_now(self):
        st = server.stage_info(["[whatsapp] checking 40 new numbers (read only, no messages sent)",
                                "Pace: checking 12 now (limit 200 per hour, 600 per 24 h); 28 left for a later run",
                                "Checked 5 (5 cached total)"])
        self.assertEqual((st["wa_i"], st["wa_n"]), (5, 12))


if __name__ == "__main__":
    unittest.main()
