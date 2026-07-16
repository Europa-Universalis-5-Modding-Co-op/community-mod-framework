"""Tests for the browser-tab heartbeat watchdog."""

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# Add src to path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

SRC_DIR = str(Path(__file__).parent.parent / "src")


def spawn_editor(port, cwd):
    """Start a real editor subprocess and wait until it serves."""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC_DIR + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        [sys.executable, "-m", "cmm_visual_editor", "--no-open", "--port", str(port)],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 15
    while True:
        assert proc.poll() is None, "editor exited before serving"
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1).close()
            return proc
        except OSError:
            assert time.monotonic() < deadline, "editor did not start within 15 seconds"
            time.sleep(0.5)


def kill_editor(proc):
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)


def test_orphaned_server_exits():
    """Once a tab has pinged, the server exits when the pings stop."""
    port = 15588
    with tempfile.TemporaryDirectory() as tmp:
        proc = spawn_editor(port, tmp)
        try:
            for _ in range(3):
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/heartbeat", timeout=1).close()
                time.sleep(1)

            deadline = time.monotonic() + 25
            while proc.poll() is None:
                assert time.monotonic() < deadline, "server did not exit after heartbeats stopped"
                time.sleep(1)
            stdout = proc.stdout.read().decode(errors="replace")
            assert "Browser tab closed" in stdout, f"Unexpected stdout: {stdout[:500]}"
        finally:
            kill_editor(proc)
    print("  PASS: test_orphaned_server_exits")


def test_never_opened_server_stays():
    """A server no tab ever pinged keeps running."""
    port = 15589
    with tempfile.TemporaryDirectory() as tmp:
        proc = spawn_editor(port, tmp)
        try:
            time.sleep(16)
            assert proc.poll() is None, "server exited although no tab ever connected"
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1).close()
        finally:
            kill_editor(proc)
    print("  PASS: test_never_opened_server_stays")


if __name__ == "__main__":
    print("Testing heartbeat watchdog:")
    test_orphaned_server_exits()
    test_never_opened_server_stays()

    print("\nAll heartbeat tests passed!")
