from pathlib import Path
from collections import namedtuple
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
from threading import Thread
import unittest
from unittest.mock import Mock, patch

from model_manager import MODEL_ESTIMATED_BYTES, MODEL_FILES, ModelDownloadError, ModelManager


class ModelManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def downloader(self, repo, cache_dir):
        path = Path(cache_dir) / repo.replace("/", "--") / "snapshot"
        path.mkdir(parents=True)
        (path / "config.json").write_text("{}")
        (path / "weights.safetensors").write_bytes(b"synthetic")
        return str(path)

    def test_missing_model_then_install_and_delete(self):
        manager = ModelManager(self.base, downloader=self.downloader)
        self.assertFalse(manager.status()["standard"]["installed"])
        installed = manager.install("standard")
        self.assertTrue(Path(installed["path"]).is_dir())
        self.assertTrue(manager.status()["standard"]["installed"])
        self.assertTrue(manager.delete("standard"))
        self.assertFalse(manager.status()["standard"]["installed"])

    def test_disk_space_is_checked_before_download(self):
        called = Mock()
        Usage = namedtuple("Usage", "total used free")
        usage = lambda _path: Usage(10, 9, MODEL_ESTIMATED_BYTES["standard"])
        manager = ModelManager(self.base, downloader=called, disk_usage=usage)
        with self.assertRaisesRegex(RuntimeError, "磁盘空间不足"):
            manager.install("standard")
        called.assert_not_called()

    def test_incomplete_model_is_rejected(self):
        def incomplete(repo, cache_dir):
            path = Path(cache_dir) / "incomplete"
            path.mkdir(parents=True)
            (path / "config.json").write_text("{}")
            return str(path)
        manager = ModelManager(self.base, downloader=incomplete)
        with self.assertRaisesRegex(RuntimeError, "不完整"):
            manager.install("standard")

    def test_unmanaged_legacy_model_is_unregistered_but_not_deleted(self):
        manager = ModelManager(self.base)
        external = self.base.parent / (self.base.name + "-external")
        self.addCleanup(lambda: __import__("shutil").rmtree(external, ignore_errors=True))
        external.mkdir()
        (external / "config.json").write_text("{}")
        weights = external / "weights.npz"
        weights.write_bytes(b"keep")
        manager._write_manifest({"standard": {
            "repo": "mlx-community/whisper-large-v3-turbo",
            "path": str(external),
            "managed": False,
        }})
        self.assertTrue(manager.delete("standard"))
        self.assertEqual(weights.read_bytes(), b"keep")

    def test_modelscope_download_resumes_and_verifies_same_model(self):
        files = {"config.json": b'{"model_type":"whisper"}', "weights.safetensors": b"model-weights"}
        ranges = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                name = self.path.rsplit("/", 1)[-1]
                data = files[name]
                offset = int(self.headers.get("Range", "bytes=0-")[6:-1])
                ranges.append((name, offset))
                self.send_response(206 if offset else 200)
                self.send_header("Content-Length", str(len(data) - offset))
                if offset:
                    self.send_header("Content-Range", f"bytes {offset}-{len(data)-1}/{len(data)}")
                self.end_headers()
                self.wfile.write(data[offset:])

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        hashes = {name: (len(data), sha256(data).hexdigest()) for name, data in files.items()}
        manager = ModelManager(self.base, modelscope_base=f"http://127.0.0.1:{server.server_port}/models")
        partial = manager.modelscope_dir / "standard" / "weights.safetensors.part"
        partial.parent.mkdir(parents=True)
        partial.write_bytes(files["weights.safetensors"][:5])
        with patch.dict(MODEL_FILES, {"standard": hashes}):
            installed = manager.install("standard")
        self.assertEqual(Path(installed["path"]).joinpath("weights.safetensors").read_bytes(), files["weights.safetensors"])
        self.assertIn(("weights.safetensors", 5), ranges)
        weights = Path(installed["path"]) / "weights.safetensors"
        partial.write_bytes(weights.read_bytes())
        weights.unlink()
        requests_before = len(ranges)
        with patch.dict(MODEL_FILES, {"standard": hashes}):
            manager.install("standard")
        self.assertEqual(len(ranges), requests_before)
        self.assertTrue(manager.delete("standard"))
        self.assertFalse(Path(installed["path"]).exists())

    def test_hugging_face_backup_is_hash_checked(self):
        manager = ModelManager(self.base)
        snapshot = self.base / "models" / "huggingface" / "snapshot"
        snapshot.mkdir(parents=True)
        (snapshot / "config.json").write_bytes(b"config")
        (snapshot / "weights.safetensors").write_bytes(b"wrong")
        hashes = {"config.json": (6, sha256(b"config").hexdigest()),
                  "weights.safetensors": (5, sha256(b"right").hexdigest())}
        with patch.dict(MODEL_FILES, {"standard": hashes}), \
             patch.object(manager, "_download_modelscope", side_effect=ModelDownloadError("不可达")), \
             patch("huggingface_hub.snapshot_download", return_value=str(snapshot)):
            with self.assertRaisesRegex(RuntimeError, "备用模型文件 SHA-256 校验失败"):
                manager.install("standard")
            (snapshot / "weights.safetensors").write_bytes(b"right")
            self.assertTrue(Path(manager.install("standard")["path"]).is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
