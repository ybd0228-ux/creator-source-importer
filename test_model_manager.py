from pathlib import Path
from collections import namedtuple
import tempfile
import unittest
from unittest.mock import Mock

from model_manager import MODEL_ESTIMATED_BYTES, ModelManager


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
