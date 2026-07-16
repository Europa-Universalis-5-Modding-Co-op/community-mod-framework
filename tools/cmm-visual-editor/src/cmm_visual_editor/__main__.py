import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from .server import create_server, serve

PORT_SCAN_COUNT = 20


def find_mod_directory(start=None):
    """Check start dir (default CWD), ancestors (up to 3 levels), and immediate children for a mod folder (.metadata/metadata.json)."""
    cwd = Path(start) if start else Path.cwd()

    # Check CWD itself
    if (cwd / ".metadata" / "metadata.json").is_file():
        return str(cwd)

    # Walk up ancestors (up to 3 levels)
    ancestor = cwd
    for _ in range(3):
        ancestor = ancestor.parent
        if ancestor == ancestor.parent:
            break  # reached filesystem root
        if (ancestor / ".metadata" / "metadata.json").is_file():
            return str(ancestor)

    # Check immediate children
    try:
        for child in cwd.iterdir():
            if child.is_dir() and (child / ".metadata" / "metadata.json").is_file():
                return str(child)
    except PermissionError:
        pass

    return None


def get_version():
    """Get installed package version."""
    from importlib.metadata import version, PackageNotFoundError
    try:
        return version("cmm-visual-editor")
    except PackageNotFoundError:
        return "unknown"


def _exit_port_error(port, problem):
    print(f"ERROR: Port {port} is {problem}.", file=sys.stderr)
    print(f"Close whatever is using port {port} or run with --port <number>.", file=sys.stderr)
    sys.exit(1)


def _port_is_free(probe_host, port):
    # Bind probe instead of a TCP connect: a refused localhost connect on Windows only surfaces after winsock's SYN retries.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind((probe_host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _probe_editor(opener, probe_host, port):
    """Classify what holds the port: ("editor", launch_dir), ("foreign", None), or ("unresponsive", None)."""
    try:
        with opener.open(f"http://{probe_host}:{port}/api/auto-open", timeout=2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if isinstance(body, dict) and "directory" in body:
            return "editor", body.get("directory") or ""
        return "foreign", None
    except socket.timeout:
        return "unresponsive", None
    except urllib.error.HTTPError:
        return "foreign", None
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
            return "unresponsive", None
        return "foreign", None
    except (ValueError, OSError):
        return "foreign", None


def _same_mod(a, b):
    if not a or not b:
        return False
    try:
        return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))
    except OSError:
        return False


def _shutdown_and_wait(opener, probe_host, port):
    try:
        req = urllib.request.Request(f"http://{probe_host}:{port}/api/shutdown", data=b"", method="POST")
        opener.open(req, timeout=3).close()
    except OSError:
        pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _port_is_free(probe_host, port):
            return True
        time.sleep(0.25)
    return False


def _replace_or_attach(opener, probe_host, port, assume_replace):
    if not assume_replace:
        print(f"The editor for this mod is already running on port {port}.")
        try:
            answer = input("Replace the running instance? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print(f"Keeping the running instance on port {port}.")
            return "attach", port
    if _shutdown_and_wait(opener, probe_host, port):
        print(f"Stopped previous editor instance on port {port}.")
        return "bind", port
    _exit_port_error(port, "still in use after asking the previous instance to stop")


def resolve_port(host, port, mod_dir=None, port_explicit=False, assume_replace=False):
    """Pick the port to serve on. A running instance of the same mod is replaced (after confirming) or kept; editors for other mods are left running by moving to the next free port; anything else holding the port is a clear error."""
    probe_host = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    if port_explicit:
        if _port_is_free(probe_host, port):
            return "bind", port
        kind, holder = _probe_editor(opener, probe_host, port)
        if kind == "editor":
            if _same_mod(holder, mod_dir):
                return _replace_or_attach(opener, probe_host, port, assume_replace)
            _exit_port_error(port, "in use by another editor instance")
        if kind == "unresponsive":
            _exit_port_error(port, "in use but not responding (possibly a stuck editor or another application)")
        _exit_port_error(port, "in use by another application")

    statuses = {}
    for p in range(port, port + PORT_SCAN_COUNT):
        if _port_is_free(probe_host, p):
            statuses[p] = ("free", None)
        else:
            kind, holder = _probe_editor(opener, probe_host, p)
            statuses[p] = (kind, holder)
            if kind == "editor" and _same_mod(holder, mod_dir):
                return _replace_or_attach(opener, probe_host, p, assume_replace)

    if statuses[port][0] == "free":
        return "bind", port

    base_kind, base_holder = statuses[port]
    if base_kind == "unresponsive":
        _exit_port_error(port, "in use but not responding (possibly a stuck editor or another application)")
    if base_kind == "foreign":
        _exit_port_error(port, "in use by another application")

    free_ports = [p for p, (kind, _) in statuses.items() if kind == "free"]
    if not free_ports:
        _exit_port_error(port, f"in use and no free port was found in {port}-{port + PORT_SCAN_COUNT - 1}")
    hopped = min(free_ports)
    if base_holder:
        print(f"Port {port} is in use by the editor for {base_holder}; using port {hopped} instead.")
    else:
        print(f"Port {port} is in use by another editor instance; using port {hopped} instead.")
    return "bind", hopped


def main():
    parser = argparse.ArgumentParser(description="CMM Visual Editor")
    parser.add_argument(
        "--port", type=int, default=None, help="Port to run the server on (default 5005)"
    )
    parser.add_argument(
        "--no-open", action="store_true", help="Do not auto-open browser"
    )
    parser.add_argument(
        "--replace", action="store_true", help="Replace a running editor instance for this mod without asking"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    args = parser.parse_args()

    if args.version:
        print(get_version())
        return

    mod_dir = find_mod_directory()
    if mod_dir:
        print(f"Detected mod directory: {mod_dir}")

    port_explicit = args.port is not None
    action, port = resolve_port(
        args.host,
        args.port if port_explicit else 5005,
        mod_dir=mod_dir,
        port_explicit=port_explicit,
        assume_replace=args.replace,
    )

    url = f"http://{args.host}:{port}"

    if action == "attach":
        print(f"Using the running editor instance at {url}")
        if not args.no_open:
            webbrowser.open(url)
        return

    try:
        server = create_server(args.host, port, auto_open_dir=mod_dir)
    except OSError as e:
        print(f"ERROR: Could not bind to {args.host}:{port}: {e}", file=sys.stderr)
        print(f"Another application is using port {port}; close it or run with --port <number>.", file=sys.stderr)
        sys.exit(1)

    print(f"CMM Visual Editor running at {url}")
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        webbrowser.open(url)

    serve(server)


if __name__ == "__main__":
    main()
