#!/usr/bin/env python3
"""
Extract types and templates from vanilla EU5 GUI files.

Creates GUI files containing only the type/template definitions from vanilla files,
allowing dependent mods to override the original files (for top-level widgets like
lateralviews) without losing the shared type/template definitions.

Definitions that the mod already overrides (outside the vanilla output folder)
are automatically excluded to avoid conflicts.

Usage: python tools/extract_vanilla_types.py
"""

import re
import sys
from pathlib import Path

GAME_GUI_DIR = Path(r"C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MOD_GUI_DIR = PROJECT_ROOT / "in_game" / "gui"
OUTPUT_DIR = MOD_GUI_DIR / "vanilla"

VANILLA_FILES = [
    "foreign_country_lateralview.gui",
    "government_lateralview.gui",
    "ingame_topbar.gui",
    "location_window.gui",
    "outliner_entries.gui",
    "single_unit_window.gui",
    "technology_lateralview.gui",
]

BOM = "\ufeff"

TYPE_DEF_RE = re.compile(r'^type\s+(?:"([^"]+)"|(\w+))\s*=')
TEMPLATE_RE = re.compile(r'^template\s+(?:"([^"]+)"|(\w+))')


def _name_from_match(match):
    """Return the captured name from either the quoted or unquoted group."""
    return match.group(1) or match.group(2)


def parse_braces(line):
    """Return (net_depth_change, has_open) for a line, ignoring strings and comments."""
    in_string = False
    depth = 0
    has_open = False
    for ch in line:
        if ch == "#" and not in_string:
            break
        if ch == '"':
            in_string = not in_string
        if not in_string:
            if ch == "{":
                depth += 1
                has_open = True
            elif ch == "}":
                depth -= 1
    return depth, has_open


def find_block_end(lines, start):
    """Find the end of a brace-delimited block starting at `start`. Returns end index (exclusive)."""
    brace_depth = 0
    seen_open = False
    i = start
    while i < len(lines):
        delta, has_open = parse_braces(lines[i])
        brace_depth += delta
        if has_open:
            seen_open = True
        i += 1
        if seen_open and brace_depth <= 0:
            break
    return i


def _collect_types_from_block(lines, start, end, mod_types):
    """Collect type names defined within a types block."""
    depth = 0
    for i in range(start, end):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        old_depth = depth
        delta, _ = parse_braces(lines[i])
        depth += delta
        if old_depth == 1:
            match = TYPE_DEF_RE.match(stripped)
            if match:
                mod_types.add(_name_from_match(match))


def collect_mod_definitions():
    """Scan mod GUI files (excluding vanilla output) for type and template names."""
    mod_types = set()
    mod_templates = set()

    for gui_file in MOD_GUI_DIR.rglob("*.gui"):
        if gui_file.is_relative_to(OUTPUT_DIR):
            continue

        try:
            content = gui_file.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue

        lines = content.split("\n")
        i = 0

        while i < len(lines):
            stripped = lines[i].strip()

            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            match = TEMPLATE_RE.match(stripped)
            if match:
                mod_templates.add(_name_from_match(match))
                i = find_block_end(lines, i)
                continue

            if stripped.startswith("types "):
                block_end = find_block_end(lines, i)
                _collect_types_from_block(lines, i, block_end, mod_types)
                i = block_end
                continue

            if "{" in stripped:
                i = find_block_end(lines, i)
            else:
                i += 1

    return mod_types, mod_templates


def filter_types_block(block_lines, mod_types):
    """Remove overridden type definitions from a types block.

    Returns (filtered_lines or None, list of removed type names).
    """
    if not mod_types:
        return block_lines, []

    # Find body start (after opening brace of types block)
    depth = 0
    body_start = 0
    for idx in range(len(block_lines)):
        delta, has_open = parse_braces(block_lines[idx])
        depth += delta
        if has_open and depth >= 1:
            body_start = idx + 1
            break

    header = block_lines[:body_start]
    body = block_lines[body_start:-1]
    footer = block_lines[-1:]

    filtered_body = []
    comment_buffer = []
    removed = []
    kept_count = 0
    total_types = 0
    i = 0

    while i < len(body):
        stripped = body[i].strip()

        if not stripped or stripped.startswith("#"):
            comment_buffer.append(body[i])
            i += 1
            continue

        match = TYPE_DEF_RE.match(stripped)
        if match:
            type_name = _name_from_match(match)
            total_types += 1
            type_end = find_block_end(body, i)

            if type_name in mod_types:
                comment_buffer = []
                removed.append(type_name)
                i = type_end
                continue

            filtered_body.extend(comment_buffer)
            comment_buffer = []
            filtered_body.extend(body[i:type_end])
            kept_count += 1
            i = type_end
            continue

        # Non-type content (variables, etc.) — keep
        filtered_body.extend(comment_buffer)
        comment_buffer = []
        if "{" in stripped:
            block_end = find_block_end(body, i)
            filtered_body.extend(body[i:block_end])
            i = block_end
        else:
            filtered_body.append(body[i])
            i += 1

    if kept_count == 0 and total_types > 0:
        return None, removed

    return header + filtered_body + footer, removed


def extract_types_templates(content, mod_types=None, mod_templates=None):
    """Extract variables, templates, and types blocks from GUI file content.

    Skips types and templates already defined in mod files (overrides).
    Returns (extracted_lines, stats, overridden_names).
    """
    mod_types = mod_types or set()
    mod_templates = mod_templates or set()

    lines = content.split("\n")
    result = []
    buffer = []  # Pending comment/blank lines before next block
    stats = {"variables": 0, "templates": 0, "types_blocks": 0, "skipped": 0}
    overridden = []
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        # Collect comments and blank lines in buffer
        if not stripped or stripped.startswith("#"):
            buffer.append(lines[i])
            i += 1
            continue

        # Variable definition (@name = value)
        if stripped.startswith("@"):
            result.extend(buffer)
            buffer = []
            result.append(lines[i])
            stats["variables"] += 1
            i += 1
            continue

        # Template block
        if stripped.startswith("template "):
            match = TEMPLATE_RE.match(stripped)
            block_end = find_block_end(lines, i)
            if match and _name_from_match(match) in mod_templates:
                overridden.append(f"template {_name_from_match(match)}")
                buffer = []
                i = block_end
                continue
            result.extend(buffer)
            buffer = []
            result.extend(lines[i:block_end])
            result.append("")
            stats["templates"] += 1
            i = block_end
            continue

        # Types block
        if stripped.startswith("types "):
            block_end = find_block_end(lines, i)
            block_lines = lines[i:block_end]
            filtered, removed = filter_types_block(block_lines, mod_types)
            for name in removed:
                overridden.append(f"type {name}")
            if filtered is None:
                buffer = []
                i = block_end
                continue
            result.extend(buffer)
            buffer = []
            result.extend(filtered)
            result.append("")
            stats["types_blocks"] += 1
            i = block_end
            continue

        # Any other top-level block (widget, lateralview, select_menu, etc.) — skip
        buffer = []
        stats["skipped"] += 1
        if "{" in stripped:
            i = find_block_end(lines, i)
        else:
            i += 1

    return result, stats, overridden


def process_file(filename, mod_types, mod_templates):
    """Process a single vanilla GUI file and write extracted types/templates."""
    input_path = GAME_GUI_DIR / filename
    if not input_path.exists():
        print(f"  SKIP: {input_path} not found")
        return False

    content = input_path.read_text(encoding="utf-8-sig")
    extracted, stats, overridden = extract_types_templates(
        content, mod_types, mod_templates
    )

    # Strip trailing blank lines
    while extracted and not extracted[-1].strip():
        extracted.pop()

    stem = filename.removesuffix(".gui")
    output_name = f"cmf_{stem}_vanilla_types.gui"
    output_path = OUTPUT_DIR / output_name

    if not stats["variables"] and not stats["templates"] and not stats["types_blocks"]:
        if overridden:
            print(f"  SKIP: All content overridden by mod ({len(overridden)} items)")
            for item in overridden:
                print(f"    {item}")
        else:
            print(f"  SKIP: No types or templates found")
        return False

    header = [
        f"# Vanilla types and templates extracted from {filename}",
        "# Auto-generated by tools/extract_vanilla_types.py",
        "",
    ]

    output_content = BOM + "\r\n".join(header + extracted) + "\r\n"
    output_path.write_bytes(output_content.encode("utf-8"))

    parts = []
    if stats["variables"]:
        parts.append(f"{stats['variables']} vars")
    if stats["templates"]:
        parts.append(f"{stats['templates']} templates")
    if stats["types_blocks"]:
        parts.append(f"{stats['types_blocks']} types blocks")
    if overridden:
        parts.append(f"{len(overridden)} overrides skipped")
    print(f"  OK: {output_name} ({', '.join(parts)})")
    for item in overridden:
        print(f"    Skipped: {item}")
    return True


def main():
    if OUTPUT_DIR.exists():
        for f in OUTPUT_DIR.glob("*.gui"):
            f.unlink()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mod_types, mod_templates = collect_mod_definitions()

    print(f"Source: {GAME_GUI_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print(
        f"Mod overrides: {len(mod_types)} types, "
        f"{len(mod_templates)} templates\n"
    )

    count = 0
    for filename in VANILLA_FILES:
        print(f"Processing {filename}...")
        if process_file(filename, mod_types, mod_templates):
            count += 1

    print(f"\nDone: {count}/{len(VANILLA_FILES)} files processed")
    return 0 if count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
