"""Tests for identity-aware port resolution and exclusive binding."""

import builtins
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add src to path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cmm_visual_editor.__main__ import resolve_port
from cmm_visual_editor.server import RequestHandler, create_server

SRC_DIR = str(Path(__file__).parent.parent / "src")


def make_mod_dir(base):
    """Create a fake mod directory with .metadata/metadata.json."""
    meta = Path(base) / ".metadata"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "metadata.json").write_text('{"name": "test"}')
    return str(base)


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


def test_resolve_free_port():
    """A free port is used as-is."""
    assert resolve_port("127.0.0.1", 15570) == ("bind", 15570)
    print("  PASS: test_resolve_free_port")


def test_replace_same_mod():
    """--replace stops a running instance of the same mod and frees its port."""
    port = 15571
    with tempfile.TemporaryDirectory() as tmp:
        mod = make_mod_dir(tmp)
        proc = spawn_editor(port, mod)
        try:
            result = resolve_port("127.0.0.1", port, mod_dir=mod, port_explicit=True, assume_replace=True)
            assert result == ("bind", port), f"Expected bind on {port}, got {result}"
            proc.wait(timeout=10)

            server = create_server("127.0.0.1", port)
            server.server_close()
        finally:
            kill_editor(proc)
    print("  PASS: test_replace_same_mod")


def test_decline_keeps_instance():
    """Answering no at the prompt keeps the running instance and attaches to it."""
    port = 15572
    with tempfile.TemporaryDirectory() as tmp:
        mod = make_mod_dir(tmp)
        proc = spawn_editor(port, mod)
        real_input = builtins.input
        builtins.input = lambda *a: "n"
        try:
            result = resolve_port("127.0.0.1", port, mod_dir=mod, port_explicit=True)
            assert result == ("attach", port), f"Expected attach on {port}, got {result}"
            assert proc.poll() is None, "running instance was killed despite declining"
        finally:
            builtins.input = real_input
            kill_editor(proc)
    print("  PASS: test_decline_keeps_instance")


def test_confirm_replaces_instance():
    """Answering yes at the prompt replaces the running instance."""
    port = 15573
    with tempfile.TemporaryDirectory() as tmp:
        mod = make_mod_dir(tmp)
        proc = spawn_editor(port, mod)
        real_input = builtins.input
        builtins.input = lambda *a: "y"
        try:
            result = resolve_port("127.0.0.1", port, mod_dir=mod, port_explicit=True)
            assert result == ("bind", port), f"Expected bind on {port}, got {result}"
            proc.wait(timeout=10)
        finally:
            builtins.input = real_input
            kill_editor(proc)
    print("  PASS: test_confirm_replaces_instance")


def test_hop_different_mod():
    """An editor for a different mod is left running; the launch moves to the next free port."""
    port = 15574
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        mod_a = make_mod_dir(tmp_a)
        proc = spawn_editor(port, mod_a)
        try:
            result = resolve_port("127.0.0.1", port, mod_dir=tmp_b)
            assert result == ("bind", port + 1), f"Expected bind on {port + 1}, got {result}"
            assert proc.poll() is None, "other mod's instance was killed"
        finally:
            kill_editor(proc)
    print("  PASS: test_hop_different_mod")


def test_generic_launch_hops():
    """A launch with no mod context coexists with a running instance."""
    port = 15577
    with tempfile.TemporaryDirectory() as tmp:
        proc = spawn_editor(port, tmp)
        try:
            result = resolve_port("127.0.0.1", port)
            assert result == ("bind", port + 1), f"Expected bind on {port + 1}, got {result}"
            assert proc.poll() is None, "running instance was killed"
        finally:
            kill_editor(proc)
    print("  PASS: test_generic_launch_hops")


def test_explicit_port_other_editor_errors():
    """An explicit --port held by a different editor causes exit 1 instead of a hop."""
    port = 15579
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        proc = spawn_editor(port, tmp_a)
        try:
            code = None
            try:
                resolve_port("127.0.0.1", port, mod_dir=tmp_b, port_explicit=True)
            except SystemExit as e:
                code = e.code
            assert code == 1, f"Expected exit code 1, got {code}"
            assert proc.poll() is None, "running instance was killed"
        finally:
            kill_editor(proc)
    print("  PASS: test_explicit_port_other_editor_errors")


def test_foreign_http_server():
    """A non-editor HTTP server on the port causes exit 1 and is left running."""
    port = 15584

    class ForeignHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"hello"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", port), ForeignHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        code = None
        try:
            resolve_port("127.0.0.1", port)
        except SystemExit as e:
            code = e.code
        assert code == 1, f"Expected exit code 1, got {code}"
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
    finally:
        server.shutdown()
        server.server_close()
    print("  PASS: test_foreign_http_server")


def test_unresponsive_port():
    """A port that accepts but never answers causes exit 1."""
    port = 15585
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    try:
        code = None
        try:
            resolve_port("127.0.0.1", port, port_explicit=True)
        except SystemExit as e:
            code = e.code
        assert code == 1, f"Expected exit code 1, got {code}"
    finally:
        sock.close()
    print("  PASS: test_unresponsive_port")


def test_double_bind_fails_loudly():
    """Binding the port twice raises instead of silently succeeding."""
    port = 15586
    first = create_server("127.0.0.1", port)
    try:
        err = None
        try:
            second = create_server("127.0.0.1", port)
            second.server_close()
        except OSError as e:
            err = e
        assert err is not None, "second bind unexpectedly succeeded"
        if sys.platform == "win32":
            assert getattr(err, "winerror", None) == 10048, f"Unexpected error: {err}"
    finally:
        first.server_close()
    print("  PASS: test_double_bind_fails_loudly")


def test_reuseaddr_bind_cannot_steal():
    """An old-style SO_REUSEADDR bind cannot take the new server's port."""
    if sys.platform != "win32":
        print("  SKIP: test_reuseaddr_bind_cannot_steal (Windows-only)")
        return
    port = 15587
    first = create_server("127.0.0.1", port)
    try:
        err = None
        try:
            old = HTTPServer(("127.0.0.1", port), RequestHandler)
            old.server_close()
        except OSError as e:
            err = e
        assert err is not None, "old-style bind unexpectedly succeeded"
        assert getattr(err, "winerror", None) in (10013, 10048), f"Unexpected error: {err}"
    finally:
        first.server_close()
    print("  PASS: test_reuseaddr_bind_cannot_steal")


if __name__ == "__main__":
    print("Testing port resolution:")
    test_resolve_free_port()
    test_replace_same_mod()
    test_decline_keeps_instance()
    test_confirm_replaces_instance()
    test_hop_different_mod()
    test_generic_launch_hops()
    test_explicit_port_other_editor_errors()
    test_foreign_http_server()
    test_unresponsive_port()

    print("\nTesting exclusive binding:")
    test_double_bind_fails_loudly()
    test_reuseaddr_bind_cannot_steal()

    print("\nAll port resolution tests passed!")
