"""Download and manage MLX Whisper models inside the app data directory."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import hashlib

import requests

from settings import MODEL_REPOS


MODEL_ESTIMATED_BYTES = {
    "standard": 1_700_000_000,
    "high_quality": 3_200_000_000,
}

# The ModelScope copies match the files used by mlx-whisper on Hugging Face.
# Pin their hashes so a changed upstream model cannot be installed silently.
MODEL_FILES = {
    "standard": {
        "config.json": (268, "b34fc29e4e11e0a25e812775dd67f4dd16fc2c8eb43d28ae25ff7d660ecb6379"),
        "weights.safetensors": (1_613_977_612, "951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6"),
    },
    "high_quality": {
        "config.json": (269, "34982ce6ae286095000f82ae9583b3431639e8b092bf60c961f203745e6500e3"),
        "weights.npz": (3_083_520_416, "05ff791ce3630fae47e7c51004e9666204d786246ec07cac6110af768099b40d"),
    },
}


class ModelDownloadError(RuntimeError):
    pass


class ModelManager:
    def __init__(self, state_dir, downloader=None, disk_usage=shutil.disk_usage,
                 modelscope_base="https://modelscope.cn/models"):
        self.state_dir = Path(state_dir).expanduser()
        self.cache_dir = self.state_dir / "models" / "huggingface"
        self.modelscope_dir = self.state_dir / "models" / "modelscope"
        self.manifest_path = self.state_dir / "models" / "installed.json"
        self.downloader = downloader
        self.disk_usage = disk_usage
        self.modelscope_base = modelscope_base.rstrip("/")

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

    def cache_size(self, mode=None):
        total = 0
        if mode is None:
            directories = (self.cache_dir, self.modelscope_dir)
        else:
            directories = (
                self.cache_dir / ("models--" + MODEL_REPOS[mode].replace("/", "--")),
                self.modelscope_dir / mode,
            )
        for directory in directories:
            if directory.is_dir():
                for path in directory.rglob("*"):
                    try:
                        if path.is_file() and not path.is_symlink():
                            total += path.stat().st_size
                    except OSError:
                        continue
        return total

    @staticmethod
    def _matches(path, size, digest):
        if not path.is_file() or path.stat().st_size != size:
            return False
        hasher = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest() == digest

    def _download_modelscope(self, mode):
        destination = self.modelscope_dir / mode
        destination.mkdir(parents=True, exist_ok=True)
        for filename, (size, digest) in MODEL_FILES[mode].items():
            final = destination / filename
            if self._matches(final, size, digest):
                continue
            partial = destination / (filename + ".part")
            offset = partial.stat().st_size if partial.exists() else 0
            if offset == size and self._matches(partial, size, digest):
                os.replace(partial, final)
                continue
            if offset >= size:
                partial.unlink()
                offset = 0
            url = f"{self.modelscope_base}/{MODEL_REPOS[mode]}/resolve/master/{filename}"
            try:
                with requests.get(url, headers={"Range": f"bytes={offset}-"} if offset else {},
                                  stream=True, timeout=(15, 60)) as response:
                    response.raise_for_status()
                    if offset and response.status_code == 206:
                        if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                            raise ModelDownloadError("下载源返回了错误的续传位置。")
                        write_mode = "ab"
                    elif response.status_code == 200:
                        write_mode = "wb"
                    else:
                        raise ModelDownloadError("下载源未返回可用的模型文件。")
                    with partial.open(write_mode) as output:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                output.write(chunk)
            except requests.RequestException as exc:
                raise ModelDownloadError(f"连接模型源失败：{exc}") from exc
            if partial.stat().st_size < size:
                raise ModelDownloadError("魔搭连接中断，已保留下载进度；请重试。")
            if not self._matches(partial, size, digest):
                partial.unlink(missing_ok=True)
                raise ModelDownloadError("魔搭模型文件大小或 SHA-256 校验失败。")
            os.replace(partial, final)
        return destination

    def install(self, mode):
        if mode not in MODEL_REPOS:
            raise ValueError("转录模式无效。")
        required = MODEL_ESTIMATED_BYTES[mode]
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if self.disk_usage(self.cache_dir).free < required + 1_000_000_000:
            raise RuntimeError("磁盘空间不足，无法下载语音识别模型。")
        if self.downloader is None:
            try:
                path = self._download_modelscope(mode)
            except ModelDownloadError as domestic_error:
                from huggingface_hub import snapshot_download
                try:
                    path = Path(snapshot_download(MODEL_REPOS[mode], cache_dir=str(self.cache_dir)))
                    if not all(self._matches(path / filename, size, digest)
                               for filename, (size, digest) in MODEL_FILES[mode].items()):
                        raise ModelDownloadError("备用模型文件 SHA-256 校验失败。")
                except Exception as international_error:
                    raise RuntimeError(
                        f"魔搭下载失败：{domestic_error}；Hugging Face 备用下载失败：{international_error}"
                    ) from international_error
        else:
            path = Path(self.downloader(MODEL_REPOS[mode], cache_dir=str(self.cache_dir)))
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
            if not any(path.is_relative_to(directory) for directory in
                       (self.cache_dir, self.modelscope_dir)):
                raise RuntimeError("模型目录不在应用数据目录中，未删除。") from None
            shutil.rmtree(path, ignore_errors=True)
        self._write_manifest(manifest)
        return True
