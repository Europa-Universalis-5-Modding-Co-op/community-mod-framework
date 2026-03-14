"""End-to-end test: start server, fetch /api/auto-open, then /api/import."""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cmm_visual_editor.server import run_server
from http.server import HTTPServer
from cmm_visual_editor.server import RequestHandler


def test_e2e_auto_open_and_import():
    """Full flow: server with auto_open_dir → /api/auto-open → /api/import."""
    # Create a fake mod directory with the minimal files the parser expects
    with tempfile.TemporaryDirectory() as tmp:
        mod_dir = Path(tmp) / "testmod"
        mod_dir.mkdir()
        meta = mod_dir / ".metadata"
        meta.mkdir()
        (meta / "metadata.json").write_text(json.dumps({
            "name": "Test Mod",
            "id": "test_mod",
            "version": "1.0",
            "short_description": "A test",
            "tags": ["Utilities"],
            "game_version": "1.1.*",
        }))

        port = 15553
        server = HTTPServer(("127.0.0.1", port), RequestHandler)
        server.auto_open_dir = str(mod_dir)

        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)

        try:
            # Step 1: Check /api/auto-open returns the directory
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/auto-open")
            data = json.loads(resp.read())
            assert data["directory"] == str(mod_dir), f"auto-open: expected {mod_dir}, got {data['directory']}"
            print("  PASS: /api/auto-open returns correct directory")

            # Step 2: Use that directory to call /api/import (like the frontend would)
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/import",
                data=json.dumps({"directory": data["directory"]}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp2 = urllib.request.urlopen(req)
            import_data = json.loads(resp2.read())

            assert "error" not in import_data, f"Import returned error: {import_data.get('error')}"
            print(f"  PASS: /api/import succeeded (mod_id={import_data.get('mod_id', '(empty)')!r})")

            # Step 3: Verify the import data has the metadata
            assert import_data.get("metadata_name") == "Test Mod", \
                f"Expected metadata_name='Test Mod', got {import_data.get('metadata_name')!r}"
            print("  PASS: imported data contains correct metadata")

        finally:
            server.shutdown()

    print("  E2E test passed!")


def test_e2e_no_auto_open():
    """When auto_open_dir is None, frontend should get empty string and skip import."""
    port = 15554
    server = HTTPServer(("127.0.0.1", port), RequestHandler)
    server.auto_open_dir = None

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)

    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/auto-open")
        data = json.loads(resp.read())
        assert data["directory"] == "", f"Expected empty, got {data['directory']!r}"
        print("  PASS: /api/auto-open returns empty when no mod detected")
    finally:
        server.shutdown()


if __name__ == "__main__":
    print("E2E auto-open tests:")
    test_e2e_auto_open_and_import()
    test_e2e_no_auto_open()
    print("\nAll E2E tests passed!")
