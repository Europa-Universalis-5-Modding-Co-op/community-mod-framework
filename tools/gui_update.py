"""GUI Update Helper. Track and merge vanilla GUI changes for EU5 mod overrides.

Uses two git refs to track vanilla state:

* ``gui/vanilla``: branch holding the latest vanilla definitions. Advances
  when ``merge`` detects a game update.
* ``gui/vanilla-merged``: bookmark on the same chain pointing at the last
  successfully merged vanilla commit. Used as the explicit merge base for
  per-file three-way merges so the merge result does not depend on git's
  parent-link auto-detection.

Per-file three-way merges run through ``git merge-file`` with
``gui/vanilla-merged`` as base. Conflicts produce a 2-parent merge
commit; the next ``apply`` (or ``merge``) run advances the bookmark.

Commands:
    init      Set up tracking for this mod
    check     Report which tracked definitions changed in vanilla
    merge     Update vanilla branch and merge changes
    apply     Write resolved tracking files back to mod GUI files
    refresh   Re-extract mod definitions into tracking files
    status    Show tracking status

Pass ``--beta`` (``-b``) to any vanilla-reading command (init, check, merge,
refresh) to target the EU5 closed-beta install (Project Caesar Review) instead
of the live game. Beta-sourced gui/vanilla commits are tagged ``(beta)`` in
their subject.

Pass ``--repull`` (``--force-pull``) to ``merge`` to force a fresh vanilla
scan when a previous merge is still pending (gui/vanilla ahead of
gui/vanilla-merged). The re-pulled snapshot overwrites the pending
gui/vanilla commit instead of resuming it, so the branch gains no duplicate
commit.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

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
MERGED_BRANCH = "gui/vanilla-merged"

STEAM_GAME_PATHS = [
    os.path.join("C:" + os.sep, "Steam", "steamapps", "common",
                 "Europa Universalis V", "game"),
    os.path.join("C:" + os.sep, "Program Files (x86)", "Steam", "steamapps",
                 "common", "Europa Universalis V", "game"),
    os.path.join("C:" + os.sep, "Program Files", "Steam", "steamapps",
                 "common", "Europa Universalis V", "game"),
]

BETA_STEAM_GAME_PATHS = [
    os.path.join("C:" + os.sep, "Steam", "steamapps", "common",
                 "Project Caesar Review", "game"),
    os.path.join("C:" + os.sep, "Program Files (x86)", "Steam", "steamapps",
                 "common", "Project Caesar Review", "game"),
    os.path.join("C:" + os.sep, "Program Files", "Steam", "steamapps",
                 "common", "Project Caesar Review", "game"),
]

# ─── Regex (used with .match() on lstripped lines) ───────────────────────────

_TYPES_BLOCK_RE = re.compile(r"types\s+(\w+)\s*(\{)?\s*(?:#.*)?$")
_TYPE_DEF_RE = re.compile(r"type\s+(\w+)\s*=\s*(\w+)\s*(\{)?\s*(?:#.*)?$")
_TEMPLATE_RE = re.compile(r"template\s+(\w+)\s*(\{)?\s*(?:#.*)?$")
# Match top-level widget instances at column 0 only.
_WIDGET_INSTANCE_RE = re.compile(r"(\w+)\s*=\s*(\{)?\s*(?:#.*)?$")
_NAME_PROP_RE = re.compile(r'name\s*=\s*"([^"]+)"')
_CONSTANT_RE = re.compile(r"@(\w+)\s*=")
# Match @name and @[name ...] (first name only) for body references.
_CONSTANT_REF_RE = re.compile(r"@\[?(\w+)")

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

        # ── Constant declaration (file-scope, column 0 only) ──────
        if lines[i][:1] == "@":
            m = _CONSTANT_RE.match(lines[i])
            if m:
                cname = m.group(1)
                definitions.append(GuiDefinition(
                    name=cname, kind="constant",
                    namespace=None, base_widget=None,
                    text=lines[i].rstrip("\r"),
                    source_file=source_file,
                    start_line=i, end_line=i,
                ))
            i += 1
            continue

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

        # ── Top-level widget instance (column 0 only — skip nested children)
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


def _assert_unique_top_level_defs(text, path):
    """Report duplicated top-level definitions in *text*.

    Checks that no ``(kind, namespace, name)`` parsed from *text* is defined
    more than once. A repeated definition, typically a top-level widget name
    appearing twice, is the signature of a corrupted ``.gui`` file that EU5
    fails to load. Prints an error for each duplicate and returns ``False``
    when any is found, ``True`` when *text* is clean.
    """
    seen = {}
    unique = True
    for d in parse_gui_file(text, path):
        sig = (d.kind, d.namespace, d.name)
        first = seen.get(sig)
        if first is None:
            seen[sig] = d
            continue
        label = f"{d.kind} '{d.name}'"
        if d.namespace:
            label += f" ({d.namespace})"
        print(f"  Error: Duplicate {label} in {path}: lines "
              f"{first.start_line + 1} and {d.start_line + 1}.")
        unique = False
    return unique

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
            encoding="utf-8",
            # Tolerate stray non-UTF-8 bytes in vanilla GUI content.
            errors="replace",
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
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _vanilla_branch_exists():
    return run_git(["rev-parse", "--verify", VANILLA_BRANCH],
                   check=False) is not None


def _vanilla_merged_ref_exists():
    return run_git(["rev-parse", "--verify", MERGED_BRANCH],
                   check=False) is not None


def _ensure_vanilla_merged_ref():
    """Initialize gui/vanilla-merged from gui/vanilla tip if missing."""
    if _vanilla_merged_ref_exists():
        return
    if not _vanilla_branch_exists():
        return
    tip = run_git(["rev-parse", VANILLA_BRANCH])
    run_git(["update-ref", f"refs/heads/{MERGED_BRANCH}", tip])


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
    """Read a file from *branch* without switching, stripping any leading BOM."""
    content = run_git(["show", f"{branch}:{path}"], check=False)
    if content is not None and content.startswith("﻿"):
        content = content[1:]
    return content


def _push_refs(refs, force=False):
    """Push refs to origin (no-op for local-only repos). force=True uses --force-with-lease."""
    refs = [r for r in refs if r]
    if not refs:
        return
    if run_git(["remote", "get-url", "origin"], check=False) is None:
        return
    print(f"Pushing {', '.join(refs)} to origin"
          f"{' (force-with-lease)' if force else ''}...")
    cmd = ["git", "push"]
    if force:
        cmd.append("--force-with-lease")
    # -u sets upstream so the local branch and origin/<branch> show as one
    # logical branch in git history tools. No-op when already set.
    cmd += ["-u", "origin"] + refs
    result = subprocess.run(
        cmd,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        print(f"  Warning: Failed to push {', '.join(refs)}.")
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"  {line}")


def _versioned_message(message, version, beta=False):
    """Prefix the commit subject *message* with *version* when it is set,
    tagging it ``(beta)`` after the version when *beta*."""
    marker = " (beta)" if beta else ""
    if version:
        return f"{version}{marker}: {message}"
    return f"(beta) {message}" if beta else message


def _update_vanilla_branch(tracking_files,
                           message="Update vanilla GUI definitions",
                           version=None,
                           force_push=False,
                           beta=False,
                           parent_override=None):
    """Create or update the ``gui/vanilla`` branch via plumbing (no checkout).

    *tracking_files* maps relative paths to content strings.
    *version* prefixes the commit subject when provided; *beta* tags it.
    *parent_override* sets the new commit's parent, replacing the current tip
    rather than stacking on it; the branch is then force-pushed. Returns the
    new commit SHA.
    """
    message = _versioned_message(message, version, beta=beta)
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
        if parent_override is not None:
            parent_args = ["-p", parent_override]
        elif _vanilla_branch_exists():
            parent = run_git(["rev-parse", VANILLA_BRANCH])
            parent_args = ["-p", parent]

        commit = run_git(
            ["commit-tree", tree_sha] + parent_args + ["-m", message])
        run_git(["update-ref", f"refs/heads/{VANILLA_BRANCH}", commit])
    finally:
        if os.path.exists(tmp_index):
            os.remove(tmp_index)

    _push_refs([VANILLA_BRANCH],
               force=force_push or parent_override is not None)
    return commit

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


def _constant_tracking_path(mod_file, vanilla_file, name):
    mod_safe = os.path.splitext(mod_file.replace("/", "__"))[0]
    vanilla_safe = os.path.splitext(vanilla_file.replace("/", "__"))[0]
    return f"{TRACKING_DIR_NAME}/constants/{mod_safe}/{vanilla_safe}/{name}.gui"


def _tracking_key(kind, name):
    return f"{kind}:{name}"


def _constant_tracking_key(mod_file, vanilla_file, name):
    return f"constant:{mod_file}:{vanilla_file}:{name}"

# ─── Scanner ─────────────────────────────────────────────────────────────────

def _scan_definitions(base_dir, source_dirs, assert_unique=False):
    """Recursively parse all ``.gui`` files and return ``[GuiDefinition, …]``.

    With *assert_unique*, a file containing a duplicated top-level definition
    aborts the run before its definitions are collected.
    """
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
                if assert_unique and not _assert_unique_top_level_defs(
                        text, rel):
                    print("Aborting: refusing to sync tracking from a "
                          "corrupted mod file.")
                    sys.exit(1)
                all_defs.extend(parse_gui_file(text, rel))
    return all_defs


def _find_overrides(mod_defs, vanilla_defs):
    """Return ``[(mod_def, vanilla_def), …]`` for names that appear in both.

    Constants are file-scoped and handled separately by ``_link_constants``.
    """
    vanilla_map = {}
    for d in vanilla_defs:
        if d.kind == "constant":
            continue
        key = _tracking_key(d.kind, d.name)
        vanilla_map.setdefault(key, d)

    mod_map = {}
    for d in mod_defs:
        if d.kind == "constant":
            continue
        key = _tracking_key(d.kind, d.name)
        if key in mod_map:
            prev = mod_map[key]
            print(f"  Warning: Duplicate {d.kind} '{d.name}' in mod "
                  f"({prev.source_file} and {d.source_file}). Using first.")
        else:
            mod_map[key] = d

    return [(mod_map[k], vanilla_map[k])
            for k in sorted(mod_map) if k in vanilla_map]


def _link_constants(mod_defs, vanilla_defs, override_pairs):
    """Return ``[(mod_const, vanilla_const), …]`` linked by file-scope usage. A mod constant pairs with each vanilla file that holds one of its referenced overrides."""
    mod_consts = {}
    for d in mod_defs:
        if d.kind == "constant":
            mod_consts.setdefault(d.source_file, {}).setdefault(d.name, d)

    vanilla_consts = {}
    for d in vanilla_defs:
        if d.kind == "constant":
            vanilla_consts.setdefault(d.source_file, {}).setdefault(d.name, d)

    usage = {}
    for mod_def, vanilla_def in override_pairs:
        for name in _CONSTANT_REF_RE.findall(mod_def.text):
            usage.setdefault((mod_def.source_file, name), set()).add(
                vanilla_def.source_file)

    pairs = []
    for mod_file, by_name in mod_consts.items():
        for name, mod_const in by_name.items():
            for vfile in usage.get((mod_file, name), ()):
                vd = vanilla_consts.get(vfile, {}).get(name)
                if vd is not None:
                    pairs.append((mod_const, vd))
    return pairs

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

    beta = getattr(args, "beta", False)
    cfg = _load_config()
    if beta:
        cfg_dir = cfg.get("beta_game_directory", "")
        search_paths = BETA_STEAM_GAME_PATHS
        config_key = "beta_game_directory"
        label = "EU5 closed beta (Project Caesar Review)"
    else:
        cfg_dir = cfg.get("game_directory", "")
        search_paths = STEAM_GAME_PATHS
        config_key = "game_directory"
        label = "EU5 game"

    if cfg_dir and os.path.isdir(cfg_dir):
        return cfg_dir

    for p in search_paths:
        if os.path.isdir(p):
            return p

    print(f"Error: Could not locate {label} directory.")
    print(f"Set '{config_key}' in config.toml or use --game-dir.")
    sys.exit(1)

# ─── Utilities ───────────────────────────────────────────────────────────────

def _content_hash(content):
    n = content.replace("\r\n", "\n").rstrip("\n") + "\n"
    return hashlib.sha256(n.encode("utf-8")).hexdigest()


def _make_tracking_header(vanilla_file, mod_file):
    return (f"# vanilla: {vanilla_file}\n"
            f"# mod: {mod_file}\n"
            f"\n")


def _strip_tracking_header(content):
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].rstrip("\r ")
        if (stripped.startswith("# vanilla:")
                or stripped.startswith("# mod:")):
            i += 1
        else:
            break
    if i > 0 and i < len(lines) and lines[i].strip() == "":
        i += 1
    return "\n".join(lines[i:])


def _body_hash(content):
    return _content_hash(_strip_tracking_header(content))


def _write_tracking_file(rel_path, content):
    """Write a tracking file under ROOT_DIR with UTF-8 BOM + CRLF."""
    abs_path = os.path.join(ROOT_DIR, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    if content.startswith("﻿"):
        content = content[1:]
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    new_bytes = (b"\xef\xbb\xbf"
                 + normalized.replace("\n", "\r\n").encode("utf-8"))
    if os.path.exists(abs_path):
        with open(abs_path, "rb") as f:
            if f.read() == new_bytes:
                return
    with open(abs_path, "wb") as f:
        f.write(new_bytes)


def _force_rmtree(path):
    """Remove a directory tree, retrying past Windows read-only files
    and transient handle locks (OneDrive, antivirus, IDE indexer)."""
    if not os.path.isdir(path):
        return

    def _on_exc(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
        except OSError:
            pass
        for delay in (0.0, 0.25, 1.0):
            if delay:
                time.sleep(delay)
            try:
                func(target)
                return
            except OSError:
                continue
        func(target)

    shutil.rmtree(path, onexc=_on_exc)


def _three_way_merge_string(base, ours, theirs):
    """Three-way merge of three string contents via ``git merge-file``.

    Returns ``(merged_content, has_conflicts)``. Conflict regions are
    written inline with the standard ``<<<<<<<`` / ``|||||||`` /
    ``=======`` / ``>>>>>>>`` markers (zdiff3 style).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = {
            "base": os.path.join(tmpdir, "base"),
            "ours": os.path.join(tmpdir, "ours"),
            "theirs": os.path.join(tmpdir, "theirs"),
        }
        for name, path in paths.items():
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write({"base": base, "ours": ours, "theirs": theirs}[name])
        result = subprocess.run(
            ["git", "merge-file", "-p", "--zdiff3",
             "--diff-algorithm=minimal",
             "-L", "ours", "-L", "base", "-L", "theirs",
             paths["ours"], paths["base"], paths["theirs"]],
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        if result.returncode < 0 or (
                not result.stdout and (base or ours or theirs)):
            print("Error: git merge-file failed.")
            if result.stderr:
                print(result.stderr.strip())
            sys.exit(1)
        has_conflict = "<<<<<<<" in result.stdout
        return result.stdout, has_conflict


def _scan_unresolved_conflicts():
    """Return a list of tracking files containing conflict markers."""
    if not os.path.isdir(TRACKING_DIR):
        return []
    bad = []
    for dirpath, _, filenames in os.walk(TRACKING_DIR):
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            try:
                with open(full, "r", encoding="utf-8-sig") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            if "<<<<<<<" in content and ">>>>>>>" in content:
                rel = os.path.relpath(full, ROOT_DIR).replace(os.sep, "/")
                bad.append(rel)
    return bad


def _advance_merged_ref_if_absorbed():
    """Advance ``gui/vanilla-merged`` to ``gui/vanilla`` if HEAD already has the merge. Returns whether it advanced; exits 1 on stray conflict markers."""
    if not _vanilla_branch_exists() or not _vanilla_merged_ref_exists():
        return False
    vanilla_sha = run_git(["rev-parse", VANILLA_BRANCH])
    merged_sha = run_git(["rev-parse", MERGED_BRANCH])
    if vanilla_sha == merged_sha:
        return False
    if run_git(["merge-base", "--is-ancestor", vanilla_sha, "HEAD"],
               check=False) is None:
        return False
    bad = _scan_unresolved_conflicts()
    if bad:
        print("Error: tracking files contain conflict markers:")
        for f in bad:
            print(f"  {f}")
        print("\nFix the markers, re-stage, and amend the commit, "
              "then re-run.")
        sys.exit(1)
    print("Advancing gui/vanilla-merged bookmark...")
    run_git(["update-ref",
             f"refs/heads/{MERGED_BRANCH}", vanilla_sha])
    _push_refs([MERGED_BRANCH])
    return True


def _setup_merge_state(merge_head_sha, merge_msg):
    """Write ``.git/MERGE_HEAD``/``MERGE_MSG``/``ORIG_HEAD`` so git sees a merge in progress."""
    git_dir = os.path.join(ROOT_DIR, ".git")
    head_sha = run_git(["rev-parse", "HEAD"])
    for name, content in (
        ("MERGE_HEAD", merge_head_sha),
        ("MERGE_MSG", merge_msg),
        ("ORIG_HEAD", head_sha),
    ):
        with open(os.path.join(git_dir, name), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(content + "\n")


def _stage_merge_entries(path, base_content, ours_content, theirs_content):
    """Populate index stages 1/2/3 for ``path`` so git treats the file as conflicted."""
    # --force-remove clears stage 0; plain --remove is a no-op when the file
    # exists on disk, which would leave stage 0 alongside the unmerged stages.
    run_git(["update-index", "--force-remove", path], check=False)
    lines = []
    if base_content is not None:
        sha = _git_hash_object(base_content)
        lines.append(f"100644 {sha} 1\t{path}")
    if ours_content is not None:
        sha = _git_hash_object(ours_content)
        lines.append(f"100644 {sha} 2\t{path}")
    if theirs_content is not None:
        sha = _git_hash_object(theirs_content)
        lines.append(f"100644 {sha} 3\t{path}")
    if not lines:
        return
    # Send bytes; text=True would CRLF the input on Windows and break --index-info parsing.
    subprocess.run(
        ["git", "update-index", "--index-info"],
        cwd=ROOT_DIR,
        input=("\n".join(lines) + "\n").encode("utf-8"),
        check=True,
    )

# ─── Game Version ──────────────────────────────────────────────────────────────

# continue_game.json sits in the EU5 user-data dir, two levels above the mod root.
CONTINUE_GAME_PATH = os.path.join(
    os.path.dirname(os.path.dirname(ROOT_DIR)), "continue_game.json")

_VERSION_RE = re.compile(r"v?(\d+(?:\.\d+)*)", re.IGNORECASE)


def _version_key(version):
    """Parse *version* into a tuple of ints for comparison, or None."""
    if not version:
        return None
    m = _VERSION_RE.fullmatch(str(version).strip())
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def _normalize_version(version):
    """Return *version* as ``vMAJOR.MINOR.PATCH`` with a single leading ``v``."""
    s = str(version).strip()
    if s[:1] in ("v", "V"):
        s = s[1:]
    return "v" + s


def _leading_version(text):
    """Return the normalized version token at the start of *text*, or None."""
    m = re.match(r"\s*(v?\d+(?:\.\d+)*)", text, re.IGNORECASE)
    return _normalize_version(m.group(1)) if m else None


def _ask(prompt):
    """input() that exits cleanly when no interactive terminal is attached."""
    try:
        return input(prompt)
    except EOFError:
        print("\nError: A game version is required but no terminal is "
              "available to prompt for one.")
        print("Pass it explicitly, e.g. --gv 1.2.5.")
        sys.exit(1)


def _read_continue_game_version():
    """Return ``rawGameVersion`` from continue_game.json, normalized, or None."""
    try:
        with open(CONTINUE_GAME_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    raw = data.get("rawGameVersion")
    return _normalize_version(raw) if _version_key(raw) else None


def _last_vanilla_commit_version():
    """Return the version from the latest gui/vanilla commit subject, or None."""
    if not _vanilla_branch_exists():
        return None
    subject = run_git(["log", "-1", "--format=%s", VANILLA_BRANCH], check=False)
    return _leading_version(subject) if subject else None


def _prompt_version_value(default):
    """Prompt until a valid version is entered; empty input takes *default*."""
    while True:
        if default:
            resp = _ask(f"Enter game version [{default}]: ").strip()
            if not resp:
                return default
        else:
            resp = _ask("Enter game version (e.g. 1.2.5): ").strip()
            if not resp:
                continue
        if _version_key(resp) is None:
            print("  Not a valid version. Use a numeric form like 1.2.5.")
            continue
        return _normalize_version(resp)


def _confirm_or_correct_version(detected):
    """Confirm *detected* or type a correction; return the chosen version."""
    resp = _ask("Press [Enter]/[y] to confirm, or type the correct "
                "version: ").strip()
    if not resp or resp.lower() in ("y", "yes"):
        return detected
    if _version_key(resp) is None:
        return _prompt_version_value(detected)
    return _normalize_version(resp)


def _resolve_game_version(args, is_init):
    """Resolve the version to prefix onto the gui/vanilla commit subject.

    A ``--game-version`` flag wins and skips prompting. Otherwise the detected
    version is always shown for interactive confirmation (press [Enter]/[y] to
    accept or type a correction), including when it is newer than the last
    tracked commit, so an auto-detection can always be fixed.
    """
    flag = getattr(args, "game_version", None)
    if flag:
        if _version_key(flag) is None:
            print(f"Error: Invalid --game-version value: {flag}")
            sys.exit(1)
        return _normalize_version(flag)

    detected = _read_continue_game_version()

    if is_init:
        if detected:
            print(f"\nGame version read from continue_game.json: {detected}")
            return _confirm_or_correct_version(detected)
        print("\nGame version not found in continue_game.json.")
        return _prompt_version_value(None)

    last = _last_vanilla_commit_version()
    if detected and last and _version_key(detected) > _version_key(last):
        print(f"\nGame version read from continue_game.json: {detected} "
              f"(newer than last tracked {last}).")
        return _confirm_or_correct_version(detected)

    print("\nNo newer game version detected automatically:")
    print(f"  continue_game.json: {detected or '(unavailable)'}")
    print(f"  last tracked:       {last or '(none)'}")
    return _prompt_version_value(last or detected)

# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_init(args):
    game_dir = _resolve_game_dir(args)

    _ensure_clean_worktree()
    _ensure_no_merge()

    branch_exists = _vanilla_branch_exists()
    tracking_exists = os.path.isdir(TRACKING_DIR)

    if branch_exists or tracking_exists:
        if not args.force:
            print("Error: GUI tracking is already initialized.")
            if branch_exists:
                print(f"  Branch '{VANILLA_BRANCH}' exists.")
            if tracking_exists:
                print(f"  {TRACKING_DIR_NAME}/ exists.")
            print("Use 'refresh' to update existing tracking, "
                  "or 'init --force' to reset and re-initialize.")
            return 1

        print("Force re-init: clearing existing tracking state...")
        if tracking_exists:
            tracked = run_git(["ls-files", TRACKING_DIR_NAME],
                              check=False) or ""
            if tracked.strip():
                run_git(["rm", "-rf", TRACKING_DIR_NAME])
                run_git(["commit", "-m",
                         "Reset GUI tracking before re-initialization"])
            # git clean handles Windows/OneDrive better than shutil for leftovers + empty dirs.
            run_git(["clean", "-fdx", "--", TRACKING_DIR_NAME],
                    check=False)
            if os.path.isdir(TRACKING_DIR):
                _force_rmtree(TRACKING_DIR)
        if branch_exists:
            run_git(["branch", "-D", VANILLA_BRANCH])
        if _vanilla_merged_ref_exists():
            run_git(["branch", "-D", MERGED_BRANCH])

    # Scan
    print("Scanning mod GUI files...")
    mod_defs = _scan_definitions(ROOT_DIR, GUI_SOURCES)
    print(f"  Found {len(mod_defs)} definition(s) in mod.")

    print("Scanning vanilla GUI files...")
    vanilla_defs = _scan_definitions(game_dir, GUI_SOURCES)
    print(f"  Found {len(vanilla_defs)} definition(s) in vanilla.")

    overrides = _find_overrides(mod_defs, vanilla_defs)
    constants = _link_constants(mod_defs, vanilla_defs, overrides)
    total = len(overrides) + len(constants)
    if not total:
        print("\nNo overrides detected. Your mod does not override "
              "any vanilla GUI types, templates, widgets, or constants.")
        return 0

    n_types = sum(1 for m, _ in overrides if m.kind == "type")
    n_tmpls = sum(1 for m, _ in overrides if m.kind == "template")
    n_consts = len(constants)
    print(f"\nDetected {total} override(s) "
          f"({n_types} type(s), {n_tmpls} template(s), "
          f"{n_consts} constant(s)):")
    for md, _ in overrides:
        print(f"  {md.kind}: {md.name}  ({md.source_file})")
    for md, vd in constants:
        print(f"  constant: @{md.name}  "
              f"({md.source_file} <- {vd.source_file})")

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
        header = _make_tracking_header(vd.source_file, md.source_file)
        vanilla_files[tp] = header + vd.text + "\n"

    for md, vd in constants:
        key = _constant_tracking_key(md.source_file, vd.source_file, md.name)
        tp = _constant_tracking_path(md.source_file, vd.source_file, md.name)
        manifest["definitions"][key] = {
            "kind": "constant",
            "name": md.name,
            "mod_file": md.source_file,
            "vanilla_file": vd.source_file,
            "tracking_path": tp,
        }
        header = _make_tracking_header(vd.source_file, md.source_file)
        vanilla_files[tp] = header + vd.text + "\n"

    # 1. Create gui/vanilla orphan branch (via plumbing, no checkout)
    version = _resolve_game_version(args, is_init=True)
    print(f"\nCreating {VANILLA_BRANCH} branch...")
    new_vanilla_sha = _update_vanilla_branch(
        vanilla_files,
        "Initialize vanilla GUI definitions",
        version=version,
        force_push=args.force,
        beta=getattr(args, "beta", False))

    # 2. Anchor gui/vanilla-merged at the same commit for the next merge base.
    run_git(["update-ref", f"refs/heads/{MERGED_BRANCH}", new_vanilla_sha])
    _push_refs([MERGED_BRANCH], force=args.force)

    # 3. Write tracking files with mod content + manifest
    for md, vd in overrides:
        tp = _tracking_path(md.kind, md.name)
        header = _make_tracking_header(vd.source_file, md.source_file)
        _write_tracking_file(tp, header + md.text + "\n")
    for md, vd in constants:
        tp = _constant_tracking_path(md.source_file, vd.source_file, md.name)
        header = _make_tracking_header(vd.source_file, md.source_file)
        _write_tracking_file(tp, header + md.text + "\n")
    _save_manifest(manifest)

    # 4. Commit
    run_git(["add", TRACKING_DIR_NAME + "/"])
    run_git(["commit", "-m",
             _versioned_message(
                 f"Initialize GUI tracking with {total} definition(s)",
                 version)])

    print(f"\nDone! Tracking {total} GUI override(s).")
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
    _ensure_vanilla_merged_ref()

    print("Scanning current vanilla GUI files...")
    vanilla_defs = _scan_definitions(game_dir, GUI_SOURCES)
    vanilla_map = {}
    vanilla_consts = {}
    for d in vanilla_defs:
        if d.kind == "constant":
            vanilla_consts.setdefault((d.source_file, d.name), d)
        else:
            vanilla_map.setdefault(_tracking_key(d.kind, d.name), d)

    changed = []
    removed = []

    # Compare against the merged baseline so an aborted merge still surfaces pending changes.
    base_ref = MERGED_BRANCH if _vanilla_merged_ref_exists() else VANILLA_BRANCH

    for key, entry in sorted(manifest["definitions"].items()):
        old = _read_from_branch(base_ref, entry["tracking_path"])
        if old is None:
            continue
        if key.startswith("constant:"):
            vd = vanilla_consts.get((entry["vanilla_file"], entry["name"]))
        else:
            vd = vanilla_map.get(key)
        if vd is not None:
            new = vd.text + "\n"
            if _body_hash(old) != _body_hash(new):
                changed.append((key, entry))
        else:
            removed.append((key, entry))

    pending_merge = (
        _vanilla_merged_ref_exists()
        and run_git(["rev-parse", VANILLA_BRANCH])
            != run_git(["rev-parse", MERGED_BRANCH])
    )

    if not changed and not removed:
        if pending_merge:
            print("\nPrevious merge is unfinished "
                  f"({VANILLA_BRANCH} is ahead of {MERGED_BRANCH}).")
            print("Run 'gui_update.py apply' to finalize.")
        else:
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

    if pending_merge:
        print(f"\nNote: {VANILLA_BRANCH} is ahead of {MERGED_BRANCH} from a "
              "previous unfinished merge; running merge will resume it.")
    print("\nRun 'gui_update.py merge' to incorporate these changes.")
    return 0


def cmd_merge(args):
    manifest = _load_manifest()
    if manifest is None:
        print("Not initialized. Run 'gui_update.py init' first.")
        return 1
    if not _vanilla_branch_exists():
        print(f"Error: {VANILLA_BRANCH} branch not found.")
        return 1

    _ensure_clean_worktree()
    _ensure_no_merge()
    _ensure_vanilla_merged_ref()

    repull = getattr(args, "repull", False)
    just_advanced = _advance_merged_ref_if_absorbed()
    vanilla_sha = run_git(["rev-parse", VANILLA_BRANCH])
    merged_sha = run_git(["rev-parse", MERGED_BRANCH])
    # An unfinished merge leaves gui/vanilla ahead of gui/vanilla-merged.
    # Resuming reuses that tip and skips the game scan; --repull forces a
    # fresh scan that overwrites the pending commit instead.
    pending = vanilla_sha != merged_sha
    resuming = pending and not repull
    if not resuming:
        game_dir = _resolve_game_dir(args)

    # Sync tracking from mod state. Skip if just advanced — tracking holds
    # the resolution and mod files may still be pre-apply.
    if just_advanced:
        print("Skipping mod-state sync.")
    else:
        print("Syncing tracking files from current mod content...")
        mod_defs = _scan_definitions(ROOT_DIR, GUI_SOURCES, assert_unique=True)
        mod_map = {}
        mod_consts = {}
        for d in mod_defs:
            if d.kind == "constant":
                mod_consts.setdefault((d.source_file, d.name), d)
            else:
                mod_map.setdefault(_tracking_key(d.kind, d.name), d)

        synced = 0
        removed_keys = []
        new_definitions = {}
        for key, entry in manifest["definitions"].items():
            if key.startswith("constant:"):
                md = mod_consts.get((entry["mod_file"], entry["name"]))
            else:
                md = mod_map.get(key)
            if md is not None:
                if (not key.startswith("constant:")
                        and entry["mod_file"] != md.source_file):
                    entry["mod_file"] = md.source_file
                new_definitions[key] = entry
                tp = entry["tracking_path"]
                header = _make_tracking_header(
                    entry["vanilla_file"], entry["mod_file"])
                new_text = header + md.text + "\n"
                abs_tp = os.path.join(ROOT_DIR, tp.replace("/", os.sep))
                old_text = None
                if os.path.isfile(abs_tp):
                    with open(abs_tp, "r", encoding="utf-8-sig") as f:
                        old_text = f.read()
                if old_text != new_text:
                    _write_tracking_file(tp, new_text)
                    synced += 1
            else:
                removed_keys.append(key)
                abs_tp = os.path.join(
                    ROOT_DIR, entry["tracking_path"].replace("/", os.sep))
                if os.path.isfile(abs_tp):
                    os.remove(abs_tp)

        if synced or removed_keys:
            manifest["definitions"] = new_definitions
            _save_manifest(manifest)
            run_git(["add", "-A", TRACKING_DIR_NAME + "/"])
            parts = []
            if synced:
                parts.append(f"{synced} updated")
            if removed_keys:
                parts.append(f"{len(removed_keys)} removed")
            run_git(["commit", "-m",
                     "Sync tracking from mod state: " + ", ".join(parts)])
            if synced:
                print(f"  {synced} tracking file(s) updated.")
            if removed_keys:
                print(f"  {len(removed_keys)} stale entry(ies) removed:")
                for k in removed_keys:
                    print(f"    - {k}")
        else:
            print("  Tracking already in sync with mod.")

    if resuming:
        print(f"{VANILLA_BRANCH} is ahead of {MERGED_BRANCH} from an "
              "unfinished merge; resuming it without re-scanning vanilla.")
        new_vanilla_sha = vanilla_sha
        version = _last_vanilla_commit_version()
    else:
        # Build the new vanilla snapshot from current game files.
        print("Scanning current vanilla GUI files...")
        vanilla_defs = _scan_definitions(game_dir, GUI_SOURCES)
        vanilla_map = {}
        vanilla_consts = {}
        for d in vanilla_defs:
            if d.kind == "constant":
                vanilla_consts.setdefault((d.source_file, d.name), d)
            else:
                vanilla_map.setdefault(_tracking_key(d.kind, d.name), d)

        tracking_files = {}
        updated = 0
        for key, entry in manifest["definitions"].items():
            tp = entry["tracking_path"]
            if key.startswith("constant:"):
                vd = vanilla_consts.get((entry["vanilla_file"], entry["name"]))
            else:
                vd = vanilla_map.get(key)
            if vd is not None:
                header = _make_tracking_header(
                    entry["vanilla_file"], entry["mod_file"])
                new_content = header + vd.text + "\n"
                old_content = _read_from_branch(VANILLA_BRANCH, tp)
                tracking_files[tp] = new_content
                if (old_content is None
                        or _body_hash(old_content) != _body_hash(new_content)):
                    updated += 1

        if updated == 0 and not pending:
            print("Vanilla branch already up to date. Nothing to merge.")
            return 0

        if updated == 0:
            print(f"Re-pulled vanilla matches the pending {VANILLA_BRANCH} "
                  "commit; resuming it.")
            new_vanilla_sha = vanilla_sha
            version = _last_vanilla_commit_version()
        else:
            # Overwrite the pending commit to avoid a duplicate.
            parent_override = merged_sha if pending else None
            version = _resolve_game_version(args, is_init=False)
            verb = "Overwriting pending" if pending else "Updating"
            print(f"{verb} {VANILLA_BRANCH} ({updated} definition(s) "
                  "changed)...")
            new_vanilla_sha = _update_vanilla_branch(
                tracking_files,
                f"Update {updated} vanilla GUI definition(s)",
                version=version,
                beta=getattr(args, "beta", False),
                parent_override=parent_override)

    # Per-file three-way merge using gui/vanilla-merged as base and
    # gui/vanilla as theirs.
    print("Running three-way merge...")
    conflicts = []
    clean_paths = []

    for key, entry in manifest["definitions"].items():
        tp = entry["tracking_path"]
        abs_tp = os.path.join(ROOT_DIR, tp.replace("/", os.sep))

        base = _read_from_branch(MERGED_BRANCH, tp)
        theirs = _read_from_branch(VANILLA_BRANCH, tp)
        ours = None
        if os.path.isfile(abs_tp):
            with open(abs_tp, "r", encoding="utf-8-sig") as f:
                ours = f.read()

        if base is not None:
            base = base.replace("\r\n", "\n")
            if not base.endswith("\n"):
                base += "\n"
        if theirs is not None:
            theirs = theirs.replace("\r\n", "\n")
            if not theirs.endswith("\n"):
                theirs += "\n"
        if ours is not None:
            ours = ours.replace("\r\n", "\n")

        if theirs is None:
            # Vanilla removed this definition.
            if base is None or ours is None:
                continue
            if _body_hash(ours) == _body_hash(base):
                if os.path.isfile(abs_tp):
                    os.remove(abs_tp)
                clean_paths.append(tp)
            else:
                conflicts.append((tp, base, ours, None))
            continue

        if base is None:
            base = ""
        if ours is None:
            ours = ""

        if base == ours == theirs:
            continue

        merged, has_conflict = _three_way_merge_string(base, ours, theirs)
        if merged != ours:
            _write_tracking_file(tp, merged)
        if has_conflict:
            conflicts.append((tp, base, ours, theirs))
        elif merged != ours:
            clean_paths.append(tp)

    if conflicts:
        # Stage the clean files normally.
        for tp in clean_paths:
            run_git(["add", tp])
        # Stage conflicts at 1/2/3 so git GUIs offer the 3-way merge editor.
        for tp, base, ours, theirs in conflicts:
            _stage_merge_entries(tp, base, ours, theirs)
        # Set MERGE_HEAD/MERGE_MSG so the next git commit produces a 2-parent merge.
        affected = len(conflicts) + len(clean_paths)
        msg = _versioned_message(
            f"Merge vanilla GUI updates ({affected} definition(s))", version)
        _setup_merge_state(new_vanilla_sha, msg)

        print(f"\nConflicts in {len(conflicts)} file(s):")
        for tp, _, _, _ in conflicts:
            print(f"  {tp}")
        print("\nResolve the conflicts in your merge tool of choice, then run:")
        print("  python tools/gui_update.py apply")
        return 1

    # No conflicts: stage and commit as a regular single-parent commit.
    run_git(["add", TRACKING_DIR_NAME + "/"])
    diff_check = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=ROOT_DIR,
    )
    if diff_check.returncode != 0:
        run_git(["commit", "-m",
                 _versioned_message(
                     f"Merge vanilla GUI updates "
                     f"({len(clean_paths)} definition(s))",
                     version)])

    # Advance the bookmark to match gui/vanilla.
    run_git(["update-ref",
             f"refs/heads/{MERGED_BRANCH}", new_vanilla_sha])
    _push_refs([MERGED_BRANCH])

    if clean_paths:
        print(f"\nMerge completed cleanly ({len(clean_paths)} definition(s) updated).")
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

    _advance_merged_ref_if_absorbed()

    applied = 0
    errors = 0

    # Read all tracking files first so divergent constants get reported before any mod file is touched.
    const_groups = {}
    to_apply = []

    for key, entry in sorted(manifest["definitions"].items()):
        tp = entry["tracking_path"]
        abs_tp = os.path.join(ROOT_DIR, tp.replace("/", os.sep))

        if not os.path.isfile(abs_tp):
            print(f"  Warning: Tracking file missing: {tp}")
            continue

        with open(abs_tp, "r", encoding="utf-8-sig") as f:
            new_text = _strip_tracking_header(f.read()).rstrip("\n")

        if key.startswith("constant:"):
            const_groups.setdefault(
                (entry["mod_file"], entry["name"]), []
            ).append((key, entry, new_text))
        else:
            to_apply.append((key, entry, new_text))

    for (mod_file, name), items in const_groups.items():
        unique = set(it[2] for it in items)
        if len(unique) > 1:
            print(f"  Error: Divergent vanilla values for @{name} "
                  f"in {mod_file}:")
            for _k, e, t in items:
                print(f"    from {e['vanilla_file']}: {t}")
            errors += 1
            continue
        to_apply.append(items[0])

    for key, entry, new_text in to_apply:
        mod_file = entry["mod_file"]
        abs_mod = os.path.join(ROOT_DIR, mod_file.replace("/", os.sep))

        if not os.path.isfile(abs_mod):
            print(f"  Warning: Mod file not found: {mod_file}")
            errors += 1
            continue

        # Read mod file (detect line endings; BOM is always restored on write).
        with open(abs_mod, "rb") as f:
            raw = f.read()
        has_crlf = b"\r\n" in raw
        mod_text = raw.decode("utf-8-sig").replace("\r\n", "\n")
        # Any U+FEFF past byte 0 is a corruption artifact.
        mod_text = mod_text.replace("\ufeff", "")

        if not _assert_unique_top_level_defs(mod_text, mod_file):
            errors += 1
            continue

        if key.startswith("constant:"):
            kind = "constant"
            name = entry["name"]
            namespace = None
        else:
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

        if not _assert_unique_top_level_defs(result, mod_file):
            errors += 1
            continue

        if has_crlf:
            result = result.replace("\n", "\r\n")

        new_raw = b"\xef\xbb\xbf" + result.encode("utf-8")
        if new_raw == raw:
            continue

        with open(abs_mod, "wb") as f:
            f.write(new_raw)

        applied += 1
        print(f"  Applied: {key} -> {mod_file}")

    if errors:
        print(f"\n{errors} error(s) encountered.")
    if applied:
        print(f"\n{applied} definition(s) applied to mod files.")
        print("Review the changes and commit when ready.")
    elif not errors:
        print("\nAll mod files already up to date.")

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
    constants = _link_constants(mod_defs, vanilla_defs, overrides)
    new_keys = {}
    for md, vd in overrides:
        new_keys[_tracking_key(md.kind, md.name)] = (md, vd)
    for md, vd in constants:
        new_keys[_constant_tracking_key(
            md.source_file, vd.source_file, md.name)] = (md, vd)

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
        if md.kind == "constant":
            tp = _constant_tracking_path(
                md.source_file, vd.source_file, md.name)
            new_manifest["definitions"][key] = {
                "kind": "constant",
                "name": md.name,
                "mod_file": md.source_file,
                "vanilla_file": vd.source_file,
                "tracking_path": tp,
            }
        else:
            tp = _tracking_path(md.kind, md.name)
            new_manifest["definitions"][key] = {
                "namespace": md.namespace,
                "base_widget": md.base_widget,
                "mod_file": md.source_file,
                "vanilla_file": vd.source_file,
                "tracking_path": tp,
            }
        header = _make_tracking_header(vd.source_file, md.source_file)
        _write_tracking_file(tp, header + md.text + "\n")

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
    vanilla_consts = {}
    for d in vanilla_defs:
        if d.kind == "constant":
            vanilla_consts.setdefault((d.source_file, d.name), d)
        else:
            vanilla_map.setdefault(_tracking_key(d.kind, d.name), d)
    vanilla_files = {}
    for key, entry in new_manifest["definitions"].items():
        if key.startswith("constant:"):
            vd = vanilla_consts.get((entry["vanilla_file"], entry["name"]))
        else:
            vd = vanilla_map.get(key)
        if vd is not None:
            header = _make_tracking_header(
                entry["vanilla_file"], entry["mod_file"])
            vanilla_files[entry["tracking_path"]] = (
                header + vd.text + "\n")
    version = _resolve_game_version(args, is_init=False)
    new_vanilla_sha = _update_vanilla_branch(
        vanilla_files, "Refresh vanilla GUI definitions", version=version,
        beta=getattr(args, "beta", False))

    # Refresh re-baselines tracking, so the bookmark moves to the new tip.
    run_git(["update-ref",
             f"refs/heads/{MERGED_BRANCH}", new_vanilla_sha])
    _push_refs([MERGED_BRANCH])

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
    if _vanilla_branch_exists() and _vanilla_merged_ref_exists():
        v = run_git(["rev-parse", VANILLA_BRANCH])
        m = run_git(["rev-parse", MERGED_BRANCH])
        print(f"  Merge bookmark:  "
              f"{'in sync' if v == m else 'pending merge'}")
    elif _vanilla_branch_exists():
        print(f"  Merge bookmark:  MISSING (will init on next merge)")
    print(f"  Tracked definitions: {len(defs)}")

    if not defs:
        return 0

    types = sorted(k for k in defs if k.startswith("type:"))
    templates = sorted(k for k in defs if k.startswith("template:"))
    constants = sorted(k for k in defs if k.startswith("constant:"))

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

    if constants:
        print(f"\n  Constants ({len(constants)}):")
        for key in constants:
            e = defs[key]
            print(f"    @{e['name']}")
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

    def add_version_arg(p):
        p.add_argument(
            "--game-version", "--gv", "-gv", dest="game_version",
            metavar="VERSION", default=None,
            help="Game version for the gui/vanilla commit subject "
                 "(e.g. 1.2.5). Overrides auto-detection and prompting.",
        )

    def add_beta_arg(p):
        p.add_argument(
            "--beta", "--early-access", "-b", "--b", dest="beta",
            action="store_true",
            help="Target the EU5 closed-beta install (Project Caesar "
                 "Review) instead of the live game.",
        )

    init_parser = sub.add_parser(
        "init", help="Initialize GUI tracking for this mod")
    init_parser.add_argument(
        "--force", action="store_true",
        help="Reset existing tracking state (deletes "
             f"{TRACKING_DIR_NAME}/, {VANILLA_BRANCH}, and "
             f"{MERGED_BRANCH}) before re-initializing.",
    )
    add_version_arg(init_parser)
    add_beta_arg(init_parser)
    check_parser = sub.add_parser("check",
                                  help="Check for vanilla GUI changes")
    add_beta_arg(check_parser)
    merge_parser = sub.add_parser(
        "merge", help="Update vanilla branch and merge changes")
    merge_parser.add_argument(
		"-r", "--repull", "--force-pull", dest="repull", action="store_true",
        help="Re-scan vanilla game files even when a previous merge is "
             "pending, overwriting the pending gui/vanilla commit instead "
             "of resuming it.",
    )
    add_version_arg(merge_parser)
    add_beta_arg(merge_parser)
    sub.add_parser("apply",
                   help="Apply resolved changes back to mod GUI files")
    refresh_parser = sub.add_parser(
        "refresh",
        help="Re-extract mod definitions into tracking files")
    add_version_arg(refresh_parser)
    add_beta_arg(refresh_parser)
    sub.add_parser("status",
                   help="Show tracking status")

    args = parser.parse_args()
    sys.exit(_COMMANDS[args.command](args))


if __name__ == "__main__":
    main()
