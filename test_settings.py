import json
from pathlib import Path
import tempfile
import unittest

from settings import DEFAULT_PLATFORM_FOLDERS, LEGACY_PLATFORM_FOLDERS, SettingsStore


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / "Application Support" / "Creator Source Importer"
        self.library = self.base / "含 空格" / "iCloud 资料"
        self.library.mkdir(parents=True)

    def test_new_user_saves_generic_root_and_public_folder_names(self):
        store = SettingsStore(self.state, legacy_config=self.base / "missing.json")
        saved = store.save(self.library, model_mode="standard")
        self.assertEqual(saved["library_root"], str(self.library))
        self.assertEqual(saved["platform_folders"], DEFAULT_PLATFORM_FOLDERS)
        self.assertNotIn("ybd28", json.dumps(saved))
        self.assertEqual(store.load(), saved)

    def test_legacy_config_is_backed_up_and_copied_without_deleting_source(self):
        legacy_root = self.library / "YouTube"
        legacy_root.mkdir()
        legacy = self.base / "legacy" / "config.json"
        legacy.parent.mkdir()
        original = json.dumps({"output_dir": str(legacy_root), "model": "mlx-community/whisper-large-v3-turbo"})
        legacy.write_text(original, encoding="utf-8")
        store = SettingsStore(self.state, legacy_config=legacy)
        info = store.status()
        self.assertFalse(info["configured"])
        self.assertTrue(info["legacy_detected"])
        self.assertEqual(info["legacy_library_root"], str(self.library))
        migrated = store.migrate_legacy()
        self.assertEqual(migrated["library_root"], str(self.library))
        self.assertEqual(migrated["platform_folders"], LEGACY_PLATFORM_FOLDERS)
        self.assertEqual(legacy.read_text(encoding="utf-8"), original)
        backups = list((self.state / "migrations").glob("legacy-config-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)

    def test_reconfigure_creates_rollback_backup(self):
        first = self.base / "first"
        second = self.base / "second"
        first.mkdir(); second.mkdir()
        store = SettingsStore(self.state, legacy_config=self.base / "missing.json")
        original = store.save(first)
        store.save(second)
        restored = store.rollback()
        self.assertEqual(restored["library_root"], original["library_root"])

    def test_invalid_destination_is_rejected(self):
        store = SettingsStore(self.state, legacy_config=self.base / "missing.json")
        for path in [Path("relative"), self.base / "missing"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                store.save(path)

    def test_icloud_style_chinese_and_space_path(self):
        root = self.base / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "知识库" / "外部资料"
        root.mkdir(parents=True)
        data = SettingsStore(self.state, legacy_config=self.base / "missing.json").save(root)
        self.assertEqual(data["library_root"], str(root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
