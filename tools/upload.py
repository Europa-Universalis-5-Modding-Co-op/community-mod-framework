import argparse
import json
import os
import re
import shutil
import stat
import sys
import time
from contextlib import contextmanager

import tomllib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEPENDENCIES_DIR = os.path.join(SCRIPT_DIR, "dependencies")
# Allow importing the bundled steamworks module from tools/dependencies/steamworks.
sys.path.insert(0, DEPENDENCIES_DIR)

from steamworks import STEAMWORKS
from steamworks.enums import EItemUpdateStatus, EResult, EWorkshopFileType

# --- User Configuration ---
SOURCES = [
    "in_game",
    "main_menu",
	"loading_screen"
    # "LICENSE", - example of adding a file to the release
]

# --- Path Setup ---
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.toml")
METADATA_PATH = os.path.join(ROOT_DIR, ".metadata", "metadata.json")
WORKSHOP_DESCRIPTION_PATH = os.path.join(ROOT_DIR, "assets", "workshop", "workshop-description.bbcode")
CHANGE_NOTES_PATH = os.path.join(ROOT_DIR, "assets", "workshop", "change-notes.bbcode")
TRANSLATIONS_DIR = os.path.join(ROOT_DIR, "assets", "workshop", "translations")
APP_ID = 3450310
CREATE_ITEM_TIMEOUT_SECONDS = 30
CREATE_ITEM_POLL_INTERVAL_SECONDS = 0.1
UPLOAD_TIMEOUT_SECONDS = 300
UPLOAD_POLL_INTERVAL_SECONDS = 0.5
CLEANUP_RETRY_DELAY_SECONDS = 3
CLEANUP_MAX_ATTEMPTS = 20
WORKSHOP_FILE_TYPE = EWorkshopFileType.COMMUNITY
SUBMODS_DIR_NAME = "submods"
WORKSHOP_TRANSLATION_FILENAME_RE = re.compile(r"^workshop_(.+)\.txt$")
CHANGE_NOTES_TRANSLATION_FILENAME_RE = re.compile(r"^change-notes_(.+)\.txt$")
WORKSHOP_TITLE_MARKER = "===WORKSHOP_TITLE==="
WORKSHOP_DESCRIPTION_MARKER = "===WORKSHOP_DESCRIPTION==="
WORKSHOP_NO_TRANSLATE_BELOW = "--NO-TRANSLATE-BELOW--"
WORKSHOP_ITEM_ID_TOKEN = "$item-id$"
MAX_DESCRIPTION_LENGTH = 8000
UPLOAD_MOD_DEFAULT_KEY = "upload_mod_by_default"
UPLOAD_WORKSHOP_PAGES_DEFAULT_KEY = "upload_workshop_pages_by_default"
UPLOAD_SUBMODS_DEFAULT_KEY = "upload_submods_by_default"
UPLOAD_ON_VERSION_CHANGE_KEY = "upload_only_on_version_change"
UPLOAD_CHANGE_NOTES_DEFAULT_KEY = "upload_change_notes_by_default"
UPLOAD_VERSIONS_PATH = os.path.join(DEPENDENCIES_DIR, ".upload_versions.json")
UPLOAD_VERSIONS_FILE_VERSION = 1
CHANGE_NOTES_VERSION_RE = re.compile(
    r"^(?:(?P<hash>#)\s*|(?P<bb>\[b\]))v(?P<ver>.+?)(?P<tail>:\s*|\s*)(?:\[/b\])?$"
)

LANGUAGE_TO_STEAM = {
    "english": "english",
    "french": "french",
    "german": "german",
    "spanish": "spanish",
    "polish": "polish",
    "russian": "russian",
    "simp_chinese": "schinese",
    "turkish": "turkish",
    "braz_por": "brazilian",
    "japanese": "japanese",
    "korean": "koreana",
}

def _on_rm_error(func, path, exc_info):
    exc = exc_info[1]
    winerror = getattr(exc, "winerror", None)
    errno = getattr(exc, "errno", None)
    if winerror == 32 or errno == 16:
        raise exc
    os.chmod(path, stat.S_IWRITE)
    func(path)

def _parse_int(value, label, allow_zero=False):
    """Parse a positive integer (or zero when allowed) with a friendly error message."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        print(f"Error: Invalid {label} '{value}'. Expected an integer.")
        return None
    if parsed == 0 and allow_zero:
        return 0
    if parsed <= 0:
        print(f"Error: Invalid {label} '{value}'. Expected a positive integer.")
        return None
    return parsed

def load_config(config_path):
    """Load config.toml values needed for Workshop uploads."""
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}")
        return None
    except Exception as e:
        print(f"Error reading config file: {e}")
        return None

    return data

def load_workshop_item_id(config, key, label):
    """Load the workshop item ID from config data."""
    upload_item_id = config.get(key)
    if upload_item_id is None:
        print(f"Error: {key} not set in config.toml.")
        return None

    return _parse_int(upload_item_id, label, allow_zero=True)

def load_dev_name(config):
    """Load an optional dev mod name override from config data."""
    dev_name = config.get("workshop_dev_name")
    if dev_name is None:
        return None
    dev_name = str(dev_name).strip()
    return dev_name if dev_name else None

def load_source_language(config):
    """Load and validate source_language used for workshop page uploads."""
    source_language = config.get("source_language")
    if source_language is None:
        print("Error: source_language not set in config.toml.")
        return None

    source_language = str(source_language).strip().lower()
    if source_language not in LANGUAGE_TO_STEAM:
        valid = ", ".join(sorted(LANGUAGE_TO_STEAM.keys()))
        print(f"Error: Unsupported source_language '{source_language}'.")
        print(f"Supported values: {valid}")
        return None

    return source_language

def load_required_bool(config, key):
    """Load a required boolean config setting."""
    value = config.get(key)
    if value is None:
        print(f"Error: {key} not set in config.toml.")
        return None
    if not isinstance(value, bool):
        print(f"Error: {key} must be true or false in config.toml.")
        return None
    return value

def load_optional_bool(config, key, default):
    """Load an optional boolean config setting."""
    if key not in config:
        return default
    value = config.get(key)
    if not isinstance(value, bool):
        print(f"Error: {key} must be true or false in config.toml.")
        return None
    return value

def resolve_upload_targets(args, config):
    """Resolve whether to upload mod, workshop pages, submods, and change notes."""
    if args.mod or args.workshop_pages or args.submods or args.change_notes:
        # CLI target flags override config defaults for this run.
        return args.mod, args.workshop_pages, args.submods, args.change_notes

    upload_mod = load_required_bool(config, UPLOAD_MOD_DEFAULT_KEY)
    if upload_mod is None:
        return None, None, None, None

    upload_workshop_pages = load_required_bool(config, UPLOAD_WORKSHOP_PAGES_DEFAULT_KEY)
    if upload_workshop_pages is None:
        return None, None, None, None

    upload_submods = load_optional_bool(config, UPLOAD_SUBMODS_DEFAULT_KEY, False)
    if upload_submods is None:
        return None, None, None, None

    upload_change_notes = load_optional_bool(config, UPLOAD_CHANGE_NOTES_DEFAULT_KEY, False)
    if upload_change_notes is None:
        return None, None, None, None

    return upload_mod, upload_workshop_pages, upload_submods, upload_change_notes

def load_upload_versions(path):
    """Load cached uploaded versions for main mod and submods."""
    if not os.path.exists(path):
        return {"version": UPLOAD_VERSIONS_FILE_VERSION, "entries": {}}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to read upload version cache '{path}': {e}. Rebuilding.")
        return {"version": UPLOAD_VERSIONS_FILE_VERSION, "entries": {}}

    if not isinstance(data, dict):
        print(f"Warning: Upload version cache '{path}' is invalid. Rebuilding.")
        return {"version": UPLOAD_VERSIONS_FILE_VERSION, "entries": {}}

    if data.get("version") != UPLOAD_VERSIONS_FILE_VERSION:
        print(f"Warning: Upload version cache '{path}' has unsupported version. Rebuilding.")
        return {"version": UPLOAD_VERSIONS_FILE_VERSION, "entries": {}}

    entries = data.get("entries")
    if not isinstance(entries, dict):
        print(f"Warning: Upload version cache '{path}' has invalid entries. Rebuilding.")
        return {"version": UPLOAD_VERSIONS_FILE_VERSION, "entries": {}}

    return data

def save_upload_versions(path, data):
    """Persist uploaded version cache atomically."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(temp_path, path)

def load_metadata_version(metadata_path, label):
    """Read and validate metadata.json version."""
    try:
        with open(metadata_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Metadata file not found for {label}: {metadata_path}")
        return None
    except Exception as e:
        print(f"Error: Failed reading metadata for {label} at '{metadata_path}': {e}")
        return None

    version = data.get("version")
    if version is None:
        print(f"Error: Missing 'version' in metadata for {label}: {metadata_path}")
        return None

    version = str(version).strip()
    if not version:
        print(f"Error: Blank 'version' in metadata for {label}: {metadata_path}")
        return None

    return version

def should_upload_for_version(version_cache, cache_key, current_version):
    """Return True when upload is needed for a version-gated entry."""
    entries = version_cache.setdefault("entries", {})
    return entries.get(cache_key) != current_version

def set_uploaded_version(version_cache, cache_key, uploaded_version):
    """Update cached uploaded version for an entry."""
    entries = version_cache.setdefault("entries", {})
    entries[cache_key] = uploaded_version

def _replace_value_preserve_comment(line, key, value):
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)([^#]*?)(\s*)(#.*)?$")
    match = pattern.match(line)
    if not match:
        return f"{key} = {value}"
    prefix, _old_value, gap, comment = match.groups()
    comment = comment or ""
    if comment and not gap:
        gap = " "
    elif not comment:
        gap = ""
    return f"{prefix}{value}{gap}{comment}".rstrip()

def update_config_value(config_path, key, value):
    """Update a single key in config.toml while preserving comments."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}")
        return False
    except Exception as e:
        print(f"Error reading config file: {e}")
        return False

    updated = False
    for idx, line in enumerate(lines):
        if re.match(rf"^\s*{re.escape(key)}\s*=", line):
            lines[idx] = _replace_value_preserve_comment(line, key, value)
            updated = True
            break

    if not updated:
        lines.append(f"{key} = {value}")

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        print(f"Error writing config file: {e}")
        return False

    return True

@contextmanager
def steamworks_session():
    cwd_before = os.getcwd()
    try:
        os.chdir(DEPENDENCIES_DIR)
        steam = STEAMWORKS()
        steam.initialize()
        yield steam
    finally:
        os.chdir(cwd_before)

def create_workshop_item(steam):
    result_holder = {"done": False, "result": None}

    def on_created(result):
        result_holder["done"] = True
        result_holder["result"] = result

    workshop = steam.Workshop
    workshop.CreateItem(APP_ID, WORKSHOP_FILE_TYPE, callback=on_created)

    start = time.time()
    while not result_holder["done"]:
        steam.run_callbacks()
        time.sleep(CREATE_ITEM_POLL_INTERVAL_SECONDS)
        if time.time() - start > CREATE_ITEM_TIMEOUT_SECONDS:
            print("Error: Timed out while waiting for Workshop item creation.")
            return None

    result = result_holder["result"]
    if result is None:
        print("Error: Workshop item creation did not return a result.")
        return None

    try:
        result_code = EResult(result.result)
    except ValueError:
        print(f"Error: Workshop item creation failed with unknown result code {result.result}.")
        return None

    if result_code != EResult.OK:
        print(f"Error: Workshop item creation failed with result {result_code.name}.")
        return None

    if result.userNeedsToAcceptWorkshopLegalAgreement:
        print("Warning: You must accept the Workshop legal agreement in Steam before uploading.")

    new_id = int(result.publishedFileId)
    if new_id <= 0:
        print("Error: Workshop item creation returned an invalid published file id.")
        return None

    print(f"Created new Workshop item: {new_id}")
    return new_id

def ensure_item_id(steam, item_id, config_path, config_key):
    if item_id != 0:
        return item_id

    print("Workshop item id is 0; creating a new Workshop item...")
    new_id = create_workshop_item(steam)
    if new_id is None:
        return None

    if update_config_value(config_path, config_key, new_id):
        print(f"Updated {config_key} in {config_path}.")
    else:
        print(
            f"Warning: Failed to update {config_path}. "
            f"Please set {config_key} = {new_id} manually."
        )

    return new_id

def cleanup_release_dir(release_dir):
    if not release_dir:
        return False
    release_dir = os.path.abspath(release_dir)
    if not os.path.isdir(release_dir):
        return False
    if release_dir == ROOT_DIR:
        print(f"Warning: Refusing to remove release folder at root: {release_dir}")
        return False
    if os.path.dirname(release_dir) != os.path.dirname(ROOT_DIR):
        print(f"Warning: Refusing to remove release folder outside repo parent: {release_dir}")
        return False

    for attempt in range(1, CLEANUP_MAX_ATTEMPTS + 1):
        try:
            shutil.rmtree(release_dir, onerror=_on_rm_error)
            print(f"Removed release folder: {release_dir}")
            return True
        except OSError as e:
            winerror = getattr(e, "winerror", None)
            errno = getattr(e, "errno", None)
            if winerror == 32 or errno == 16:
                if attempt == CLEANUP_MAX_ATTEMPTS:
                    print(f"Warning: Release folder still in use: {release_dir}")
                    return False
                time.sleep(CLEANUP_RETRY_DELAY_SECONDS)
                continue
            print(f"Warning: Failed to remove release folder: {e}")
            return False

    return False

def _parse_submod_blocks(lines):
    blocks = []
    current = None

    def finalize(end_index):
        nonlocal current
        if current is None:
            return
        current["end"] = end_index
        blocks.append(current)
        current = None

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[[") and stripped.endswith("]]"):
            finalize(idx - 1)
            if stripped == "[[submods]]":
                current = {
                    "start": idx,
                    "end": None,
                    "mod_id": None,
                    "mod_id_line": None,
                    "workshop_id_line": None
                }
            continue

        if current is None:
            continue

        match = re.match(r"^\s*mod_id\s*=\s*(.+?)(\s*#.*)?$", line)
        if match:
            value = match.group(1).strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            current["mod_id"] = value
            current["mod_id_line"] = idx
            continue

        match = re.match(r"^\s*workshop_id\s*=\s*(.+?)(\s*#.*)?$", line)
        if match:
            current["workshop_id_line"] = idx
            continue

    finalize(len(lines) - 1)
    return blocks

def update_submod_entry(config_path, mod_id, workshop_id):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}")
        return False
    except Exception as e:
        print(f"Error reading config file: {e}")
        return False

    blocks = _parse_submod_blocks(lines)
    target = None
    for block in blocks:
        if block["mod_id"] == mod_id:
            target = block
            break

    if target:
        if target["workshop_id_line"] is not None:
            idx = target["workshop_id_line"]
            lines[idx] = _replace_value_preserve_comment(lines[idx], "workshop_id", workshop_id)
        else:
            insert_at = target["mod_id_line"] + 1 if target["mod_id_line"] is not None else target["start"] + 1
            lines.insert(insert_at, f"workshop_id = {workshop_id}")
    else:
        if lines and lines[-1].strip():
            lines.append("")
        escaped_mod_id = str(mod_id).replace('"', '\\"')
        lines.append("[[submods]]")
        lines.append(f'mod_id = "{escaped_mod_id}"')
        lines.append(f"workshop_id = {workshop_id}")

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        print(f"Error writing config file: {e}")
        return False

    return True

def load_submods_config(config):
    entries = config.get("submods") or []
    mapping = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        mod_id = entry.get("mod_id")
        workshop_id = entry.get("workshop_id")
        if mod_id is None or workshop_id is None:
            continue
        mod_id = str(mod_id).strip()
        if not mod_id or mod_id in mapping:
            continue
        parsed_id = _parse_int(workshop_id, f"workshop id for {mod_id}", allow_zero=True)
        if parsed_id is None:
            continue
        mapping[mod_id] = parsed_id
    return mapping

def _load_submod_metadata(mod_dir):
    meta_path = os.path.join(mod_dir, ".metadata", "metadata.json")
    if not os.path.exists(meta_path):
        print(f"Warning: Missing metadata.json for submod at {mod_dir}.")
        return None
    try:
        with open(meta_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to read submod metadata '{meta_path}': {e}")
        return None

    mod_id = data.get("id")
    if not mod_id:
        print(f"Warning: Submod metadata missing 'id' at {meta_path}.")
        return None
    mod_id = str(mod_id).strip()
    if not mod_id:
        print(f"Warning: Submod metadata 'id' is blank at {meta_path}.")
        return None

    name = data.get("name")
    name = str(name) if name is not None else None
    if name is not None and not name:
        name = None

    version = data.get("version")
    version = str(version).strip() if version is not None else None
    if version == "":
        version = None

    return {
        "id": mod_id,
        "name": name,
        "version": version,
        "root": mod_dir,
        "thumbnail": os.path.join(mod_dir, ".metadata", "thumbnail.png")
    }

def ensure_submod_item_id(steam, mod_id, workshop_id, config_path):
    if workshop_id and workshop_id != 0:
        return workshop_id

    print(f"Submod '{mod_id}' has no Workshop id; creating a new Workshop item...")
    new_id = create_workshop_item(steam)
    if new_id is None:
        return None

    if update_submod_entry(config_path, mod_id, new_id):
        print(f"Updated submods list in {config_path} for '{mod_id}'.")
    else:
        print(
            f"Warning: Failed to update {config_path}. "
            f"Please add workshop_id = {new_id} for mod_id = '{mod_id}'."
        )

    return new_id

def upload_submods(steam, config, version_gate_enabled=False, version_cache=None, upload_change_notes=False):
    submods_root = os.path.join(ROOT_DIR, SUBMODS_DIR_NAME)
    if not os.path.isdir(submods_root):
        print(f"Warning: submods folder not found: {submods_root}")
        return True, False

    mapping = load_submods_config(config)
    success = True
    cache_changed = False

    entries = sorted(os.listdir(submods_root))
    if not entries:
        print(f"Warning: No submods found in {submods_root}.")
        return True, False

    for entry in entries:
        mod_dir = os.path.join(submods_root, entry)
        if not os.path.isdir(mod_dir):
            continue

        meta = _load_submod_metadata(mod_dir)
        if meta is None:
            success = False
            continue

        mod_id = meta["id"]
        version = meta.get("version")
        cache_key = f"submod:{mod_id}"

        if version_gate_enabled:
            if not version:
                print(
                    f"Error: upload_only_on_version_change is enabled, "
                    f"but submod '{mod_id}' is missing metadata.version."
                )
                success = False
                continue
            if version_cache is None:
                print("Error: Internal version cache not provided for submod upload gating.")
                return False, cache_changed
            if not should_upload_for_version(version_cache, cache_key, version):
                print(f"Skipping submod '{mod_id}': version '{version}' already uploaded.")
                continue

        workshop_id = mapping.get(mod_id, 0)
        workshop_id = _parse_int(workshop_id, f"workshop id for {mod_id}", allow_zero=True)
        if workshop_id is None:
            success = False
            continue

        workshop_id = ensure_submod_item_id(steam, mod_id, workshop_id, CONFIG_PATH)
        if workshop_id is None:
            success = False
            continue
        mapping[mod_id] = workshop_id

        title = meta["name"]
        if title is None:
            print(f"Warning: Submod '{mod_id}' has no name; Workshop title will not be updated.")

        preview_path = meta["thumbnail"]
        if not os.path.exists(preview_path):
            preview_path = None

        if not upload_release(steam, meta["root"], preview_path, workshop_id, title):
            success = False
            continue

        if upload_change_notes:
            submod_change_notes_path = os.path.join(mod_dir, "workshop", "change-notes.bbcode")
            submod_change_note = load_change_notes(submod_change_notes_path, workshop_id, version=version)
            if submod_change_note is None:
                print(f"Warning: No change notes found for submod '{mod_id}' version '{version}'. Skipping change notes.")
            else:
                handle = steam.Workshop.StartItemUpdate(APP_ID, workshop_id)
                if not handle:
                    print(f"Error: StartItemUpdate failed for submod '{mod_id}' change note.")
                    success = False
                    continue
                if not _submit_and_wait(steam, handle, submod_change_note):
                    print(f"Error: Change note update failed for submod '{mod_id}'.")
                    success = False
                    continue
                print(f"Change note submitted for submod '{mod_id}'.")

        if version_gate_enabled:
            set_uploaded_version(version_cache, cache_key, version)
            cache_changed = True

    return success, cache_changed

def _normalize_release_title(raw_name):
    title = str(raw_name)
    if title.endswith(" Dev"):
        title = title[:-4].rstrip()
    return title.strip()

def build_release(dev_mode=False, dev_name=None):
    # --- Generate Release Folder Name ---
    dev_meta_path = os.path.join(ROOT_DIR, ".metadata", "metadata.json")

    if os.path.exists(dev_meta_path):
        with open(dev_meta_path, "r", encoding="utf-8-sig") as f:
            meta_data = json.load(f)

        raw_name = meta_data["name"]
        resolved_dev_name = dev_name if dev_mode and dev_name else raw_name
        workshop_title = (
            str(resolved_dev_name).strip()
            if dev_mode
            else _normalize_release_title(raw_name)
        )
        base_name = resolved_dev_name if dev_mode else raw_name
        clean_name = base_name.removesuffix(" Dev")

        clean_name = clean_name.lower().replace(" ", "-")
        target_folder_name = f"{clean_name}-dev" if dev_mode else f"{clean_name}-release"
    else:
        raise FileNotFoundError(f"Metadata file not found at {dev_meta_path}")

    release_dir = os.path.join(os.path.dirname(ROOT_DIR), target_folder_name)

    # --- Script ---

    # 1. Clean and Recreate Release Directory
    if os.path.exists(release_dir):
        shutil.rmtree(release_dir, onerror=_on_rm_error)

    os.makedirs(release_dir)

    # 2. Copy Sources directly to Release Directory
    for item in SOURCES:
        src_path = os.path.join(ROOT_DIR, item)
        dest_path = os.path.join(release_dir, item)

        if os.path.exists(src_path):
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            else:
                shutil.copy(src_path, dest_path)

    # 3. Generate Release Metadata
    dest_meta_dir = os.path.join(release_dir, ".metadata")
    dest_meta_path = os.path.join(dest_meta_dir, "metadata.json")

    if not os.path.exists(dest_meta_dir):
        os.makedirs(dest_meta_dir)

    with open(dev_meta_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if dev_mode:
        data["name"] = resolved_dev_name
    else:
        data["name"] = data["name"].removesuffix(" Dev")
        data["id"] = data["id"].removesuffix(".dev")

    with open(dest_meta_path, "w", encoding="utf-8-sig") as f:
        json.dump(data, f, indent=4)

    # 4. Handle Thumbnail
    thumb_release = os.path.join(ROOT_DIR, ".metadata", "thumbnail-release.png")
    thumb_std = os.path.join(ROOT_DIR, ".metadata", "thumbnail.png")
    thumb_dest = os.path.join(dest_meta_dir, "thumbnail.png")

    if dev_mode:
        if os.path.exists(thumb_std):
            shutil.copy(thumb_std, thumb_dest)
        else:
            thumb_dest = None
    else:
        if os.path.exists(thumb_release):
            shutil.copy(thumb_release, thumb_dest)
        elif os.path.exists(thumb_std):
            shutil.copy(thumb_std, thumb_dest)
        else:
            thumb_dest = None

    return (
        os.path.abspath(release_dir),
        os.path.abspath(thumb_dest) if thumb_dest else None,
        workshop_title
    )

def _submit_and_wait(steam, handle, change_note="", show_progress=False):
    """Submit an item update and block until Steam finishes processing it."""
    workshop = steam.Workshop
    result_holder = {"done": False, "result": None}

    def on_updated(result):
        result_holder["done"] = True
        result_holder["result"] = result

    workshop.SubmitItemUpdate(handle, change_note, callback=on_updated, override_callback=True)

    last_status = None
    last_progress_line = False
    start = time.time()
    while not result_holder["done"]:
        steam.run_callbacks()
        if show_progress:
            progress = workshop.GetItemUpdateProgress(handle)
            status = progress["status"]
            if status != EItemUpdateStatus.INVALID:
                if status == EItemUpdateStatus.UPLOADING_CONTENT and progress["total"] > 0:
                    pct = progress["progress"] * 100
                    mb_done = progress["processed"] / (1024 * 1024)
                    mb_total = progress["total"] / (1024 * 1024)
                    print(f"\r  Uploading Content... {pct:.0f}% ({mb_done:.1f} / {mb_total:.1f} MB)   ", end="", flush=True)
                    last_progress_line = True
                elif status != last_status:
                    if last_progress_line:
                        print()
                        last_progress_line = False
                    status_label = status.name.replace("_", " ").title()
                    print(f"  {status_label}...")
                last_status = status
        time.sleep(UPLOAD_POLL_INTERVAL_SECONDS)
        if time.time() - start > UPLOAD_TIMEOUT_SECONDS:
            if last_progress_line:
                print()
            print(f"Error: Upload timed out after {UPLOAD_TIMEOUT_SECONDS} seconds.")
            return False

    if last_progress_line:
        print()

    result = result_holder["result"]
    if result is None:
        print("Error: Workshop update did not return a result.")
        return False

    try:
        result_code = EResult(result.result)
    except ValueError:
        print(f"Error: Workshop update failed with unknown result code {result.result}.")
        return False

    if result_code != EResult.OK:
        print(f"Error: Workshop update failed with result {result_code.name}.")
        return False

    if result.userNeedsToAcceptWorkshopLegalAgreement:
        print("Warning: You must accept the Workshop legal agreement in Steam.")

    return True

def upload_release(steam, content_dir, preview_path, item_id, workshop_title=None):
    if not os.path.isdir(content_dir):
        print(f"Error: Release directory not found: {content_dir}")
        return False

    workshop = steam.Workshop
    handle = workshop.StartItemUpdate(APP_ID, item_id)
    if not handle:
        print("Error: StartItemUpdate failed. Check app ID and item ID.")
        return False

    if workshop_title:
        title_result = workshop.SetItemTitle(handle, workshop_title)
        if title_result is False:
            print("Error: SetItemTitle failed.")
            return False

    content_result = workshop.SetItemContent(handle, content_dir)
    if content_result is False:
        print("Error: SetItemContent failed.")
        return False

    if preview_path:
        preview_result = workshop.SetItemPreview(handle, preview_path)
        if preview_result is False:
            print("Error: SetItemPreview failed.")
            return False

    print("Workshop update submitted. Waiting for upload to complete...")
    if not _submit_and_wait(steam, handle, "", show_progress=True):
        return False

    print("Workshop update completed successfully.")
    return True

def read_text(path):
    """Read a UTF-8 text file, returning None on missing/failed reads."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Warning: Failed to read '{path}': {e}")
        return None

def parse_change_notes_entry(text, version=None):
    """Extract a single versioned entry from change notes text.

    If version is None, returns the latest (topmost) entry.
    Returns None if no version headers are found or no entry matches the requested version.

    Supports two header formats:
    - Markdown: ``# v1.0:`` (colon prepends ``[b]v1.0:[/b]``; no colon returns body only)
    - BBCode: ``[b]v1.0:[/b]`` or ``[b]v1.0[/b]`` (always prepends the header as-is)
    """
    entries = []
    current_version = None
    current_has_colon = False
    current_is_bb = False
    current_lines = []

    for line in text.splitlines(keepends=True):
        m = CHANGE_NOTES_VERSION_RE.match(line.strip())
        if m:
            if current_version is not None:
                entries.append((current_version, current_has_colon, current_is_bb, "".join(current_lines).strip()))
            current_version = m.group('ver').strip()
            current_has_colon = ":" in m.group('tail')
            current_is_bb = m.group('bb') is not None
            current_lines = []
        elif current_version is not None:
            current_lines.append(line)

    if current_version is not None:
        entries.append((current_version, current_has_colon, current_is_bb, "".join(current_lines).strip()))

    if not entries:
        return None

    target = entries[0] if version is None else next(
        (e for e in entries if e[0] == version), None
    )
    if target is None:
        return None

    entry_version, has_colon, is_bb, content = target
    if is_bb or has_colon:
        colon = ":" if has_colon else ""
        header = f"[b]v{entry_version}{colon}[/b]"
        return f"{header}\n{content}" if content else header
    return content or None

def get_latest_change_notes_version(text):
    """Return the version string from the first # v header, or None if unversioned."""
    if text is None:
        return None
    for line in text.splitlines():
        m = CHANGE_NOTES_VERSION_RE.match(line.strip())
        if m:
            return m.group('ver').strip()
    return None

def load_change_notes(path, item_id, version=None):
    """Load change notes from a bbcode file.

    Returns empty string if file is missing/empty.
    Returns None if version headers exist but no entry matches the requested version.
    """
    text = read_text(path)
    if text is None or not text.strip():
        return ""
    entry = parse_change_notes_entry(text, version=version)
    if entry is None:
        return None
    if not entry.strip():
        return ""
    return apply_workshop_item_id(entry, item_id)

def load_workshop_source_title(dev_mode=False, dev_name=None):
    """Load workshop title from metadata, applying dev/release naming rules."""
    try:
        with open(METADATA_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Warning: Metadata file not found: {METADATA_PATH}")
        return None
    except Exception as e:
        print(f"Warning: Failed to read metadata file '{METADATA_PATH}': {e}")
        return None

    raw_title = data.get("name")
    if raw_title is None:
        print(f"Warning: Metadata 'name' not found in {METADATA_PATH}")
        return None

    raw_title = str(raw_title).strip()
    if not raw_title:
        print(f"Warning: Metadata 'name' is blank in {METADATA_PATH}")
        return None

    if dev_mode:
        if dev_name:
            return str(dev_name).strip()
        return raw_title

    return _normalize_release_title(raw_title)

def parse_workshop_translation(text):
    """Extract title/description sections from a combined workshop translation file."""
    title = None
    description = None
    current = None
    buffer = []

    def flush():
        nonlocal title, description, buffer, current
        content = "".join(buffer)
        if current == "title":
            cleaned = content.strip()
            title = cleaned if cleaned else None
        elif current == "description":
            description = content
        buffer = []

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == WORKSHOP_TITLE_MARKER:
            flush()
            current = "title"
            continue
        if stripped == WORKSHOP_DESCRIPTION_MARKER:
            flush()
            current = "description"
            continue
        if current:
            buffer.append(line)

    flush()
    return title, description

def split_workshop_description(text):
    """Remove the no-translate marker line while keeping remaining source text."""
    if text is None:
        return None

    lines = text.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        if line.strip() == WORKSHOP_NO_TRANSLATE_BELOW:
            return "".join(lines[:idx] + lines[idx + 1:])
    return text

def apply_workshop_item_id(text, item_id):
    """Replace the $item-id$ token when an item id is available."""
    if text is None or item_id is None:
        return text
    return text.replace(WORKSHOP_ITEM_ID_TOKEN, str(item_id))

def trim_description(text, lang_label):
    """Truncate the description to MAX_DESCRIPTION_LENGTH bytes and warn if truncated."""
    if not text:
        return text

    encoded = text.encode("utf-8")
    if len(encoded) > MAX_DESCRIPTION_LENGTH:
        print(f"Warning: Description for '{lang_label}' exceeds {MAX_DESCRIPTION_LENGTH} bytes. Truncating.")
        return encoded[:MAX_DESCRIPTION_LENGTH].decode("utf-8", errors="ignore")
    return text

def build_workshop_page_updates(config, item_id, dev_mode=False, dev_name=None):
    """Collect source and translated workshop title/description payloads."""
    source_language = load_source_language(config)
    if source_language is None:
        return None

    base_description = read_text(WORKSHOP_DESCRIPTION_PATH)
    if base_description is None:
        print(f"Error: Workshop description file not found: {WORKSHOP_DESCRIPTION_PATH}")
        return None

    base_description = split_workshop_description(base_description)
    base_description = apply_workshop_item_id(base_description, item_id)
    base_description = trim_description(base_description, source_language)
    base_title = load_workshop_source_title(dev_mode=dev_mode, dev_name=dev_name)

    updates = [{
        "lang": source_language,
        "steam_lang": LANGUAGE_TO_STEAM[source_language],
        "title": base_title,
        "description": base_description,
    }]

    if not os.path.exists(TRANSLATIONS_DIR):
        print(f"Warning: Translations folder not found: {TRANSLATIONS_DIR}")
        return updates

    translations = {}
    for filename in os.listdir(TRANSLATIONS_DIR):
        match = WORKSHOP_TRANSLATION_FILENAME_RE.match(filename)
        if not match:
            continue
        lang = match.group(1)
        path = os.path.join(TRANSLATIONS_DIR, filename)
        text = read_text(path)
        if text is None:
            continue

        title_text, desc_text = parse_workshop_translation(text)
        title_text = apply_workshop_item_id(title_text, item_id)
        desc_text = apply_workshop_item_id(desc_text, item_id)
        if title_text is None and desc_text is None:
            continue

        desc_text = trim_description(desc_text, lang)
        translations[lang] = {"title": title_text, "description": desc_text}

    for lang, entry in translations.items():
        if lang == source_language:
            continue
        if lang not in LANGUAGE_TO_STEAM:
            print(f"Warning: No Steam language mapping for '{lang}', skipping.")
            continue
        updates.append({
            "lang": lang,
            "steam_lang": LANGUAGE_TO_STEAM[lang],
            "title": entry["title"],
            "description": entry["description"],
        })

    return updates

def build_change_notes_updates(config, item_id, version=None):
    """Collect source and translated change note payloads for per-language submission."""
    source_language = load_source_language(config)
    if source_language is None:
        return None

    base_change_notes = load_change_notes(CHANGE_NOTES_PATH, item_id, version=version)
    if base_change_notes is None:
        print(f"Warning: No change notes found for version '{version}'.")
        return []

    updates = [{
        "lang": source_language,
        "steam_lang": LANGUAGE_TO_STEAM[source_language],
        "change_notes": base_change_notes,
    }]

    # Translated change notes files correspond to the latest entry (whatever translate.py last ran on).
    # Only use them when the requested version matches the latest, otherwise they'd be stale.
    raw_cn_text = read_text(CHANGE_NOTES_PATH)
    latest_cn_version = get_latest_change_notes_version(raw_cn_text) if raw_cn_text else None
    use_translated = version is None or latest_cn_version is None or version == latest_cn_version

    if use_translated and os.path.exists(TRANSLATIONS_DIR):
        for filename in os.listdir(TRANSLATIONS_DIR):
            cn_match = CHANGE_NOTES_TRANSLATION_FILENAME_RE.match(filename)
            if not cn_match:
                continue
            lang = cn_match.group(1)
            if lang == source_language or lang not in LANGUAGE_TO_STEAM:
                continue
            path = os.path.join(TRANSLATIONS_DIR, filename)
            text = read_text(path)
            if text and text.strip():
                updates.append({
                    "lang": lang,
                    "steam_lang": LANGUAGE_TO_STEAM[lang],
                    "change_notes": apply_workshop_item_id(text, item_id),
                })

    return updates

def upload_workshop_pages_for_item(steam, updates, item_id):
    """Upload workshop title/description updates for each language entry."""
    if updates is None:
        return False

    print("Workshop language updates:")
    for update in updates:
        print(
            f"  - {update['lang']} ({update['steam_lang']}): "
            f"{'title' if update['title'] is not None else 'no-title'}, "
            f"{'description' if update['description'] is not None else 'no-description'}"
        )

    workshop = steam.Workshop
    for update in updates:
        handle = workshop.StartItemUpdate(APP_ID, item_id)
        if not handle:
            print("Error: StartItemUpdate failed. Check app ID and item ID.")
            return False

        lang_label = f"{update['lang']} ({update['steam_lang']})"
        lang_result = steam.Workshop_SetItemUpdateLanguage(handle, update["steam_lang"].encode())
        if lang_result is False:
            print(f"Error: SetItemUpdateLanguage failed for {lang_label}.")
            return False

        if update["title"] is not None:
            title_result = workshop.SetItemTitle(handle, update["title"])
            if title_result is False:
                print(f"Error: SetItemTitle failed for {lang_label}.")
                return False

        if update["description"] is not None:
            desc_result = workshop.SetItemDescription(handle, update["description"])
            if desc_result is False:
                print(f"Error: SetItemDescription failed for {lang_label}.")
                return False

        if not _submit_and_wait(steam, handle, ""):
            print(f"Error: Workshop page update failed for {lang_label}.")
            return False

    print("Workshop page updates submitted.")
    return True

def upload_change_notes_for_item(steam, updates, item_id):
    """Submit per-language change notes as standalone updates."""
    if not updates:
        print("No change notes to submit.")
        return True

    print("Change note updates:")
    for update in updates:
        print(f"  - {update['lang']} ({update['steam_lang']})")

    workshop = steam.Workshop
    for update in updates:
        change_notes = update.get("change_notes", "")
        if not change_notes:
            continue
        handle = workshop.StartItemUpdate(APP_ID, item_id)
        if not handle:
            print("Error: StartItemUpdate failed for change note submission.")
            return False
        lang_label = f"{update['lang']} ({update['steam_lang']})"
        lang_result = steam.Workshop_SetItemUpdateLanguage(handle, update["steam_lang"].encode())
        if lang_result is False:
            print(f"Error: SetItemUpdateLanguage failed for {lang_label}.")
            return False
        if not _submit_and_wait(steam, handle, change_notes):
            print(f"Error: Change note update failed for {lang_label}.")
            return False

    print("Change notes submitted.")
    return True

def parse_args():
    parser = argparse.ArgumentParser(description="Build and upload an EU5 mod to Steam Workshop.")
    parser.add_argument(
        "-m", "--mod",
        action="store_true",
        help="Upload mod content only. When set, config default target settings are ignored."
    )
    parser.add_argument(
        "-wp", "--workshop-pages",
        action="store_true",
        help="Upload Workshop title/description pages only. When set, config default target settings are ignored."
    )
    parser.add_argument(
        "-d", "--dev",
        action="store_true",
        help="Upload the dev Workshop item using dev metadata and thumbnail."
    )
    parser.add_argument(
        "-s", "--submods",
        action="store_true",
        help="Upload all submods found in the submods folder."
    )
    parser.add_argument(
        "-cn", "--change-notes",
        action="store_true",
        help="Upload change notes. When set, config default target settings are ignored."
    )
    return parser.parse_args()

def main():
    args = parse_args()
    config = load_config(CONFIG_PATH)
    if config is None:
        return 1

    upload_mod, upload_workshop_pages, upload_submods_selected, upload_change_notes = resolve_upload_targets(args, config)
    if upload_mod is None:
        return 1

    upload_only_on_version_change = load_optional_bool(config, UPLOAD_ON_VERSION_CHANGE_KEY, False)
    if upload_only_on_version_change is None:
        return 1

    version_cache = load_upload_versions(UPLOAD_VERSIONS_PATH) if upload_only_on_version_change else None

    if not upload_mod and not upload_workshop_pages and not upload_submods_selected and not upload_change_notes:
        print(
            "No upload actions selected. "
            "Enable defaults in config.toml or pass -m/-wp/-s/-cn."
        )
        return 0

    upload_mod_effective = upload_mod
    main_version = None
    main_cache_key = "main:dev" if args.dev else "main:release"
    if upload_mod and upload_only_on_version_change:
        main_version = load_metadata_version(METADATA_PATH, "main mod")
        if main_version is None:
            return 1
        if not should_upload_for_version(version_cache, main_cache_key, main_version):
            print(f"Skipping main mod upload: version '{main_version}' already uploaded.")
            upload_mod_effective = False
    if upload_change_notes and main_version is None:
        main_version = load_metadata_version(METADATA_PATH, "main mod")

    if not upload_mod_effective and not upload_workshop_pages and not upload_submods_selected and not upload_change_notes:
        print("No uploads required after version check.")
        return 0

    item_id_key = "workshop_upload_item_id_dev" if args.dev else "workshop_upload_item_id"
    item_label = "dev item id" if args.dev else "item id"
    item_id = None
    dev_name = load_dev_name(config) if args.dev else None

    if upload_mod_effective or upload_workshop_pages or upload_change_notes:
        item_id = load_workshop_item_id(config, item_id_key, item_label)
        if item_id is None:
            return 1

    release_dir = None
    preview_path = None
    workshop_title = None
    if upload_mod_effective:
        release_dir, preview_path, workshop_title = build_release(dev_mode=args.dev, dev_name=dev_name)

    uploaded_main = False

    with steamworks_session() as steam:
        if upload_mod_effective or upload_workshop_pages or upload_change_notes:
            item_id = ensure_item_id(steam, item_id, CONFIG_PATH, item_id_key)
            if item_id is None:
                return 1

        if upload_workshop_pages:
            updates = build_workshop_page_updates(
                config,
                item_id,
                dev_mode=args.dev,
                dev_name=dev_name,
            )
            if updates is None:
                return 1
            if not upload_workshop_pages_for_item(steam, updates, item_id):
                return 1

        if upload_submods_selected:
            submods_ok, submod_cache_changed = upload_submods(
                steam,
                config,
                version_gate_enabled=upload_only_on_version_change,
                version_cache=version_cache,
                upload_change_notes=upload_change_notes
            )
            if not submods_ok:
                return 1
            if upload_only_on_version_change and submod_cache_changed:
                save_upload_versions(UPLOAD_VERSIONS_PATH, version_cache)

        if upload_mod_effective:
            if not upload_release(steam, release_dir, preview_path, item_id,
                                  workshop_title):
                return 1
            uploaded_main = True
            if upload_only_on_version_change:
                set_uploaded_version(version_cache, main_cache_key, main_version)
                save_upload_versions(UPLOAD_VERSIONS_PATH, version_cache)

        if upload_change_notes:
            cn_updates = build_change_notes_updates(config, item_id, version=main_version)
            if cn_updates is None:
                return 1
            if cn_updates:
                if not upload_change_notes_for_item(steam, cn_updates, item_id):
                    return 1

    if uploaded_main:
        cleanup_release_dir(release_dir)
    return 0

if __name__ == "__main__":
    sys.exit(main())
