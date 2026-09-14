"""Persistent serial task queue for the desktop application."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading

from importer import run_batch


FINAL_STATES = {"complete", "skipped", "failed", "cancelled", "interrupted"}


class TaskManager:
    def __init__(self, state_dir, runner=run_batch):
        self.state_dir = Path(state_dir).expanduser()
        self.path = self.state_dir / "tasks.json"
        self.runner = runner
        self.lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.data = self._load()
        if self.data.get("running"):
            self.data["running"] = False
            self.data["error"] = "上次任务因应用关闭而中断，可以重新执行。"
            for item in self.data.get("items", []):
                if item.get("status") not in FINAL_STATES:
                    item.update(status="interrupted", message="应用关闭前未完成")
            self._save()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data
        except (OSError, ValueError):
            pass
        return {"running": False, "items": [], "error": None}

    def _save(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    def status(self):
        with self.lock:
            return json.loads(json.dumps(self.data, ensure_ascii=False))

    def _update(self, item):
        with self.lock:
            index = int(item["index"])
            if index < len(self.data["items"]):
                self.data["items"][index] = item
                self._save()

    def start(self, inputs, **options):
        values = [str(value) for value in inputs]
        with self.lock:
            if self.data.get("running"):
                raise RuntimeError("已有任务正在运行，请等待完成。")
            self.cancel_event.clear()
            self.data = {
                "running": True,
                "items": [dict(index=i, url=value, status="queued", message="等待处理")
                          for i, value in enumerate(values)],
                "error": None,
            }
            self._save()
        thread = threading.Thread(target=self._work, args=(values, options), daemon=True)
        thread.start()

    def _work(self, values, options):
        try:
            results = self.runner(values, callback=self._update,
                                  cancel_check=self.cancel_event.is_set, **options)
            with self.lock:
                self.data["items"] = results
        except Exception as exc:
            with self.lock:
                self.data["error"] = str(exc)
        finally:
            with self.lock:
                self.data["running"] = False
                self._save()

    def cancel(self):
        with self.lock:
            if not self.data.get("running"):
                return False
            self.cancel_event.set()
            return True

