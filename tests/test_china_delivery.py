"""PLAN E (boss 11-17, 「All three」): updates from Gitee with a signed manifest, GitHub as backup; the app drives the
PC's own Edge instead of a bundled Chromium. Run: python -m unittest tests.test_china_delivery -v (needs cryptography)."""
import base64, functools, http.server, io, json, os, sys, tempfile, threading, unittest, zipfile
from unittest import mock
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "app")); sys.path.insert(0, os.path.join(ROOT, "build"))
import launcher as L            # noqa: E402
import make_gitee_release as R  # noqa: E402
import browser as B             # noqa: E402

KEY = Ed25519PrivateKey.generate()
PUB = base64.b64encode(KEY.public_key().public_bytes_raw()).decode()


def app_zip(path, version):
    with zipfile.ZipFile(path, "w") as z:
        for m in L.MUST_HAVE: z.writestr(m, version if m == "VERSION" else "# test\n")


class Gitee(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wat_gitee_")
        self.site = os.path.join(self.tmp, "site"); os.makedirs(self.site)
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=self.site)
        h.log_message = lambda *a: None
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.patches = [mock.patch.object(L, "GITEE", f"http://127.0.0.1:{self.srv.server_port}/"),
                        mock.patch.object(L, "PUBKEY", PUB), mock.patch.object(R, "PUBKEY", PUB),
                        mock.patch.object(L, "APPS", os.path.join(self.tmp, "apps")),
                        mock.patch.object(L, "from_github", mock.Mock(side_effect=OSError("no VPN")))]
        for p in self.patches: p.start()
        os.makedirs(L.APPS)

    def tearDown(self):
        for p in self.patches: p.stop()
        self.srv.shutdown()

    def publish(self, version, key=KEY):
        z = os.path.join(self.tmp, f"build-{version}.zip"); app_zip(z, version)
        R.make(z, self.site, key) if key is KEY else self._make_other(z, key)

    def _make_other(self, z, key):
        with mock.patch.object(R, "PUBKEY", base64.b64encode(key.public_key().public_bytes_raw()).decode()):
            R.make(z, self.site, key)

    def test_signed_update_installs(self):
        self.publish("1.1.1")
        new, src, problems = L.update("1.1.0")
        self.assertEqual((new, src, problems), ("1.1.1", "gitee", []))
        self.assertEqual(open(os.path.join(L.APPS, "current.txt")).read(), "1.1.1")
        self.assertTrue(os.path.exists(os.path.join(L.APPS, "1.1.1", "app", "main.py")))

    def test_same_version_is_no_update(self):
        self.publish("1.1.0")
        self.assertEqual(L.update("1.1.0")[:2], (None, "gitee"))

    def test_wrong_key_refused_then_github_tried(self):
        self.publish("1.1.1", key=Ed25519PrivateKey.generate())
        with self.assertRaises(RuntimeError) as e: L.update("1.1.0")
        self.assertIn("gitee: InvalidSignature", str(e.exception)); self.assertIn("github: OSError", str(e.exception))
        self.assertFalse(os.path.exists(os.path.join(L.APPS, "current.txt")))

    def test_swapped_zip_refused(self):
        self.publish("1.1.1")
        app_zip(os.path.join(self.site, "app-1.1.1.zip"), "1.1.1-evil")      # same name, other bytes
        with self.assertRaises(RuntimeError) as e: L.update("1.1.0")
        self.assertIn("对不上", str(e.exception))
        self.assertFalse(os.path.exists(os.path.join(L.APPS, "current.txt")))



class Keys(unittest.TestCase):
    def test_real_keys_match(self):
        """The public key in launcher.py and the release tool are the same one (and it is a real Ed25519 key)."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        self.assertEqual(L.PUBKEY, R.PUBKEY)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(L.PUBKEY))


class Browser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wat_br_")
        self.env = mock.patch.dict(os.environ, {"LOCALAPPDATA": os.path.join(self.tmp, "la"), "ProgramFiles": os.path.join(self.tmp, "pf"),
                                                "ProgramFiles(x86)": os.path.join(self.tmp, "pf86"),
                                                "PLAYWRIGHT_BROWSERS_PATH": os.path.join(self.tmp, "browsers")})
        self.env.start()
        for k in ("WAT_BROWSER_CHANNEL", "WAT_BROWSER_EXE"): os.environ.pop(k, None)
        self.nt = mock.patch.object(B.os, "name", "nt"); self.nt.start()
        self.net = mock.patch.object(B.urllib.request, "urlopen", mock.Mock(side_effect=AssertionError("real download in a test")))
        self.net.start()

    def tearDown(self):
        self.net.stop(); self.nt.stop(); self.env.stop()

    def touch(self, *p):
        f = os.path.join(self.tmp, *p); os.makedirs(os.path.dirname(f), exist_ok=True); open(f, "w").close()

    def test_edge_first(self):
        self.touch("pf86", "Microsoft", "Edge", "Application", "msedge.exe")
        self.touch("pf", "Google", "Chrome", "Application", "chrome.exe")
        self.assertEqual(B.pick(self.tmp), "Microsoft Edge"); self.assertEqual(os.environ["WAT_BROWSER_CHANNEL"], "msedge")

    def test_chrome_when_no_edge(self):
        self.touch("la", "Google", "Chrome", "Application", "chrome.exe")
        self.assertEqual(B.pick(self.tmp), "Google Chrome"); self.assertEqual(os.environ["WAT_BROWSER_CHANNEL"], "chrome")

    def test_old_install_keeps_bundled(self):
        self.touch("browsers", "chromium-1228", "chrome-win64", "chrome.exe")
        self.assertEqual(B.pick(self.tmp), "bundled Chromium"); self.assertNotIn("WAT_BROWSER_CHANNEL", os.environ)

    def test_download_when_nothing(self):
        def fake(home, log):
            return os.path.join(home, "browsers", "cft", "chrome-win64", "chrome.exe")
        with mock.patch.object(B, "_download", fake):
            self.assertIn("downloaded", B.pick(self.tmp))
        self.assertTrue(os.environ["WAT_BROWSER_EXE"].endswith("chrome.exe"))

    def test_download_failure_says_install_edge(self):
        with mock.patch.object(B, "_download", mock.Mock(side_effect=OSError("timed out"))):
            self.assertIn("请装 Microsoft Edge", B.pick(self.tmp))

    def test_bad_download_size_not_kept(self):
        B.urllib.request.urlopen.side_effect = None
        B.urllib.request.urlopen.return_value = io.BytesIO(b"x" * 10)
        with self.assertRaises(ValueError): B._download(self.tmp, lambda *a: None)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "browsers", f"cft-{B.CFT_VER}")))

    def test_hand_override(self):
        os.environ["WAT_BROWSER_CHANNEL"] = "bundled"
        self.touch("pf86", "Microsoft", "Edge", "Application", "msedge.exe")
        self.assertIn("by hand", B.pick(self.tmp)); self.assertNotIn("WAT_BROWSER_CHANNEL", os.environ)


if __name__ == "__main__":
    unittest.main()
