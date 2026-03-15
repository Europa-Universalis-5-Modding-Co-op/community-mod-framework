import argparse
import webbrowser
from pathlib import Path
from .server import run_server


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
    """Read version from pyproject.toml."""
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    if pyproject.is_file():
        for line in pyproject.read_text().splitlines():
            if line.startswith("version"):
                return line.split('"')[1]
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="CMM Visual Editor")
    parser.add_argument(
        "--port", type=int, default=5005, help="Port to run the server on"
    )
    parser.add_argument(
        "--no-open", action="store_true", help="Do not auto-open browser"
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

    url = f"http://{args.host}:{args.port}"
    print(f"CMM Visual Editor running at {url}")
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        webbrowser.open(url)

    run_server(args.host, args.port, auto_open_dir=mod_dir)


if __name__ == "__main__":
    main()
