"""GUI Update Helper — Track and merge vanilla GUI changes for EU5 mod overrides.

Uses a git orphan branch (gui/vanilla) to store vanilla versions of overridden
type, template, and widget definitions.  When vanilla updates, the branch is
updated and merged into the working branch, letting git do a proper three-way
merge.

Commands:
    init      Set up tracking for this mod
    check     Report which tracked definitions changed in vanilla
    merge     Update vanilla branch and merge changes
    apply     Write resolved tracking files back to mod GUI files
    refresh   Re-extract mod definitions into tracking files
    status    Show tracking status
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

# ─── Constants ────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.toml")

GUI_SOURCES = ["in_game", "main_menu", "loading_screen"]
# Subdirs treated as vanilla extracts (not mod overrides) and skipped.
EXCLUDED_DIRS = {"vanilla"}
TRACKING_DIR_NAME = "tools/dependencies/gui-tracking"
TRACKING_DIR = os.path.join(ROOT_DIR, *TRACKING_DIR_NAME.split("/"))
MANIFEST_PATH = os.path.join(TRACKING_DIR, "manifest.json")
MANIFEST_VERSION = 1
VANILLA_BRANCH = "gui/vanilla"

STEAM_GAME_PATHS = [
    os.path.join("C:" + os.sep, "Steam", "steamapps", "common",
                 "Europa Universalis V", "game"),
    os.path.join("C:" + os.sep, "Program Files (x86)", "Steam", "steamapps",
                 "common", "Europa Universalis V", "game"),
    os.path.join("C:" + os.sep, "Program Files", "Steam", "steamapps",
                 "common", "Europa Universalis V", "game"),
]

# ─── Regex (used with .match() on lstripped lines) ───────────────────────────

_TYPES_BLOCK_RE = re.compile(r"types\s+(\w+)\s*(\{)?\s*(?:#.*)?$")
_TYPE_DEF_RE = re.compile(r"type\s+(\w+)\s*=\s*(\w+)\s*(\{)?\s*(?:#.*)?$")
_TEMPLATE_RE = re.compile(r"template\s+(\w+)\s*(\{)?\s*(?:#.*)?$")
# Top-level widget instances: "window = {", "lateralview = {", etc.
# Only matched on lines with NO leading whitespace (top-level).
_WIDGET_INSTANCE_RE = re.compile(r"(\w+)\s*=\s*(\{)?\s*(?:#.*)?$")
_NAME_PROP_RE = re.compile(r'name\s*=\s*"([^"]+)"')

# ─── Data Structures ─────────────────────────────────────────────────────────

class GuiDefinition:
    """A single extracted type or template definition."""

    __slots__ = (
        "name", "kind", "namespace", "base_widget",
        "text", "source_file", "start_line", "end_line",
    )

    def __init__(self, name, kind, namespace, base_widget,
                 text, source_file, start_line, end_line):
        self.name = name
        self.kind = kind                # "type" or "template"
        self.namespace = namespace      # types-block name; None for templates
        self.base_widget = base_widget  # RHS of '='; None for templates
        self.text = text                # exact extracted text
        self.source_file = source_file  # relative path from base_dir
        self.start_line = start_line    # 0-indexed
        self.end_line = end_line        # 0-indexed, inclusive

# ─── GUI Parser ──────────────────────────────────────────────────────────────

def _strip_comment(line):
    """Remove ``# …`` comment for brace-counting purposes."""
    idx = line.find("#")
    return line[:idx] if idx != -1 else line


def _find_opening_brace(lines, start, stop=None):
    """Return the index of the first line with ``{`` after *start*.

    Skips blank lines and ``#``-comments.  Returns ``None`` if a non-blank,
    non-comment line without a brace is encountered first.
    """
    if stop is None:
        stop = len(lines)
    for i in range(start, stop):
        s = lines[i].strip()
        if not s or s.startswith("#"):
            continue
        if "{" in _strip_comment(s):
            return i
        return None
    return None


def _find_closing_brace(lines, brace_start, stop=None):
    """Starting from *brace_start* (the line containing the opening ``{``),
    return the index of the line where brace depth returns to zero.
    """
    if stop is None:
        stop = len(lines)
    depth = 0
    for i in range(brace_start, stop):
        cleaned = _strip_comment(lines[i])
        depth += cleaned.count("{") - cleaned.count("}")
        if depth == 0:
            return i
    return None


def parse_gui_file(text, source_file):
    """Extract all type and template definitions from *text*.

    Returns a list of :class:`GuiDefinition`.
    """
    lines = text.split("\n")
    definitions = []
    i = 0

    while i < len(lines):
        stripped = lines[i].lstrip()

        # ── Template ──────────────────────────────────────────────
        m = _TEMPLATE_RE.match(stripped)
        if m:
            name = m.group(1)
            start = i
            if m.group(2):                     # brace on same line
                brace_line = i
            else:
                brace_line = _find_opening_brace(lines, i + 1)
                if brace_line is None:
                    i += 1
                    continue
            end = _find_closing_brace(lines, brace_line)
            if end is None:
                print(f"  Warning: Unbalanced braces for template "
                      f"'{name}' in {source_file}:{i + 1}")
                i += 1
                continue
            definitions.append(GuiDefinition(
                name=name, kind="template",
                namespace=None, base_widget=None,
                text="\n".join(lines[start:end + 1]),
                source_file=source_file,
                start_line=start, end_line=end,
            ))
            i = end + 1
            continue

        # ── Types block ───────────────────────────────────────────
        m = _TYPES_BLOCK_RE.match(stripped)
        if m:
            namespace = m.group(1)
            if m.group(2):
                brace_line = i
            else:
                brace_line = _find_opening_brace(lines, i + 1)
                if brace_line is None:
                    i += 1
                    continue
            types_end = _find_closing_brace(lines, brace_line)
            if types_end is None:
                print(f"  Warning: Unbalanced braces for types "
                      f"'{namespace}' in {source_file}:{i + 1}")
                i += 1
                continue

            # Scan inside for individual type definitions
            j = brace_line + 1
            while j < types_end:
                inner = lines[j].lstrip()
                tm = _TYPE_DEF_RE.match(inner)
                if tm:
                    tname = tm.group(1)
                    base = tm.group(2)
                    tstart = j
                    if tm.group(3):
                        tbrace = j
                    else:
                        tbrace = _find_opening_brace(lines, j + 1,
                                                     stop=types_end)
                        if tbrace is None:
                            j += 1
                            continue
                    tend = _find_closing_brace(lines, tbrace,
                                              stop=types_end)
                    if tend is None:
                        print(f"  Warning: Unbalanced braces for type "
                              f"'{tname}' in {source_file}:{j + 1}")
                        j += 1
                        continue
                    definitions.append(GuiDefinition(
                        name=tname, kind="type",
                        namespace=namespace, base_widget=base,
                        text="\n".join(lines[tstart:tend + 1]),
                        source_file=source_file,
                        start_line=tstart, end_line=tend,
                    ))
                    j = tend + 1
                else:
                    j += 1

            i = types_end + 1
            continue

        # ── Top-level widget instance ─────────────────────────────
        # Only match at column 0 (no leading whitespace) to avoid
        # picking up nested widget children inside other definitions.
        raw = lines[i]
        if raw and raw[0:1] not in ("", " ", "\t", "\r", "\n", "#", "@"):
            m = _WIDGET_INSTANCE_RE.match(stripped)
            if m:
                wtype = m.group(1)
                start = i
                if m.group(2):
                    brace_line = i
                else:
                    brace_line = _find_opening_brace(lines, i + 1)
                    if brace_line is None:
                        i += 1
                        continue
                end = _find_closing_brace(lines, brace_line)
                if end is None:
                    i += 1
                    continue

                # Extract name = "..." from the first few lines
                wname = None
                scan_limit = min(brace_line + 15, end + 1)
                for k in range(brace_line, scan_limit):
                    nm = _NAME_PROP_RE.search(lines[k])
                    if nm:
                        wname = nm.group(1)
                        break

                if wname:
                    definitions.append(GuiDefinition(
                        name=wname, kind="widget",
                        namespace=wtype, base_widget=None,
                        text="\n".join(lines[start:end + 1]),
                        source_file=source_file,
                        start_line=start, end_line=end,
                    ))
                i = end + 1
                continue

        i += 1

    return definitions


def find_definition_in_file(text, name, kind, namespace=None):
    """Locate *name* in *text* and return ``(start_line, end_line)`` or ``None``."""
    for d in parse_gui_file(text, ""):
        if d.name == name and d.kind == kind:
            if kind == "type" and namespace and d.namespace != namespace:
                continue
            return (d.start_line, d.end_line)
    return None

# ─── Git Helpers ──────────────────────────────────────────────────────────────

def run_git(args, cwd=ROOT_DIR, check=True, env=None):
    """Run ``git <args>`` and return stdout.  Exits on failure when *check*."""
    try:
        run_env = None
        if env:
            run_env = os.environ.copy()
            run_env.update(env)
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=check,
            env=run_env,
        )
        if not check and result.returncode != 0:
            return None
        return result.stdout.rstrip()
    except subprocess.CalledProcessError as e:
        print(f"Git error: git {' '.join(args)}")
        if e.stdout:
            print(e.stdout.strip())
        if e.stderr:
            print(e.stderr.strip())
        sys.exit(1)


def _git_hash_object(content):
    """Write *content* to the git object store.  Returns the blob SHA."""
    result = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=ROOT_DIR,
        input=content,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _vanilla_branch_exists():
    return run_git(["rev-parse", "--verify", VANILLA_BRANCH],
                   check=False) is not None


def _has_merge_in_progress():
    return os.path.exists(os.path.join(ROOT_DIR, ".git", "MERGE_HEAD"))


def _ensure_clean_worktree():
    output = run_git(["status", "--porcelain"])
    if not output:
        return
    for line in output.splitlines():
        if line.startswith("??"):
            continue
        print("Error: You have uncommitted changes. "
              "Commit or stash them first.")
        sys.exit(1)


def _ensure_no_merge():
    if _has_merge_in_progress():
        print("Error: A merge is in progress. "
              "Complete or abort it first.")
        sys.exit(1)


def _read_from_branch(branch, path):
    """Read a file from *branch* without switching.  Returns content or ``None``."""
    return run_git(["show", f"{branch}:{path}"], check=False)


def _update_vanilla_branch(tracking_files, message="Update vanilla GUI definitions"):
    """Create or update the ``gui/vanilla`` branch via plumbing (no checkout).

    *tracking_files* maps relative paths to content strings.
    Returns the new commit SHA.
    """
    tmp_index = os.path.join(ROOT_DIR, ".git", "tmp_gui_index")
    plumbing = {"GIT_INDEX_FILE": tmp_index}

    try:
        if _vanilla_branch_exists():
            tree = run_git(["rev-parse", f"{VANILLA_BRANCH}^{{tree}}"])
            run_git(["read-tree", tree], env=plumbing)

        all_paths = set()
        for rel, content in tracking_files.items():
            blob = _git_hash_object(content)
            run_git(["update-index", "--add", "--cacheinfo",
                     f"100644,{blob},{rel}"], env=plumbing)
            all_paths.add(rel)

        # Remove entries no longer tracked
        existing = run_git(["ls-files", "--cached"], env=plumbing)
        if existing:
            for path in existing.splitlines():
                if path not in all_paths:
                    run_git(["update-index", "--remove", path],
                            env=plumbing)

        tree_sha = run_git(["write-tree"], env=plumbing)

        parent_args = []
        if _vanilla_branch_exists():
            parent = run_git(["rev-parse", VANILLA_BRANCH])
            parent_args = ["-p", parent]

        commit = run_git(
            ["commit-tree", tree_sha] + parent_args + ["-m", message])
        run_git(["update-ref", f"refs/heads/{VANILLA_BRANCH}", commit])
        return commit
    finally:
        if os.path.exists(tmp_index):
            os.remove(tmp_index)

# ─── Manifest ────────────────────────────────────────────────────────────────

def _load_manifest():
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _save_manifest(manifest):
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")


def _tracking_path(kind, name):
    subdirs = {"type": "types", "template": "templates", "widget": "widgets"}
    return f"{TRACKING_DIR_NAME}/{subdirs[kind]}/{name}.gui"


def _tracking_key(kind, name):
    return f"{kind}:{name}"

# ─── Scanner ─────────────────────────────────────────────────────────────────

def _scan_definitions(base_dir, source_dirs):
    """Recursively parse all ``.gui`` files and return ``[GuiDefinition, …]``."""
    all_defs = []
    for source in source_dirs:
        gui_dir = os.path.join(base_dir, source, "gui")
        if not os.path.isdir(gui_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(gui_dir):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            for fname in sorted(filenames):
                if not fname.endswith(".gui"):
                    continue
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, base_dir).replace("\\", "/")
                try:
                    with open(full, "r", encoding="utf-8-sig") as f:
                        text = f.read()
                except (OSError, UnicodeDecodeError) as e:
                    print(f"  Warning: Could not read {rel}: {e}")
                    continue
                all_defs.extend(parse_gui_file(text, rel))
    return all_defs


def _find_overrides(mod_defs, vanilla_defs):
    """Return ``[(mod_def, vanilla_def), …]`` for names that appear in both."""
    vanilla_map = {}
    for d in vanilla_defs:
        key = _tracking_key(d.kind, d.name)
        vanilla_map.setdefault(key, d)

    mod_map = {}
    for d in mod_defs:
        key = _tracking_key(d.kind, d.name)
        if key in mod_map:
            prev = mod_map[key]
            print(f"  Warning: Duplicate {d.kind} '{d.name}' in mod "
                  f"({prev.source_file} and {d.source_file}). Using first.")
        else:
            mod_map[key] = d

    return [(mod_map[k], vanilla_map[k])
            for k in sorted(mod_map) if k in vanilla_map]

# ─── Config ──────────────────────────────────────────────────────────────────

def _load_config():
    if tomllib is None:
        return {}
    try:
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def _resolve_game_dir(args):
    if args.game_dir:
        if os.path.isdir(args.game_dir):
            return args.game_dir
        print(f"Error: Game directory not found: {args.game_dir}")
        sys.exit(1)

    cfg = _load_config().get("game_directory", "")
    if cfg and os.path.isdir(cfg):
        return cfg

    for p in STEAM_GAME_PATHS:
        if os.path.isdir(p):
            return p

    print("Error: Could not locate EU5 game directory.")
    print("Set 'game_directory' in config.toml or use --game-dir.")
    sys.exit(1)

# ─── Utilities ───────────────────────────────────────────────────────────────

def _content_hash(content):
    n = content.replace("\r\n", "\n").rstrip("\n") + "\n"
    return hashlib.sha256(n.encode("utf-8")).hexdigest()


def _write_tracking_file(rel_path, content):
    """Write a tracking file under ROOT_DIR."""
    abs_path = os.path.join(ROOT_DIR, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_init(args):
    game_dir = _resolve_game_dir(args)

    _ensure_clean_worktree()
    _ensure_no_merge()

    if _vanilla_branch_exists():
        print(f"Error: Branch '{VANILLA_BRANCH}' already exists.")
        print(f"Delete it first (git branch -D {VANILLA_BRANCH}) "
              "or use 'refresh' to update tracking.")
        return 1
    if os.path.isdir(TRACKING_DIR):
        print(f"Error: {TRACKING_DIR_NAME}/ already exists.")
        return 1

    # Scan
    print("Scanning mod GUI files...")
    mod_defs = _scan_definitions(ROOT_DIR, GUI_SOURCES)
    print(f"  Found {len(mod_defs)} definition(s) in mod.")

    print("Scanning vanilla GUI files...")
    vanilla_defs = _scan_definitions(game_dir, GUI_SOURCES)
    print(f"  Found {len(vanilla_defs)} definition(s) in vanilla.")

    overrides = _find_overrides(mod_defs, vanilla_defs)
    if not overrides:
        print("\nNo overrides detected — your mod does not override "
              "any vanilla GUI types or templates.")
        return 0

    n_types = sum(1 for m, _ in overrides if m.kind == "type")
    n_tmpls = sum(1 for m, _ in overrides if m.kind == "template")
    print(f"\nDetected {len(overrides)} override(s) "
          f"({n_types} type(s), {n_tmpls} template(s)):")
    for md, _ in overrides:
        print(f"  {md.kind}: {md.name}  ({md.source_file})")

    # Build manifest + vanilla tracking files
    manifest = {"version": MANIFEST_VERSION, "definitions": {}}
    vanilla_files = {}

    for md, vd in overrides:
        key = _tracking_key(md.kind, md.name)
        tp = _tracking_path(md.kind, md.name)
        manifest["definitions"][key] = {
            "namespace": md.namespace,
            "base_widget": md.base_widget,
            "mod_file": md.source_file,
            "vanilla_file": vd.source_file,
            "tracking_path": tp,
        }
        vanilla_files[tp] = vd.text + "\n"

    # 1. Create gui/vanilla orphan branch (via plumbing — no checkout)
    print(f"\nCreating {VANILLA_BRANCH} branch...")
    _update_vanilla_branch(vanilla_files,
                           "Initialize vanilla GUI definitions")

    # 2. Merge into working branch (establishes common ancestor)
    print("Merging vanilla base into working branch...")
    run_git(["merge", "--allow-unrelated-histories", "--no-commit",
             VANILLA_BRANCH])

    # 3. Overwrite with mod versions + add manifest
    for md, _ in overrides:
        tp = _tracking_path(md.kind, md.name)
        _write_tracking_file(tp, md.text + "\n")
    _save_manifest(manifest)

    # 4. Commit
    run_git(["add", TRACKING_DIR_NAME + "/"])
    run_git(["commit", "-m",
             f"Initialize GUI tracking with {len(overrides)} definition(s)"])

    print(f"\nDone! Tracking {len(overrides)} GUI override(s).")
    print("Run 'gui_update.py check' after a game update to detect changes.")
    return 0


def cmd_check(args):
    game_dir = _resolve_game_dir(args)
    manifest = _load_manifest()
    if manifest is None:
        print("Not initialized. Run 'gui_update.py init' first.")
        return 1
    if not _vanilla_branch_exists():
        print(f"Error: {VANILLA_BRANCH} branch not found.")
        return 1

    print("Scanning current vanilla GUI files...")
    vanilla_defs = _scan_definitions(game_dir, GUI_SOURCES)
    vanilla_map = {}
    for d in vanilla_defs:
        vanilla_map[_tracking_key(d.kind, d.name)] = d

    changed = []
    removed = []

    for key, entry in sorted(manifest["definitions"].items()):
        old = _read_from_branch(VANILLA_BRANCH, entry["tracking_path"])
        if old is None:
            continue
        if key in vanilla_map:
            new = vanilla_map[key].text + "\n"
            if _content_hash(old) != _content_hash(new):
                changed.append((key, entry))
        else:
            removed.append((key, entry))

    if not changed and not removed:
        print("\nAll tracked definitions are up to date with vanilla.")
        return 0

    if changed:
        print(f"\n{len(changed)} definition(s) changed in vanilla:")
        for key, entry in changed:
            print(f"  {key}  (in {entry['vanilla_file']})")
    if removed:
        print(f"\n{len(removed)} definition(s) removed from vanilla:")
        for key, entry in removed:
            print(f"  {key}  (was in {entry['vanilla_file']})")

    print("\nRun 'gui_update.py merge' to incorporate these changes.")
    return 0


def cmd_merge(args):
    game_dir = _resolve_game_dir(args)
    manifest = _load_manifest()
    if manifest is None:
        print("Not initialized. Run 'gui_update.py init' first.")
        return 1
    if not _vanilla_branch_exists():
        print(f"Error: {VANILLA_BRANCH} branch not found.")
        return 1

    _ensure_clean_worktree()
    _ensure_no_merge()

    # Update vanilla branch with current vanilla definitions
    print("Scanning current vanilla GUI files...")
    vanilla_defs = _scan_definitions(game_dir, GUI_SOURCES)
    vanilla_map = {}
    for d in vanilla_defs:
        vanilla_map[_tracking_key(d.kind, d.name)] = d

    tracking_files = {}
    updated = 0
    for key, entry in manifest["definitions"].items():
        tp = entry["tracking_path"]
        if key in vanilla_map:
            new_content = vanilla_map[key].text + "\n"
            old_content = _read_from_branch(VANILLA_BRANCH, tp)
            tracking_files[tp] = new_content
            if (old_content is None
                    or _content_hash(old_content) != _content_hash(new_content)):
                updated += 1

    if updated == 0:
        print("Vanilla branch already up to date. Nothing to merge.")
        return 0

    print(f"Updating {VANILLA_BRANCH} ({updated} definition(s) changed)...")
    _update_vanilla_branch(
        tracking_files,
        f"Update {updated} vanilla GUI definition(s)")

    # Start merge
    print(f"Merging {VANILLA_BRANCH} into current branch...")
    run_git(["merge", VANILLA_BRANCH, "--no-commit", "--no-ff"], check=False)

    # Check for conflicts
    conflict_out = run_git(["diff", "--name-only", "--diff-filter=U"],
                           check=False) or ""
    conflicts = [f for f in conflict_out.splitlines()
                 if f.startswith(TRACKING_DIR_NAME + "/")]

    if conflicts:
        print(f"\nConflicts in {len(conflicts)} file(s):")
        for c in conflicts:
            print(f"  {c}")
        print(f"\nResolve conflicts in {TRACKING_DIR_NAME}/, then:")
        print(f"  git add {TRACKING_DIR_NAME}/")
        print("  git commit")
        print("  python tools/gui_update.py apply")
        return 1

    if _has_merge_in_progress():
        run_git(["commit", "-m",
                 f"Merge vanilla GUI updates ({updated} definition(s))"])
        print(f"\nMerge completed cleanly ({updated} definition(s) updated).")
    else:
        print("\nMerge completed (no file-level changes).")

    print("Run 'gui_update.py apply' to sync changes to mod GUI files.")
    return 0


def cmd_apply(args):
    manifest = _load_manifest()
    if manifest is None:
        print("Not initialized. Run 'gui_update.py init' first.")
        return 1
    if _has_merge_in_progress():
        print("Error: Merge in progress. Resolve conflicts and commit first.")
        return 1

    applied = 0
    errors = 0

    for key, entry in sorted(manifest["definitions"].items()):
        tp = entry["tracking_path"]
        abs_tp = os.path.join(ROOT_DIR, tp.replace("/", os.sep))

        if not os.path.isfile(abs_tp):
            print(f"  Warning: Tracking file missing: {tp}")
            continue

        with open(abs_tp, "r", encoding="utf-8") as f:
            new_text = f.read().rstrip("\n")

        mod_file = entry["mod_file"]
        abs_mod = os.path.join(ROOT_DIR, mod_file.replace("/", os.sep))

        if not os.path.isfile(abs_mod):
            print(f"  Warning: Mod file not found: {mod_file}")
            errors += 1
            continue

        # Read mod file (preserve BOM + detect line endings)
        with open(abs_mod, "rb") as f:
            raw = f.read()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        has_crlf = b"\r\n" in raw
        mod_text = raw.decode("utf-8-sig").replace("\r\n", "\n")

        kind, name = key.split(":", 1)
        namespace = entry.get("namespace")

        span = find_definition_in_file(mod_text, name, kind, namespace)
        if span is None:
            print(f"  Error: Could not find {key} in {mod_file}")
            errors += 1
            continue

        start, end = span
        lines = mod_text.split("\n")
        new_lines = lines[:start] + new_text.split("\n") + lines[end + 1:]
        result = "\n".join(new_lines)

        if has_crlf:
            result = result.replace("\n", "\r\n")

        with open(abs_mod, "wb") as f:
            if has_bom:
                f.write(b"\xef\xbb\xbf")
            f.write(result.encode("utf-8"))

        applied += 1
        print(f"  Applied: {key} -> {mod_file}")

    if errors:
        print(f"\n{errors} error(s) encountered.")
    if applied:
        print(f"\n{applied} definition(s) applied to mod files.")
        print("Review the changes and commit when ready.")
    else:
        print("\nNo definitions to apply.")

    return 1 if errors else 0


def cmd_refresh(args):
    game_dir = _resolve_game_dir(args)
    manifest = _load_manifest()
    if manifest is None:
        print("Not initialized. Run 'gui_update.py init' first.")
        return 1
    if not _vanilla_branch_exists():
        print(f"Error: {VANILLA_BRANCH} branch not found.")
        return 1

    _ensure_no_merge()

    print("Scanning mod GUI files...")
    mod_defs = _scan_definitions(ROOT_DIR, GUI_SOURCES)

    print("Scanning vanilla GUI files...")
    vanilla_defs = _scan_definitions(game_dir, GUI_SOURCES)

    overrides = _find_overrides(mod_defs, vanilla_defs)
    new_keys = {}
    for md, vd in overrides:
        new_keys[_tracking_key(md.kind, md.name)] = (md, vd)

    old_set = set(manifest["definitions"])
    new_set = set(new_keys)
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)

    if added:
        print(f"\n{len(added)} new override(s):")
        for k in added:
            print(f"  + {k}")
    if removed:
        print(f"\n{len(removed)} removed override(s):")
        for k in removed:
            print(f"  - {k}")

    # Rebuild manifest + tracking files
    new_manifest = {"version": MANIFEST_VERSION, "definitions": {}}

    for key in sorted(new_set):
        md, vd = new_keys[key]
        tp = _tracking_path(md.kind, md.name)
        new_manifest["definitions"][key] = {
            "namespace": md.namespace,
            "base_widget": md.base_widget,
            "mod_file": md.source_file,
            "vanilla_file": vd.source_file,
            "tracking_path": tp,
        }
        _write_tracking_file(tp, md.text + "\n")

    # Remove stale tracking files
    for key in removed:
        entry = manifest["definitions"][key]
        abs_tp = os.path.join(ROOT_DIR,
                              entry["tracking_path"].replace("/", os.sep))
        if os.path.isfile(abs_tp):
            os.remove(abs_tp)

    _save_manifest(new_manifest)

    # Update vanilla branch
    vanilla_map = {}
    for d in vanilla_defs:
        vanilla_map[_tracking_key(d.kind, d.name)] = d
    vanilla_files = {}
    for key, entry in new_manifest["definitions"].items():
        if key in vanilla_map:
            vanilla_files[entry["tracking_path"]] = \
                vanilla_map[key].text + "\n"
    _update_vanilla_branch(vanilla_files,
                           "Refresh vanilla GUI definitions")

    print(f"\nRefreshed: {len(new_set)} definition(s) tracked.")
    if added or removed:
        print(f"Stage and commit {TRACKING_DIR_NAME}/ changes when ready.")
    return 0


def cmd_status(args):
    manifest = _load_manifest()
    if manifest is None:
        print("GUI tracking is not initialized.")
        print("Run 'gui_update.py init' to set up tracking.")
        return 0

    defs = manifest.get("definitions", {})
    print("GUI Update Tracking Status")
    print(f"  Vanilla branch: "
          f"{'OK' if _vanilla_branch_exists() else 'MISSING'}")
    print(f"  Tracked definitions: {len(defs)}")

    if not defs:
        return 0

    types = sorted(k for k in defs if k.startswith("type:"))
    templates = sorted(k for k in defs if k.startswith("template:"))

    if types:
        print(f"\n  Types ({len(types)}):")
        for key in types:
            e = defs[key]
            ns = f" [{e['namespace']}]" if e.get("namespace") else ""
            print(f"    {key}{ns}")
            print(f"      mod: {e['mod_file']}")
            print(f"      vanilla: {e['vanilla_file']}")

    if templates:
        print(f"\n  Templates ({len(templates)}):")
        for key in templates:
            e = defs[key]
            print(f"    {key}")
            print(f"      mod: {e['mod_file']}")
            print(f"      vanilla: {e['vanilla_file']}")

    return 0

# ─── CLI ─────────────────────────────────────────────────────────────────────

_COMMANDS = {
    "init": cmd_init,
    "check": cmd_check,
    "merge": cmd_merge,
    "apply": cmd_apply,
    "refresh": cmd_refresh,
    "status": cmd_status,
}


def main():
    parser = argparse.ArgumentParser(
        description="Track and merge vanilla GUI updates "
                    "for EU5 mod overrides.",
    )
    parser.add_argument(
        "--game-dir", type=str, default=None,
        help="Path to EU5 game directory (overrides config.toml)",
    )

    sub = parser.add_subparsers(dest="command")
    sub.required = True

    sub.add_parser("init",
                   help="Initialize GUI tracking for this mod")
    sub.add_parser("check",
                   help="Check for vanilla GUI changes")
    sub.add_parser("merge",
                   help="Update vanilla branch and merge changes")
    sub.add_parser("apply",
                   help="Apply resolved changes back to mod GUI files")
    sub.add_parser("refresh",
                   help="Re-extract mod definitions into tracking files")
    sub.add_parser("status",
                   help="Show tracking status")

    args = parser.parse_args()
    sys.exit(_COMMANDS[args.command](args))


if __name__ == "__main__":
    main()
