"""Test that the .bat launcher starts the server successfully."""

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BAT_PATH = Path(__file__).parent.parent.parent / "cmm-visual-editor.bat"
TEST_PORT = 15560


def test_bat_launches_server():
    """Run the bat file with --no-open and verify the server responds."""
    assert BAT_PATH.is_file(), f"Bat file not found: {BAT_PATH}"

    # Start the bat file as a subprocess with --no-open and a test port
    proc = subprocess.Popen(
        ["cmd", "/c", str(BAT_PATH), "--no-open", "--port", str(TEST_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(BAT_PATH.parent),
    )

    try:
        # Wait for server to start (poll /api/health)
        started = False
        for _ in range(30):
            time.sleep(0.5)
            # Check if process died
            if proc.poll() is not None:
                stdout = proc.stdout.read().decode(errors="replace")
                stderr = proc.stderr.read().decode(errors="replace")
                print(f"  Process exited early with code {proc.returncode}")
                print(f"  stdout: {stdout[:500]}")
                print(f"  stderr: {stderr[:500]}")
                assert False, "Bat process exited before server started"
            try:
                resp = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/api/health", timeout=2)
                data = resp.read().decode()
                if "ok" in data:
                    started = True
                    break
            except Exception:
                continue

        assert started, "Server did not start within 15 seconds"
        print("  PASS: Server started via bat file")

        # Verify /api/auto-open responds
        resp = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/api/auto-open", timeout=2)
        data = resp.read().decode()
        assert "directory" in data, f"Unexpected response: {data}"
        print("  PASS: /api/auto-open endpoint responds")

        # Verify /api/templates responds
        resp = urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/api/templates", timeout=2)
        data = resp.read().decode()
        assert "mod_id" in data, f"Unexpected response: {data}"
        print("  PASS: /api/templates endpoint responds")

        # Shutdown the server
        req = urllib.request.Request(f"http://127.0.0.1:{TEST_PORT}/api/shutdown", method="POST")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass  # connection drops on shutdown

        proc.wait(timeout=10)
        print("  PASS: Server shut down cleanly")

    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    print("Testing bat launcher:")
    test_bat_launches_server()
    print("\nAll bat launcher tests passed!")
