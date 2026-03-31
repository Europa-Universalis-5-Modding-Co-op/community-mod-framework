"""Tests for auto-open mod directory detection and /api/auto-open endpoint."""

import json
import os
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

# Add src to path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cmm_visual_editor.__main__ import find_mod_directory
from cmm_visual_editor.server import run_server


def make_mod_dir(base, name="mymod"):
    """Create a fake mod directory with .metadata/metadata.json."""
    mod = Path(base) / name
    meta = mod / ".metadata"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "metadata.json").write_text('{"name": "test"}')
    return mod


# ── find_mod_directory tests ──────────────────────────────────────

def test_cwd_is_mod():
    """When CWD itself is a mod folder, it should be detected."""
    with tempfile.TemporaryDirectory() as tmp:
        mod = make_mod_dir(tmp, ".")  # put .metadata directly in tmp
        # Actually create .metadata in tmp directly
        meta = Path(tmp) / ".metadata"
        meta.mkdir(exist_ok=True)
        (meta / "metadata.json").write_text('{"name": "test"}')

        result = find_mod_directory(start=tmp)
        assert result == str(Path(tmp)), f"Expected {tmp}, got {result}"
    print("  PASS: test_cwd_is_mod")


def test_parent_is_mod():
    """When CWD is one level below a mod folder (e.g. in a subfolder)."""
    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp) / ".metadata"
        meta.mkdir(exist_ok=True)
        (meta / "metadata.json").write_text('{"name": "test"}')

        subdir = Path(tmp) / "some_subfolder"
        subdir.mkdir()

        result = find_mod_directory(start=str(subdir))
        assert result == str(Path(tmp)), f"Expected {tmp}, got {result}"
    print("  PASS: test_parent_is_mod")


def test_child_is_mod():
    """When CWD contains a child directory that is a mod folder."""
    with tempfile.TemporaryDirectory() as tmp:
        make_mod_dir(tmp, "my_cool_mod")

        result = find_mod_directory(start=tmp)
        expected = str(Path(tmp) / "my_cool_mod")
        assert result == expected, f"Expected {expected}, got {result}"
    print("  PASS: test_child_is_mod")


def test_no_mod_found():
    """When no mod folder exists nearby, should return None."""
    with tempfile.TemporaryDirectory() as tmp:
        result = find_mod_directory(start=tmp)
        assert result is None, f"Expected None, got {result}"
    print("  PASS: test_no_mod_found")


def test_metadata_dir_without_json():
    """A .metadata dir without metadata.json should not count."""
    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp) / ".metadata"
        meta.mkdir()
        # No metadata.json inside

        result = find_mod_directory(start=tmp)
        assert result is None, f"Expected None, got {result}"
    print("  PASS: test_metadata_dir_without_json")


def test_prefers_cwd_over_child():
    """If CWD itself is a mod AND a child is also a mod, CWD should win."""
    with tempfile.TemporaryDirectory() as tmp:
        # CWD is a mod
        meta = Path(tmp) / ".metadata"
        meta.mkdir()
        (meta / "metadata.json").write_text('{"name": "parent"}')

        # Child is also a mod
        make_mod_dir(tmp, "child_mod")

        result = find_mod_directory(start=tmp)
        assert result == str(Path(tmp)), f"Expected {tmp} (CWD), got {result}"
    print("  PASS: test_prefers_cwd_over_child")


def test_grandparent_is_mod():
    """When CWD is two levels below a mod folder (e.g. tools/cmm-visual-editor)."""
    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp) / ".metadata"
        meta.mkdir(exist_ok=True)
        (meta / "metadata.json").write_text('{"name": "test"}')

        deep = Path(tmp) / "tools" / "cmm-visual-editor"
        deep.mkdir(parents=True)

        result = find_mod_directory(start=str(deep))
        assert result == str(Path(tmp)), f"Expected {tmp}, got {result}"
    print("  PASS: test_grandparent_is_mod")


def test_three_levels_up():
    """When CWD is three levels below a mod folder."""
    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp) / ".metadata"
        meta.mkdir(exist_ok=True)
        (meta / "metadata.json").write_text('{"name": "test"}')

        deep = Path(tmp) / "a" / "b" / "c"
        deep.mkdir(parents=True)

        result = find_mod_directory(start=str(deep))
        assert result == str(Path(tmp)), f"Expected {tmp}, got {result}"
    print("  PASS: test_three_levels_up")


def test_four_levels_up_not_found():
    """Four levels up should NOT be detected (limit is 3)."""
    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp) / ".metadata"
        meta.mkdir(exist_ok=True)
        (meta / "metadata.json").write_text('{"name": "test"}')

        deep = Path(tmp) / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)

        result = find_mod_directory(start=str(deep))
        assert result is None, f"Expected None, got {result}"
    print("  PASS: test_four_levels_up_not_found")


def test_prefers_cwd_over_parent():
    """If both CWD and parent are mods, CWD should win."""
    with tempfile.TemporaryDirectory() as tmp:
        # Parent is a mod
        meta_parent = Path(tmp) / ".metadata"
        meta_parent.mkdir()
        (meta_parent / "metadata.json").write_text('{"name": "parent"}')

        # CWD (child) is also a mod
        child = Path(tmp) / "child"
        child.mkdir()
        meta_child = child / ".metadata"
        meta_child.mkdir()
        (meta_child / "metadata.json").write_text('{"name": "child"}')

        result = find_mod_directory(start=str(child))
        assert result == str(child), f"Expected {child} (CWD), got {result}"
    print("  PASS: test_prefers_cwd_over_parent")


# ── /api/auto-open endpoint test ──────────────────────────────────

def test_api_auto_open_with_dir():
    """Server should return the auto_open_dir via /api/auto-open."""
    port = 15551
    server_ready = threading.Event()

    def start():
        from http.server import HTTPServer
        from cmm_visual_editor.server import RequestHandler
        srv = HTTPServer(("127.0.0.1", port), RequestHandler)
        srv.auto_open_dir = "/fake/mod/path"
        server_ready.set()
        srv.handle_request()  # handle one request then stop

    t = threading.Thread(target=start, daemon=True)
    t.start()
    server_ready.wait(timeout=5)

    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/auto-open")
    data = json.loads(resp.read())
    assert data["directory"] == "/fake/mod/path", f"Expected /fake/mod/path, got {data}"
    print("  PASS: test_api_auto_open_with_dir")


def test_api_auto_open_without_dir():
    """Server should return empty string when no mod detected."""
    port = 15552
    server_ready = threading.Event()

    def start():
        from http.server import HTTPServer
        from cmm_visual_editor.server import RequestHandler
        srv = HTTPServer(("127.0.0.1", port), RequestHandler)
        srv.auto_open_dir = None
        server_ready.set()
        srv.handle_request()

    t = threading.Thread(target=start, daemon=True)
    t.start()
    server_ready.wait(timeout=5)

    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/auto-open")
    data = json.loads(resp.read())
    assert data["directory"] == "", f"Expected empty string, got {data}"
    print("  PASS: test_api_auto_open_without_dir")


if __name__ == "__main__":
    print("Testing find_mod_directory():")
    test_cwd_is_mod()
    test_parent_is_mod()
    test_grandparent_is_mod()
    test_three_levels_up()
    test_four_levels_up_not_found()
    test_child_is_mod()
    test_no_mod_found()
    test_metadata_dir_without_json()
    test_prefers_cwd_over_child()
    test_prefers_cwd_over_parent()

    print("\nTesting /api/auto-open endpoint:")
    test_api_auto_open_with_dir()
    test_api_auto_open_without_dir()

    print("\nAll tests passed!")
