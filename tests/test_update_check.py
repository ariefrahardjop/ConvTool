# tests/test_update_check.py — Uji logika notif + self-update.
#
# Tanpa GUI dan tanpa jaringan luar: server HTTP lokal (127.0.0.1)
# menyajikan JSON rilis GitHub palsu + exe palsu. Jalankan:
#   .venv-test/bin/python tests/test_update_check.py

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import update_check  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-update")

RELEASE_NEW = {
    "tag_name": "v1.9.7",
    "name": "ConvTool v1.9.7",
    "body": "- Perbaikan A\n- Perbaikan B",
    "assets": [
        {"name": "ConvTool.exe",
         "browser_download_url": None,  # diisi per tes (URL server lokal)
         "size": 1234},
        {"name": "ConvTool-v1.9.7.zip",
         "browser_download_url": "https://example.invalid/x.zip",
         "size": 999},
    ],
}
RELEASE_OLD = dict(RELEASE_NEW, tag_name="v1.9.5")
RELEASE_NO_EXE = dict(RELEASE_NEW, tag_name="v1.9.8", assets=[
    {"name": "readme.txt", "browser_download_url": "https://example.invalid/r.txt", "size": 5}])


class Handler(BaseHTTPRequestHandler):
    mode = "new"       # new | old | noexe | badjson | slow | 404
    hits = 0
    exe_bytes = b"X" * 1234

    def log_message(self, *a):
        pass

    def do_GET(self):
        Handler.hits += 1
        if self.path == "/releases/latest":
            if Handler.mode == "404":
                self.send_response(404)
                self.end_headers()
                return
            if Handler.mode == "badjson":
                body = b"{bukan json"
            elif Handler.mode == "slow":
                import time
                time.sleep(2)
                body = json.dumps(RELEASE_NEW).encode()
            elif Handler.mode == "old":
                body = json.dumps(RELEASE_OLD).encode()
            elif Handler.mode == "noexe":
                body = json.dumps(RELEASE_NO_EXE).encode()
            else:
                data = dict(RELEASE_NEW)
                data["assets"] = [dict(a) for a in RELEASE_NEW["assets"]]
                data["assets"][0]["browser_download_url"] = (
                    "http://127.0.0.1:%d/exe" % self.server.server_port)
                body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/exe":
            body = Handler.exe_bytes
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


class UpdateCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.api_url = "http://127.0.0.1:%d/releases/latest" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        if os.path.exists(WORK):
            shutil.rmtree(WORK)
        os.makedirs(WORK)
        os.environ["CONVTOOL_UPDATE_STATE_DIR"] = WORK
        self._orig_url = update_check.API_URL
        self._orig_timeout = update_check._FETCH_TIMEOUT
        update_check.API_URL = self.api_url
        update_check._PENDING = None
        update_check._SHOWN_THIS_SESSION = False
        Handler.hits = 0
        Handler.mode = "new"
        Handler.exe_bytes = b"X" * 1234

    def tearDown(self):
        update_check.API_URL = self._orig_url
        update_check._FETCH_TIMEOUT = self._orig_timeout
        os.environ.pop("CONVTOOL_UPDATE_STATE_DIR", None)

    # ---- versi ----
    def test_parse_version(self):
        self.assertEqual(update_check._parse_version("v1.9.6"), (1, 9, 6))
        self.assertEqual(update_check._parse_version("1.10.0"), (1, 10, 0))
        self.assertEqual(update_check._parse_version("1.9"), (1, 9))
        self.assertEqual(update_check._parse_version("sampah"), (0,))

    def test_is_newer(self):
        self.assertTrue(update_check._is_newer("v1.9.7"))
        self.assertTrue(update_check._is_newer("v1.10.0"))
        self.assertFalse(update_check._is_newer("v1.9.6"))
        self.assertFalse(update_check._is_newer("v1.9.5"))
        self.assertFalse(update_check._is_newer("1.9.6"))

    # ---- parsing rilis ----
    def test_info_from_release_new(self):
        data = dict(RELEASE_NEW)
        data["assets"] = [dict(a) for a in RELEASE_NEW["assets"]]
        data["assets"][0]["browser_download_url"] = "http://x/ConvTool.exe"
        info = update_check._info_from_release(data)
        self.assertIsNotNone(info)
        self.assertEqual(info["version_text"], "1.9.7")
        self.assertEqual(info["download_url"], "http://x/ConvTool.exe")
        self.assertEqual(info["size"], 1234)
        self.assertIn("Perbaikan A", info["notes"])

    def test_info_from_release_old(self):
        self.assertIsNone(update_check._info_from_release(RELEASE_OLD))

    def test_info_from_release_no_exe(self):
        self.assertIsNone(update_check._info_from_release(RELEASE_NO_EXE))

    def test_info_from_release_malformed(self):
        self.assertIsNone(update_check._info_from_release(None))
        self.assertIsNone(update_check._info_from_release({}))

    # ---- check_now + state ----
    def test_check_now_finds_update(self):
        info, err = update_check.check_now()
        self.assertFalse(err)
        self.assertIsNotNone(info)
        self.assertEqual(info["version_text"], "1.9.7")
        self.assertEqual(Handler.hits, 1)

    def test_check_now_once_a_day(self):
        info1, _ = update_check.check_now()
        self.assertIsNotNone(info1)
        hits_after_first = Handler.hits
        # Panggilan kedua di hari yang sama: pending dikembalikan
        # tanpa mengambil lagi.
        info2, err2 = update_check.check_now()
        self.assertFalse(err2)
        self.assertEqual(info2["version_text"], "1.9.7")
        self.assertEqual(Handler.hits, hits_after_first)

    def test_check_now_up_to_date(self):
        Handler.mode = "old"
        info, err = update_check.check_now()
        self.assertFalse(err)
        self.assertIsNone(info)

    def test_check_now_bad_json_is_error(self):
        Handler.mode = "badjson"
        info, err = update_check.check_now()
        self.assertTrue(err)
        self.assertIsNone(info)

    def test_check_now_404_is_error(self):
        Handler.mode = "404"
        info, err = update_check.check_now()
        self.assertTrue(err)
        self.assertIsNone(info)

    def test_check_now_timeout_is_error(self):
        Handler.mode = "slow"
        update_check._FETCH_TIMEOUT = 1
        info, err = update_check.check_now()
        self.assertTrue(err)
        self.assertIsNone(info)

    def test_mark_notified_clears_pending(self):
        info, _ = update_check.check_now()
        self.assertIsNotNone(info)
        update_check.mark_notified("1.9.7")
        # Sesudah diberitahukan: pending hilang; cek berikut
        # menghormati sekali-sehari (tidak mengambil lagi).
        hits = Handler.hits
        info2, err2 = update_check.check_now()
        self.assertIsNone(info2)
        self.assertFalse(err2)
        self.assertEqual(Handler.hits, hits)

    def test_force_ignores_daily_interval(self):
        info1, _ = update_check.check_now()
        self.assertIsNotNone(info1)
        Handler.mode = "old"
        info2, err2 = update_check.check_now(force=True)
        self.assertFalse(err2)
        self.assertIsNone(info2)  # force mengambil lagi -> sudah terbaru

    # ---- unduh ----
    def test_download_exe_exact_size(self):
        dest = os.path.join(WORK, "ConvTool.exe")
        url = "http://127.0.0.1:%d/exe" % self.port
        self.assertTrue(update_check.download_exe(url, dest, 1234))
        self.assertEqual(os.path.getsize(dest), 1234)

    def test_download_exe_truncated(self):
        Handler.exe_bytes = b"X" * 100  # server kirim lebih pendek
        dest = os.path.join(WORK, "ConvTool.exe")
        url = "http://127.0.0.1:%d/exe" % self.port
        self.assertFalse(update_check.download_exe(url, dest, 1234))

    def test_download_exe_404(self):
        dest = os.path.join(WORK, "ConvTool.exe")
        url = "http://127.0.0.1:%d/tidak-ada" % self.port
        self.assertFalse(update_check.download_exe(url, dest, 1234))

    # ---- updater ----
    def test_updater_script_content(self):
        script = update_check.build_updater_script(
            r"C:\Tools\ConvTool\ConvTool.exe",
            r"C:\Users\arief\AppData\Local\Temp\ConvTool-update\ConvTool.exe",
            1234)
        self.assertIn(r"C:\Tools\ConvTool\ConvTool.exe", script)
        self.assertIn("ConvTool-update", script)
        self.assertIn("Wait-Process", script)
        self.assertIn("RunAs", script)  # fallback UAC
        self.assertNotIn("__TARGET__", script)
        self.assertNotIn("__NEW__", script)

    def test_launch_updater_not_windows(self):
        self.assertFalse(update_check.launch_updater(
            "x.ps1", "a.exe", "b.exe", 1))

    # ---- cek latar ----
    def test_background_check_fills_pending(self):
        update_check.start_background_check()
        for _ in range(50):
            if update_check._PENDING is not None:
                break
            import time
            time.sleep(0.1)
        info = update_check.take_pending()
        self.assertIsNotNone(info)
        self.assertEqual(info["version_text"], "1.9.7")
        self.assertIsNone(update_check.take_pending())


if __name__ == "__main__":
    unittest.main(verbosity=1)
