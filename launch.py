"""Double-click launcher: reuse the local server, no Terminal window required."""
import fcntl
import json
import subprocess
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler

from importer import PROJECT, STATE, VERSION


def session_url():
    try:
        session = json.loads((STATE / "session.json").read_text())
        base = f"http://127.0.0.1:{session['port']}"
        req = Request(base + "/api/health", headers={"X-Importer-Token": session["token"]})
        with build_opener(ProxyHandler({})).open(req, timeout=1) as response:
            health = json.load(response)
            if health.get("app") == "Creator Source Importer" and health.get("version") == VERSION:
                return base + "/#token=" + session["token"]
    except (OSError, ValueError, KeyError):
        return None


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "launcher.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        url = session_url()
        if not url:
            with (STATE / "server.log").open("a") as log:
                process = subprocess.Popen([sys.executable, str(PROJECT / "app.py"), "--port", "0"],
                                           stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                           start_new_session=True, cwd=PROJECT)
            for _ in range(60):
                url = session_url()
                if url:
                    break
                if process.poll() is not None:
                    break
                time.sleep(.25)
            if not url:
                raise RuntimeError(f"工具未能启动，请查看 {STATE / 'server.log'}")
    subprocess.run(["open", url], check=True)


if __name__ == "__main__":
    main()
