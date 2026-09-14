"""Loopback-only desktop UI backend with settings, models and a persistent queue."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import multiprocessing
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from urllib.parse import urlparse

from importer import PROJECT, STATE, VERSION, XHS_BROWSER
from model_manager import ModelManager
from settings import MODEL_REPOS, SettingsStore
from task_manager import TaskManager


def _choose_folder():
    script = 'POSIX path of (choose folder with prompt "选择资料保存文件夹")'
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if completed.returncode:
        raise ValueError("没有选择文件夹。")
    return completed.stdout.strip().rstrip("/")


def _choose_media_files():
    script = """
set chosenFiles to choose file with prompt "选择本地音视频" with multiple selections allowed
set output to ""
repeat with chosenFile in chosenFiles
  set output to output & POSIX path of chosenFile & linefeed
end repeat
return output
"""
    completed = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if completed.returncode:
        raise ValueError("没有选择文件。")
    return [line for line in completed.stdout.splitlines() if line]


def serve(output=None, port=18761, state=STATE):
    state = Path(state).expanduser()
    state.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_CACHE"] = str(state / "models" / "huggingface")
    token = secrets.token_urlsafe(32)
    settings_store = SettingsStore(state)
    model_manager = ModelManager(state)
    task_manager = TaskManager(state)
    login_process = [None]
    model_state = {"running": False, "mode": None, "error": None}
    model_lock = threading.Lock()

    def effective_settings():
        if output:
            return {
                "library_root": str(Path(output).expanduser()),
                "platform_folders": None,
                "model_mode": "standard",
                "model_repo": MODEL_REPOS["standard"],
                "delete_temp_media": True,
                "xhs_profile": str(state / "xhs-chrome-profile"),
            }
        return settings_store.load()

    def status_payload():
        setup = settings_store.status() if not output else {
            "configured": True,
            "settings": effective_settings(),
            "legacy_detected": False,
            "legacy_library_root": None,
        }
        with model_lock:
            download = dict(model_state)
        if download["running"] and download["mode"] in MODEL_REPOS:
            downloaded = model_manager.cache_size()
            estimated = model_manager.status()[download["mode"]]["estimated_bytes"]
            download.update(
                downloaded_bytes=downloaded,
                progress=min(0.99, downloaded / estimated) if estimated else 0,
            )
        return {
            **task_manager.status(),
            "output_dir": (setup.get("settings") or {}).get("library_root"),
            "setup": setup,
            "models": model_manager.status(),
            "model_download": download,
            "chrome_available": XHS_BROWSER.is_file(),
        }

    def install_model(mode):
        try:
            model_manager.install(mode)
            with model_lock:
                model_state.update(running=False, error=None)
        except Exception as exc:
            with model_lock:
                model_state.update(running=False, error=str(exc))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, value, content_type="application/json; charset=utf-8"):
            body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            return (
                self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                and secrets.compare_digest(self.headers.get("X-Importer-Token", ""), token)
            )

        def do_GET(self):
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                return self.reply(403, {"error": "Forbidden host"})
            path = urlparse(self.path).path
            if path == "/":
                return self.reply(200, (PROJECT / "index.html").read_bytes(), "text/html; charset=utf-8")
            if not self.authorized():
                return self.reply(403, {"error": "请从应用重新打开窗口。"})
            if path == "/api/status":
                return self.reply(200, status_payload())
            if path == "/api/health":
                return self.reply(200, {"app": "Creator Source Importer", "version": VERSION})
            return self.reply(404, {"error": "Not found"})

        def do_POST(self):
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self.authorized() or self.headers.get("Origin", expected_origin) != expected_origin:
                return self.reply(403, {"error": "Forbidden"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 200000:
                    raise ValueError("请求过大或为空。")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("请求格式无效。")

                if self.path == "/api/choose-folder":
                    return self.reply(200, {"path": _choose_folder()})
                if self.path == "/api/choose-media":
                    return self.reply(200, {"paths": _choose_media_files()})
                if self.path == "/api/settings/save":
                    configured = settings_store.save(
                        body.get("library_root", ""), body.get("model_mode", "standard")
                    )
                    return self.reply(200, {"ok": True, "settings": configured})
                if self.path == "/api/settings/migrate":
                    configured = settings_store.migrate_legacy()
                    model_manager.adopt_legacy_cache(configured["model_mode"])
                    return self.reply(200, {"ok": True, "settings": configured})
                if self.path == "/api/settings/rollback":
                    configured = settings_store.rollback()
                    return self.reply(200, {"ok": True, "settings": configured})
                if self.path == "/api/model/install":
                    mode = body.get("mode")
                    if mode not in MODEL_REPOS:
                        raise ValueError("转录模式无效。")
                    with model_lock:
                        if model_state["running"]:
                            return self.reply(409, {"error": "已有模型正在下载。"})
                        model_state.update(running=True, mode=mode, error=None)
                    threading.Thread(target=install_model, args=(mode,), daemon=True).start()
                    return self.reply(202, {"ok": True})
                if self.path == "/api/model/delete":
                    if task_manager.status()["running"]:
                        return self.reply(409, {"error": "请等待当前任务完成后再删除模型。"})
                    return self.reply(200, {"ok": model_manager.delete(body.get("mode"))})

                settings = effective_settings()
                if self.path == "/api/open-folder":
                    if not settings:
                        raise ValueError("请先完成首次设置。")
                    subprocess.run(["open", settings["library_root"]], check=True)
                    return self.reply(200, {"ok": True})
                if self.path == "/api/xhs-login":
                    if not settings:
                        raise ValueError("请先完成首次设置。")
                    if not XHS_BROWSER.is_file():
                        raise ValueError("小某书实验功能需要系统中已安装 Google Chrome。")
                    if task_manager.status()["running"]:
                        return self.reply(409, {"error": "请等待当前任务完成后再登录小某书。"})
                    process = login_process[0]
                    if process and process.poll() is None:
                        return self.reply(200, {"ok": True, "message": "小某书登录窗口已经打开。"})
                    with (state / "xhs-login.log").open("a") as log:
                        if getattr(sys, "frozen", False):
                            command = [
                                sys.executable, "--xhs-login-worker",
                                "--profile", settings["xhs_profile"],
                            ]
                        else:
                            command = [
                                sys.executable, str(PROJECT / "xhs_login.py"),
                                "--profile", settings["xhs_profile"],
                            ]
                        login_process[0] = subprocess.Popen(
                            command,
                            stdout=log, stderr=log, start_new_session=True
                        )
                    return self.reply(200, {"ok": True, "message": "已打开小某书专用登录窗口。"})
                if self.path == "/api/cancel":
                    return self.reply(200, {"ok": task_manager.cancel()})
                if self.path == "/api/quit":
                    if task_manager.status()["running"]:
                        return self.reply(409, {"error": "请先取消或等待当前任务完成。"})
                    self.reply(200, {"ok": True})
                    threading.Thread(target=self.server.shutdown).start()
                    return
                if self.path != "/api/start":
                    return self.reply(404, {"error": "Not found"})
                if not settings:
                    raise ValueError("请先完成首次设置。")
                values = body.get("inputs") if "inputs" in body else body.get("urls")
                if (
                    not isinstance(values, list)
                    or not 1 <= len(values) <= 100
                    or any(not isinstance(value, str) or not value.strip() or len(value) > 4096 for value in values)
                ):
                    raise ValueError("每批请输入 1–100 条链接或本地文件。")
                language = body.get("language", "auto")
                if language not in {"auto", "zh", "en", "ja", "ko"}:
                    raise ValueError("转录语言无效。")
                if "model" in body and body["model"] not in {"standard", "high_quality"}:
                    raise ValueError("转录模式无效。")
                keep_audio = body.get("keep_audio", not settings.get("delete_temp_media", True))
                if not isinstance(keep_audio, bool):
                    raise ValueError("临时媒体选项无效。")
                mode = settings["model_mode"]
                installed_models = model_manager.installed()
                if not output and mode not in installed_models:
                    return self.reply(409, {"error": "请先下载所选的本地语音识别模型。"})
                if mode in installed_models:
                    os.environ["CSI_MODEL_OVERRIDE"] = installed_models[mode]["path"]
                task_manager.start(
                    [value.strip() for value in values],
                    output=settings["library_root"],
                    model=settings["model_repo"],
                    language=language,
                    keep_audio=keep_audio,
                    state=state,
                    platform_folders=settings.get("platform_folders"),
                    xhs_profile=settings.get("xhs_profile"),
                )
                return self.reply(202, {"ok": True})
            except (ValueError, TypeError, OSError, RuntimeError) as exc:
                return self.reply(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    session = state / "session.json"
    session.write_text(json.dumps({"port": server.server_port, "token": token}))
    session.chmod(0o600)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        session.unlink(missing_ok=True)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--transcribe-worker":
        from transcribe_worker import main as transcribe_main
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        raise SystemExit(transcribe_main())
    if len(sys.argv) > 1 and sys.argv[1] == "--xhs-login-worker":
        from xhs_login import main as xhs_login_main
        login_parser = argparse.ArgumentParser()
        login_parser.add_argument("--profile", type=Path, required=True)
        login_args = login_parser.parse_args(sys.argv[2:])
        raise SystemExit(xhs_login_main(login_args.profile))
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--port", type=int, default=18761)
    parser.add_argument("--state", type=Path, default=STATE)
    args = parser.parse_args()
    serve(args.output, args.port, args.state)
