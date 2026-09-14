"""Versioned user settings and non-destructive migration from the personal build."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile


DEFAULT_PLATFORM_FOLDERS = {
    "youtube": "油管",
    "bilibili": "B站",
    "xiaohongshu": "小某书",
    "local": "本地媒体",
}
LEGACY_PLATFORM_FOLDERS = {
    "youtube": "YouTube",
    "bilibili": "Bilibili",
    "xiaohongshu": "小红书",
    "local": "本地媒体",
}
MODEL_REPOS = {
    "standard": "mlx-community/whisper-large-v3-turbo",
    "high_quality": "mlx-community/whisper-large-v3-mlx",
}


def _stamp():
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")


class SettingsStore:
    def __init__(self, state_dir, legacy_config=None):
        self.state_dir = Path(state_dir).expanduser()
        self.path = self.state_dir / "settings.json"
        self.legacy_config = Path(legacy_config).expanduser() if legacy_config else (
            Path.home() / "Applications/Creator_Source_Importer/config.json"
        )

    def load(self):
        if not self.path.is_file():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise ValueError("设置文件版本无法识别。")
        return data

    def _legacy_data(self):
        if not self.legacy_config.is_file():
            return None
        try:
            data = json.loads(self.legacy_config.read_text(encoding="utf-8"))
            output = Path(data["output_dir"]).expanduser()
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not output.is_absolute() or output.name != "YouTube" or not output.parent.is_dir():
            return None
        return data, output.parent

    def status(self):
        configured = self.load()
        legacy = None if configured else self._legacy_data()
        return {
            "configured": bool(configured),
            "settings": configured,
            "legacy_detected": bool(legacy),
            "legacy_library_root": str(legacy[1]) if legacy else None,
        }

    def _validate_root(self, value):
        root = Path(value).expanduser()
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            raise ValueError("请选择一个已经存在的本地文件夹。")
        if not os.access(root, os.W_OK):
            raise ValueError("所选文件夹没有写入权限。")
        return root

    def _document(self, root, model_mode, platform_folders, migrated_from=None):
        if model_mode not in MODEL_REPOS:
            raise ValueError("转录模式无效。")
        return {
            "schema_version": 1,
            "library_root": str(root),
            "platform_folders": dict(platform_folders),
            "model_mode": model_mode,
            "model_repo": MODEL_REPOS[model_mode],
            "save_raw_json": True,
            "delete_temp_media": True,
            "xiaohongshu_experimental": True,
            "xhs_profile": str(self.state_dir / "xhs-chrome-profile"),
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "migrated_from": str(migrated_from) if migrated_from else None,
        }

    def _write(self, data):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=self.state_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
            self.path.chmod(0o600)
        finally:
            Path(temp_name).unlink(missing_ok=True)
        return data

    def _backup_current(self):
        if not self.path.is_file():
            return None
        folder = self.state_dir / "migrations"
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / f"settings-backup-{_stamp()}.json"
        shutil.copy2(self.path, backup)
        return backup

    def save(self, library_root, model_mode="standard", platform_folders=None):
        root = self._validate_root(library_root)
        self._backup_current()
        data = self._document(root, model_mode, platform_folders or DEFAULT_PLATFORM_FOLDERS)
        return self._write(data)

    def migrate_legacy(self):
        legacy = self._legacy_data()
        if not legacy:
            raise ValueError("没有找到可迁移的旧版配置。")
        data, root = legacy
        folder = self.state_dir / "migrations"
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / f"legacy-config-{_stamp()}.json"
        shutil.copy2(self.legacy_config, backup)
        model_mode = "standard" if data.get("model") == MODEL_REPOS["standard"] else "standard"
        document = self._document(root, model_mode, LEGACY_PLATFORM_FOLDERS, self.legacy_config)
        old_profile = Path.home() / ".xiaohongshu-skill/chrome-profile"
        if old_profile.is_dir():
            document["xhs_profile"] = str(old_profile)
        return self._write(document)

    def rollback(self):
        backups = sorted((self.state_dir / "migrations").glob("settings-backup-*.json"))
        if not backups:
            raise ValueError("没有可回退的设置备份。")
        data = json.loads(backups[-1].read_text(encoding="utf-8"))
        return self._write(data)
