"""HTTP boundary tests use a temporary destination, never the real Vault."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from importer import PROJECT


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.process = subprocess.Popen([sys.executable, str(PROJECT / "app.py"), "--port", "0", "--state", str(cls.base / "state"), "--output", str(cls.base / "YouTube")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                cls.session = json.loads((cls.base / "state/session.json").read_text())
                cls.url = f"http://127.0.0.1:{cls.session['port']}"
                break
            except (OSError, ValueError):
                time.sleep(.05)
        else:
            cls.process.terminate()
            raise RuntimeError("Test server failed to start")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.temp.cleanup()

    def request(self, path, data=None, headers=None, token=True):
        h = {"Content-Type": "application/json"}
        if token:
            h["X-Importer-Token"] = self.session["token"]
        h.update(headers or {})
        request = Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers=h)
        try:
            response = build_opener(ProxyHandler({})).open(request, timeout=3)
        except HTTPError as exc:
            response = exc
        return response.status, json.load(response)

    def test_token_required(self):
        self.assertEqual(self.request("/api/status", token=False)[0], 403)
        self.assertEqual(self.request("/api/start", {"urls": ["invalid"]}, token=False)[0], 403)

    def test_health_and_page_show_public_platform_names(self):
        status, data = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["version"], "0.7.1")
        request = Request(self.url + "/")
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            page = response.read().decode()
        self.assertIn("油管", page)
        self.assertIn("B站", page)
        self.assertIn("小某书", page)
        self.assertIn("本地媒体", page)
        self.assertIn("v0.7", page)
        self.assertNotIn("YouTube", page)
        self.assertNotIn("Bilibili", page)
        self.assertNotIn("小红书", page)

    def test_cross_origin_rejected(self):
        self.assertEqual(self.request("/api/start", {"urls": ["invalid"]}, {"Origin": "https://example.org"})[0], 403)

    def test_unexpected_host_rejected(self):
        self.assertEqual(self.request("/api/status", headers={"Host": "attacker.test"})[0], 403)

    def test_bad_inputs_rejected(self):
        for data in [[], {"urls": []}, {"urls": "bad"}, {"urls": ["bad"] * 101}, {"urls": ["bad"], "model": "unknown"}, {"urls": ["bad"], "keep_audio": "false"}]:
            self.assertEqual(self.request("/api/start", data)[0], 400)

    def test_invalid_batch_finishes_and_can_retry(self):
        for _ in range(2):
            self.assertEqual(self.request("/api/start", {"urls": ["invalid", "https://youtube.com/playlist?list=x"]})[0], 202)
            for _ in range(100):
                status, data = self.request("/api/status")
                if not data["running"]:
                    break
                time.sleep(.02)
            self.assertEqual(status, 200)
            self.assertFalse(data["running"])
            self.assertEqual([i["status"] for i in data["items"]], ["failed", "failed"])
        self.assertFalse(list((self.base / "YouTube").rglob("*.md")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
