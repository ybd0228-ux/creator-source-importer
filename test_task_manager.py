import json
from pathlib import Path
import tempfile
import time
import unittest

from task_manager import TaskManager


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)

    def test_running_items_become_interrupted_after_restart(self):
        self.state.mkdir(exist_ok=True)
        (self.state / "tasks.json").write_text(json.dumps({
            "running": True,
            "items": [
                {"index": 0, "url": "one", "status": "transcribing", "message": "处理中"},
                {"index": 1, "url": "two", "status": "complete", "message": "完成"},
            ],
            "error": None,
        }))
        status = TaskManager(self.state).status()
        self.assertFalse(status["running"])
        self.assertEqual(status["items"][0]["status"], "interrupted")
        self.assertEqual(status["items"][1]["status"], "complete")

    def test_batch_state_is_persisted(self):
        def runner(values, callback, cancel_check, **_options):
            results = []
            for index, value in enumerate(values):
                item = {"index": index, "url": value, "status": "complete", "message": "已保存"}
                callback(item)
                results.append(item)
            return results
        manager = TaskManager(self.state, runner=runner)
        manager.start(["one", "two"])
        for _ in range(100):
            if not manager.status()["running"]:
                break
            time.sleep(.01)
        status = manager.status()
        self.assertEqual([item["status"] for item in status["items"]], ["complete", "complete"])
        self.assertEqual(json.loads((self.state / "tasks.json").read_text())["items"], status["items"])

    def test_cancel_request_reaches_runner(self):
        entered = __import__("threading").Event()
        def runner(values, callback, cancel_check, **_options):
            entered.set()
            for _ in range(100):
                if cancel_check():
                    return [{"index": 0, "url": values[0], "status": "cancelled", "message": "任务已取消"}]
                time.sleep(.005)
            return []
        manager = TaskManager(self.state, runner=runner)
        manager.start(["one"])
        self.assertTrue(entered.wait(1))
        self.assertTrue(manager.cancel())
        for _ in range(100):
            if not manager.status()["running"]:
                break
            time.sleep(.01)
        self.assertEqual(manager.status()["items"][0]["status"], "cancelled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
