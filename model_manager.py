"""Download and manage MLX Whisper models inside the app data directory."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from settings import MODEL_REPOS


MODEL_ESTIMATED_BYTES = {
    "standard": 1_700_000_000,
    "high_quality": 3_200_000_000,
}


class ModelManager:
    def __init__(self, state_dir, downloader=None, disk_usage=shutil.disk_usage):
        self.state_dir = Path(state_dir).expanduser()
        self.cache_dir = self.state_dir / "models" / "huggingface"
        self.manifest_path = self.state_dir / "models" / "installed.json"
        self.downloader = downloader
        self.disk_usage = disk_usage

    def _manifest(self):
        if not self.manifest_path.is_file():
            return {}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_manifest(self, data):
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.manifest_path)

    @staticmethod
    def _valid_snapshot(path):
        path = Path(path)
        return (path / "config.json").is_file() and any(
            (path / name).is_file() and (path / name).stat().st_size > 0
            for name in ("weights.npz", "weights.safetensors")
        )

    def installed(self):
        result = {}
        for mode, entry in self._manifest().items():
            path = Path(entry.get("path", "")) if isinstance(entry, dict) else Path()
            if mode in MODEL_REPOS and self._valid_snapshot(path):
                result[mode] = {**entry, "path": str(path)}
        return result

    def adopt_legacy_cache(self, mode):
        """Reference a complete pre-existing HF cache without copying or deleting it."""
        if mode not in MODEL_REPOS:
            raise ValueError("转录模式无效。")
        repo_cache = (
            Path.home() / ".cache" / "huggingface" / "hub"
            / ("models--" + MODEL_REPOS[mode].replace("/", "--"))
        )
        ref = repo_cache / "refs" / "main"
        try:
            snapshot = repo_cache / "snapshots" / ref.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not self._valid_snapshot(snapshot):
            return None
        manifest = self._manifest()
        manifest[mode] = {
            "repo": MODEL_REPOS[mode],
            "path": str(snapshot),
            "managed": False,
        }
        self._write_manifest(manifest)
        return manifest[mode]

    def status(self):
        installed = self.installed()
        return {
            mode: {
                "repo": repo,
                "estimated_bytes": MODEL_ESTIMATED_BYTES[mode],
                "installed": mode in installed,
                "path": installed.get(mode, {}).get("path"),
            }
            for mode, repo in MODEL_REPOS.items()
        }

    def cache_size(self):
        if not self.cache_dir.is_dir():
            return 0
        total = 0
        for path in self.cache_dir.rglob("*"):
            try:
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
            except OSError:
                continue
        return total

    def install(self, mode):
        if mode not in MODEL_REPOS:
            raise ValueError("转录模式无效。")
        required = MODEL_ESTIMATED_BYTES[mode]
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if self.disk_usage(self.cache_dir).free < required + 1_000_000_000:
            raise RuntimeError("磁盘空间不足，无法下载语音识别模型。")
        downloader = self.downloader
        if downloader is None:
            from huggingface_hub import snapshot_download
            downloader = snapshot_download
        path = Path(downloader(MODEL_REPOS[mode], cache_dir=str(self.cache_dir)))
        if not self._valid_snapshot(path):
            raise RuntimeError("模型下载不完整，请重试。")
        manifest = self._manifest()
        manifest[mode] = {"repo": MODEL_REPOS[mode], "path": str(path), "managed": True}
        self._write_manifest(manifest)
        return manifest[mode]

    def delete(self, mode):
        manifest = self._manifest()
        entry = manifest.pop(mode, None)
        if not entry:
            return False
        path = Path(entry.get("path", ""))
        if entry.get("managed", True):
            try:
                path.relative_to(self.cache_dir)
            except ValueError:
                raise RuntimeError("模型目录不在应用数据目录中，未删除。") from None
            shutil.rmtree(path, ignore_errors=True)
        self._write_manifest(manifest)
        return True
