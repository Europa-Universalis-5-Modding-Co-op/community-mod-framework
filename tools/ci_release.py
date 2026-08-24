"""Release helper for the GitHub Actions workflow.

Reuses tools/upload.py so a CI release and a local `python tools/upload.py`
resolve the same title, stage the same folder, and cut the same change notes
from the same tools/config.toml.

Steam itself is reached through SteamCMD in the workflow, not from here.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import upload

ROOT_DIR = upload.ROOT_DIR
CONFIG_PATH = upload.CONFIG_PATH
MAIN_RELEASE_CACHE_KEY = "main:release"

RELEASE_TRIGGER_KEY = "ci_release_upload_trigger"
RELEASE_BRANCHES_KEY = "ci_release_upload_branches"
RELEASE_SUBMODS_KEY = "ci_release_upload_submods"
DEV_TRIGGER_KEY = "ci_dev_upload_trigger"
DEV_BRANCHES_KEY = "ci_dev_upload_branches"
DEV_DESCRIPTION_KEY = "ci_dev_upload_workshop_description"
RELEASE_FILES_KEY = "ci_release_files"
RELEASE_ARCHIVES_KEY = "ci_release_archives"

TRIGGER_VALUES = ("off", "push", "pr-merge")

# --- Output plumbing ---

def log(message):
    print(message, flush=True)

def warn(message):
    print(f"::warning::{message}", flush=True)

def fail(message):
    print(f"::error::{message}", flush=True)
    sys.exit(1)

def emit(key, value):
    """Append a step output. Written here rather than parsed from stdout, since the
    upload.py helpers print their own warnings."""
    value = "" if value is None else str(value)
    log(f"{key}={value}" if "\n" not in value else f"{key}=<{len(value)} bytes>")

    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if "\n" in value:
            delimiter = f"ci_{uuid.uuid4().hex}"
            f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
        else:
            f.write(f"{key}={value}\n")

def summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip("\n") + "\n\n")

def as_bool(value, default=False):
    text = str(value).strip().lower() if value is not None else ""
    if text in ("true", "yes", "1"):
        return True
    if text in ("false", "no", "0"):
        return False
    return default

def yn(value):
    return "true" if value else "false"

# --- Config ---

def read_config():
    config = upload.load_config(CONFIG_PATH)
    if config is None:
        fail(f"Could not read {CONFIG_PATH}.")
    return config

def read_trigger(config, key):
    raw = config.get(key)
    if raw is None:
        return "off"
    value = str(raw).strip().lower()
    if value not in TRIGGER_VALUES:
        fail(f"{key} must be one of {', '.join(TRIGGER_VALUES)} in tools/config.toml, not '{raw}'.")
    return value

def read_branches(config, key, default):
    raw = config.get(key)
    if raw is None:
        return list(default)
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        fail(f"{key} must be a list of branch names in tools/config.toml.")
    return [str(entry).strip() for entry in raw if str(entry).strip()]

def read_string_list(config, key):
    raw = config.get(key)
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        fail(f"{key} must be a list of file paths in tools/config.toml.")
    return [str(entry).strip() for entry in raw if str(entry).strip()]

def channel_item_id(config, channel):
    key = "workshop_upload_item_id_dev" if channel == "dev" else "workshop_upload_item_id"
    item_id = upload.load_workshop_item_id(config, key, f"{channel} item id")
    if item_id is None:
        fail(f"{key} is missing or invalid in tools/config.toml.")
    if item_id == 0:
        flag = " -d" if channel == "dev" else ""
        fail(
            f"{key} is 0, so there is no {channel} Workshop item to publish to. "
            f"Run `python tools/upload.py{flag}` locally once to create the item, "
            "then commit the id it writes into tools/config.toml."
        )
    return item_id

def channel_names(config, channel):
    dev_mode = channel == "dev"
    dev_name = upload.load_name_override(config, "workshop_dev_name") if dev_mode else None
    workshop_name = upload.load_name_override(config, "workshop_name") if not dev_mode else None
    return dev_mode, dev_name, workshop_name

def version_card(config):
    card = upload.load_version_card(config)
    if card is None:
        fail("workshop_version_card is invalid in tools/config.toml.")
    return card

# --- gate ---

def git_output(args):
    try:
        result = subprocess.run(["git"] + args, cwd=ROOT_DIR, capture_output=True, text=True, check=False)
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""

def tag_exists(version):
    return bool(git_output(["tag", "-l", version]))

def last_tag():
    newest = git_output(["rev-list", "--tags", "--max-count=1"])
    if newest:
        described = git_output(["describe", "--tags", newest])
        if described:
            return described
    first_commit = git_output(["rev-list", "--max-parents=0", "HEAD"])
    return first_commit.splitlines()[0] if first_commit else ""

def skip(reason):
    emit("run", "false")
    emit("skip-reason", reason)
    summary(f"# Skipped\n\n{reason}")
    sys.exit(0)

def trigger_matches(trigger, branches, event_trigger, branch):
    return trigger == event_trigger and branch in branches

def cmd_gate(args):
    config = read_config()

    release_trigger = read_trigger(config, RELEASE_TRIGGER_KEY)
    dev_trigger = read_trigger(config, DEV_TRIGGER_KEY)
    release_branches = read_branches(config, RELEASE_BRANCHES_KEY, ["main"])
    dev_branches = read_branches(config, DEV_BRANCHES_KEY, ["dev"])

    automatic = args.event != "workflow_dispatch"

    if automatic:
        if args.event == "pull_request":
            if not as_bool(args.pr_merged):
                skip("Pull request closed without merging.")
            event_trigger = "pr-merge"
        else:
            event_trigger = "push"

        if trigger_matches(release_trigger, release_branches, event_trigger, args.ref_name):
            channel = "release"
        elif trigger_matches(dev_trigger, dev_branches, event_trigger, args.ref_name):
            channel = "dev"
        else:
            skip(
                f"No automatic upload is configured for a {event_trigger} on '{args.ref_name}'. "
                f"{RELEASE_TRIGGER_KEY} is '{release_trigger}' for {release_branches}, "
                f"{DEV_TRIGGER_KEY} is '{dev_trigger}' for {dev_branches}."
            )

        publish = True
        upload_change_notes = channel == "release"
        if channel == "release":
            upload_submods = upload.load_optional_bool(config, RELEASE_SUBMODS_KEY, False)
            upload_description = True
        else:
            upload_submods = False
            upload_description = upload.load_optional_bool(config, DEV_DESCRIPTION_KEY, False)
        if upload_submods is None or upload_description is None:
            fail("A ci_ boolean in tools/config.toml must be true or false.")
    else:
        channel = args.channel
        publish = as_bool(args.publish, True)
        upload_description = as_bool(args.upload_workshop_description, True)
        upload_change_notes = as_bool(args.upload_change_notes, True)
        upload_submods = as_bool(args.upload_submods, False)

    item_id = channel_item_id(config, channel)

    version = upload.load_metadata_version(upload.METADATA_PATH, "main mod")
    if version is None:
        fail("Could not read the mod version from .metadata/metadata.json.")

    have_secrets = bool(os.environ.get("WORKSHOP_USERNAME")) and bool(os.environ.get("WORKSHOP_PASSWORD"))
    if publish and not have_secrets:
        message = (
            "WORKSHOP_USERNAME and WORKSHOP_PASSWORD are not both set. "
            "Add them as repository secrets to publish to the Workshop."
        )
        if not automatic:
            fail(message)
        warn(message)
        skip(message)

    if channel == "dev":
        should_github = False
        should_steam = True
    else:
        # An automatic release always requires a version change; a manual run follows
        # upload_only_on_version_change.
        configured_gate = upload.load_optional_bool(config, upload.UPLOAD_ON_VERSION_CHANGE_KEY, False)
        if configured_gate is None:
            fail(f"{upload.UPLOAD_ON_VERSION_CHANGE_KEY} must be true or false in tools/config.toml.")
        gated = automatic or configured_gate

        should_github = not (gated and tag_exists(version))
        if not should_github:
            summary(f"# GitHub Release Skipped\n\nVersion **{version}** is already tagged.")

        cache = upload.load_upload_versions(upload.UPLOAD_VERSIONS_PATH)
        already_uploaded = not upload.should_upload_for_version(cache, MAIN_RELEASE_CACHE_KEY, version)
        should_steam = not (gated and already_uploaded)
        if not should_steam:
            summary(f"# Workshop Upload Skipped\n\nVersion **{version}** was already uploaded to the Workshop.")

        if not should_github and not should_steam:
            skip(f"Version {version} is already tagged and already uploaded to the Workshop.")

    emit("run", "true")
    emit("skip-reason", "")
    emit("channel", channel)
    emit("item-id", item_id)
    emit("version", version)
    emit("last-tag", last_tag() if channel == "release" else "")
    emit("publish", yn(publish))
    emit("upload-description", yn(upload_description))
    emit("upload-change-notes", yn(upload_change_notes))
    emit("upload-submods", yn(upload_submods and channel == "release"))
    emit("should-release-github", yn(should_github))
    emit("should-release-steam", yn(should_steam))

    summary(f"# {channel.capitalize()} Release\n\nVersion **{version}** to Workshop item **{item_id}**.")

# --- stage ---

def cmd_stage(args):
    config = read_config()
    dev_mode, dev_name, workshop_name = channel_names(config, args.channel)

    release_dir, preview_path, title = upload.build_release(
        dev_mode=dev_mode, dev_name=dev_name, workshop_name=workshop_name
    )
    title = upload.apply_version_card(title, version_card(config))

    log(f"Staged the {args.channel} build at {release_dir}")
    emit("release-dir", release_dir)
    emit("preview-path", preview_path or "")
    emit("workshop-title", title)

# --- change notes ---

BBCODE_URL_RE = re.compile(r"\[url=([^\]]+)\]([^\[]*)\[/url\]", re.IGNORECASE)
BBCODE_VERSION_HEADER_RE = re.compile(r"^\[b\]v[^\[\]]*\[/b\]$")

def bbcode_to_markdown(text):
    """Convert a change note into the GitHub release body."""
    lines = text.splitlines()
    if lines and BBCODE_VERSION_HEADER_RE.match(lines[0].strip()):
        # The release title already carries the version.
        lines = lines[1:]
    text = "\n".join(lines).strip()

    text = BBCODE_URL_RE.sub(r"[\2](\1)", text)
    text = re.sub(r"\[url\]([^\[]*)\[/url\]", r"\1", text, flags=re.IGNORECASE)
    for level in (1, 2, 3):
        hashes = "#" * (level + 1)
        text = re.sub(rf"\[h{level}\]([^\[]*)\[/h{level}\]", rf"{hashes} \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\[/?b\]", "**", text, flags=re.IGNORECASE)
    text = re.sub(r"\[/?i\]", "*", text, flags=re.IGNORECASE)
    text = re.sub(r"\[/?u\]", "__", text, flags=re.IGNORECASE)
    text = re.sub(r"\[/?code\]", "\n```\n", text, flags=re.IGNORECASE)
    text = re.sub(r"^[ \t]*\[\*\][ \t]*", "- ", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"^[ \t]*\[/?(?:list|olist)(?:=[^\]]*)?\][ \t]*\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\[hr\](?:\[/hr\])?", "\n---\n", text, flags=re.IGNORECASE)
    return text.strip()

def cmd_change_notes(args):
    notes = upload.load_change_notes(upload.CHANGE_NOTES_PATH, args.item_id, version=args.version)
    if notes is None:
        warn(f"No change notes entry for version {args.version} in assets/workshop/change-notes.bbcode.")
        notes = ""

    if notes and args.format == "markdown":
        notes = bbcode_to_markdown(notes)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(notes)

    emit("present", yn(bool(notes.strip())))
    if notes.strip() and args.format == "bbcode":
        summary(f"# Change Notes\n\n```\n{notes}\n```")

# --- Workshop metadata ---

def vdf_escape(text):
    # Escape backslashes for VDF; substitute " with ' since SteamCMD's
    # workshop_build_item VDF parser truncates at " even when escaped as \".
    return str(text).replace("\\", "\\\\").replace('"', "'")

def write_vdf(path, fields):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write('"workshopitem"\n{\n')
        for key, value in fields:
            if value is None or value == "":
                continue
            f.write(f'\t"{key}" "{vdf_escape(value)}"\n')
        f.write("}\n")
    return os.path.abspath(path)

def cmd_vdf(args):
    change_note = ""
    if args.change_notes_file and os.path.exists(args.change_notes_file):
        with open(args.change_notes_file, "r", encoding="utf-8") as f:
            change_note = f.read().strip()

    path = write_vdf(args.out, [
        ("appid", upload.APP_ID),
        ("publishedfileid", args.item_id),
        ("contentfolder", os.path.abspath(args.content_dir)),
        ("previewfile", os.path.abspath(args.preview) if args.preview else ""),
        ("title", upload.enforce_title_length(args.title, "workshop item")),
        ("changenote", change_note),
    ])
    emit("path", path)

    with open(path, "r", encoding="utf-8") as f:
        summary(f"# Workshop Metadata\n\n```\n{f.read().rstrip()}\n```")

def cmd_page_vdf(args):
    config = read_config()

    source_language = upload.load_source_language(config)
    if source_language is None:
        fail("source_language is missing or unsupported in tools/config.toml.")
    if source_language != "english":
        warn(
            "SteamCMD writes the Workshop item's default language page and cannot select one, "
            f"so the '{source_language}' description is uploaded there. Run "
            "`python tools/upload.py -wp` locally for per-language pages."
        )

    description = upload.read_text(upload.WORKSHOP_DESCRIPTION_PATH)
    if description is None:
        fail(f"Workshop description not found at {upload.WORKSHOP_DESCRIPTION_PATH}.")
    description = upload.apply_workshop_item_id(upload.split_workshop_description(description), args.item_id)
    description = upload.trim_description(description, source_language)

    path = write_vdf(args.out, [
        ("appid", upload.APP_ID),
        ("publishedfileid", args.item_id),
        ("title", upload.enforce_title_length(args.title, source_language)),
        ("description", description),
    ])
    emit("path", path)
    emit("language", source_language)

def cmd_submod_vdfs(args):
    config = read_config()
    mapping = upload.load_submods_config(config)
    submods_root = os.path.join(ROOT_DIR, upload.SUBMODS_DIR_NAME)
    written = []

    if not mapping:
        log("No submods configured for upload.")
    elif not os.path.isdir(submods_root):
        warn(f"submods folder not found: {submods_root}")
    else:
        found = {}
        for entry in sorted(os.listdir(submods_root)):
            mod_dir = os.path.join(submods_root, entry)
            if not os.path.isdir(mod_dir):
                continue
            meta = upload._load_submod_metadata(mod_dir)
            if meta is not None:
                found[meta["id"]] = meta

        for mod_id, workshop_id in mapping.items():
            meta = found.get(mod_id)
            if meta is None:
                warn(f"Submod '{mod_id}' not found in submods/. Skipping.")
                continue
            if workshop_id == 0:
                warn(f"Submod '{mod_id}' has no Workshop id in tools/config.toml. Skipping.")
                continue

            change_note = ""
            if as_bool(args.change_notes) and meta["version"]:
                notes_path = os.path.join(meta["root"], "workshop", "change-notes.bbcode")
                change_note = upload.load_change_notes(notes_path, workshop_id, version=meta["version"]) or ""

            thumbnail = meta["thumbnail"] if os.path.exists(meta["thumbnail"]) else ""
            path = write_vdf(os.path.join(args.out_dir, f"submod-{mod_id}.vdf"), [
                ("appid", upload.APP_ID),
                ("publishedfileid", workshop_id),
                ("contentfolder", os.path.abspath(meta["root"])),
                ("previewfile", os.path.abspath(thumbnail) if thumbnail else ""),
                ("title", upload.enforce_title_length(meta["name"], f"submod {mod_id}")),
                ("changenote", change_note.strip()),
            ])
            written.append(path)
            log(f"Prepared submod '{mod_id}' for Workshop item {workshop_id}.")

    os.makedirs(args.out_dir, exist_ok=True)
    list_file = os.path.join(args.out_dir, "submod-vdfs.txt")
    with open(list_file, "w", encoding="utf-8", newline="\n") as f:
        for path in written:
            f.write(path + "\n")

    emit("count", len(written))
    emit("list-file", os.path.abspath(list_file))
    summary(f"# Submods\n\nPrepared **{len(written)}** submod(s).")

# --- release downloads ---

def zip_tree(archive_path, root_dir):
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, _, files in os.walk(root_dir):
            for name in sorted(files):
                full = os.path.join(folder, name)
                archive.write(full, os.path.relpath(full, root_dir).replace("\\", "/"))

def read_archive_specs(config):
    specs = []
    for entry in config.get(RELEASE_ARCHIVES_KEY) or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        files = entry.get("files")
        if not name or not isinstance(files, list):
            warn(f"Ignoring a malformed {RELEASE_ARCHIVES_KEY} entry in tools/config.toml.")
            continue
        members = []
        for member in files:
            if not isinstance(member, dict):
                continue
            source = str(member.get("from") or "").strip()
            target = str(member.get("to") or "").strip() or source
            if source:
                members.append((source, target))
        specs.append((name, members))
    return specs

def cmd_assets(args):
    config = read_config()
    os.makedirs(args.out_dir, exist_ok=True)
    produced = []

    mod_zip = os.path.join(args.out_dir, args.archive_name)
    zip_tree(mod_zip, args.release_dir)
    produced.append(mod_zip)
    log(f"Packaged {args.archive_name}")

    for name, members in read_archive_specs(config):
        archive_path = os.path.join(args.out_dir, f"{name}.zip")
        included = 0
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for source, target in members:
                full = os.path.join(ROOT_DIR, source)
                if not os.path.exists(full):
                    warn(f"{RELEASE_ARCHIVES_KEY} entry '{name}' references a missing file: {source}")
                    continue
                if target.endswith("/"):
                    target += os.path.basename(source)
                archive.write(full, target.replace("\\", "/"))
                included += 1
        if included:
            produced.append(archive_path)
            log(f"Packaged {name}.zip")
        else:
            os.remove(archive_path)
            warn(f"{RELEASE_ARCHIVES_KEY} entry '{name}' had no readable files and was skipped.")

    for relative in read_string_list(config, RELEASE_FILES_KEY):
        full = os.path.join(ROOT_DIR, relative)
        if not os.path.exists(full):
            warn(f"{RELEASE_FILES_KEY} references a missing file: {relative}")
            continue
        destination = os.path.join(args.out_dir, os.path.basename(relative))
        shutil.copy(full, destination)
        produced.append(destination)
        log(f"Attached {relative}")

    emit("files", "\n".join(os.path.abspath(path) for path in produced))
    emit("count", len(produced))

# --- version cache ---

def cmd_record_version(args):
    cache = upload.load_upload_versions(upload.UPLOAD_VERSIONS_PATH)
    changed = upload.should_upload_for_version(cache, MAIN_RELEASE_CACHE_KEY, args.version)
    upload.set_uploaded_version(cache, MAIN_RELEASE_CACHE_KEY, args.version)
    upload.save_upload_versions(upload.UPLOAD_VERSIONS_PATH, cache)
    emit("changed", yn(changed))
    emit("path", os.path.relpath(upload.UPLOAD_VERSIONS_PATH, ROOT_DIR).replace("\\", "/"))

# --- CLI ---

def build_parser():
    parser = argparse.ArgumentParser(description="Release helper for the GitHub Actions workflow.")
    sub = parser.add_subparsers(dest="command", required=True)

    gate = sub.add_parser("gate", help="Decide whether this run publishes, and on which channel")
    gate.add_argument("--event", required=True, choices=["push", "pull_request", "workflow_dispatch"])
    gate.add_argument("--ref-name", default="")
    gate.add_argument("--pr-merged", default="false")
    gate.add_argument("--channel", default="release", choices=["release", "dev"])
    gate.add_argument("--publish", default="true")
    gate.add_argument("--upload-workshop-description", default="true")
    gate.add_argument("--upload-change-notes", default="true")
    gate.add_argument("--upload-submods", default="false")
    gate.set_defaults(func=cmd_gate)

    stage = sub.add_parser("stage", help="Build the release folder for a channel")
    stage.add_argument("--channel", required=True, choices=["release", "dev"])
    stage.set_defaults(func=cmd_stage)

    notes = sub.add_parser("change-notes", help="Write this version's change notes to a file")
    notes.add_argument("--version", required=True)
    notes.add_argument("--item-id", required=True, type=int)
    notes.add_argument("--format", default="bbcode", choices=["bbcode", "markdown"])
    notes.add_argument("--out", required=True)
    notes.set_defaults(func=cmd_change_notes)

    item = sub.add_parser("vdf", help="Write the SteamCMD item metadata")
    item.add_argument("--item-id", required=True, type=int)
    item.add_argument("--title", required=True)
    item.add_argument("--content-dir", required=True)
    item.add_argument("--preview", default="")
    item.add_argument("--change-notes-file", default="")
    item.add_argument("--out", required=True)
    item.set_defaults(func=cmd_vdf)

    page = sub.add_parser("page-vdf", help="Write the SteamCMD Workshop page metadata")
    page.add_argument("--item-id", required=True, type=int)
    page.add_argument("--title", required=True)
    page.add_argument("--out", required=True)
    page.set_defaults(func=cmd_page_vdf)

    submods = sub.add_parser("submod-vdfs", help="Write one SteamCMD metadata file per configured submod")
    submods.add_argument("--out-dir", required=True)
    submods.add_argument("--change-notes", default="false")
    submods.set_defaults(func=cmd_submod_vdfs)

    assets = sub.add_parser("assets", help="Package the mod zip and any configured extra release downloads")
    assets.add_argument("--release-dir", required=True)
    assets.add_argument("--out-dir", required=True)
    assets.add_argument("--archive-name", required=True)
    assets.set_defaults(func=cmd_assets)

    record = sub.add_parser("record-version", help="Record the version uploaded to the release Workshop item")
    record.add_argument("--version", required=True)
    record.set_defaults(func=cmd_record_version)

    return parser

def main():
    args = build_parser().parse_args()
    args.func(args)
    return 0

if __name__ == "__main__":
    sys.exit(main())
