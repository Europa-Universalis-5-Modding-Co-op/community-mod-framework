"""Parser: existing Paradox mod files -> ModModel."""

import json
import re
from pathlib import Path
from typing import Tuple

from .encoding import decode_bom
from .models import (
    ModModel, Tab, Group, Setting, ListField, DropdownOption,
)


def parse_mod_directory(directory: Path) -> Tuple[ModModel, list]:
    """Parse an existing mod directory into a ModModel + warnings."""
    warnings = []

    effects_content = ""
    gui_content = ""
    loc_content = ""
    on_action_content = ""
    metadata_content = ""

    # Find files by pattern
    for f in directory.rglob("*.txt"):
        name = f.name.lower()
        try:
            raw = f.read_bytes()
            text = decode_bom(raw)
        except Exception as e:
            warnings.append(f"Could not read {f}: {e}")
            continue

        if "on_action" in name and "cmm_on_mod_registration" in text:
            on_action_content = text
        elif "scripted_gui" in str(f.parent).lower() or "scripted_gui" in name:
            if "_on_changed" in text:
                gui_content += "\n" + text
        elif "effect" in name or "effect" in str(f.parent).lower():
            if "cmm_register_" in text:
                effects_content += "\n" + text

    for f in directory.rglob("*_l_english.yml"):
        try:
            raw = f.read_bytes()
            loc_content = decode_bom(raw)
        except Exception as e:
            warnings.append(f"Could not read {f}: {e}")

    metadata_path = directory / ".metadata" / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata_content = decode_bom(metadata_path.read_bytes())
        except Exception as e:
            warnings.append(f"Could not read metadata: {e}")

    return _build_model(
        on_action_content, effects_content, gui_content,
        loc_content, metadata_content, warnings
    )


def parse_uploaded_files(files: dict) -> Tuple[ModModel, list]:
    """Parse uploaded file contents (dict of name->content strings)."""
    warnings = []
    return _build_model(
        files.get("on_action", ""),
        files.get("effects", ""),
        files.get("scripted_gui", ""),
        files.get("localization", ""),
        files.get("metadata", ""),
        warnings,
    )


def _build_model(
    on_action: str, effects: str, gui: str,
    loc: str, metadata: str, warnings: list
) -> Tuple[ModModel, list]:
    # Parse prefix from on_action
    prefix = _parse_prefix(on_action)

    # Parse localization
    loc_map = _parse_localization(loc)

    # Parse registrations from effects
    registrations = _parse_registrations(effects, warnings)

    # Parse metadata
    meta = _parse_metadata(metadata, warnings)

    # Determine mod_id from registrations
    mod_id = ""
    for reg in registrations:
        mid = reg.get("mod_id", "")
        if mid:
            mod_id = mid
            break

    # Build tabs/groups/settings from registrations
    tabs_map = {}  # tab_id -> Tab
    groups_map = {}  # (tab_id, group_id) -> Group
    tab_order = []
    group_order = []

    # First pass: collect all list fields
    list_fields = {}  # setting_id -> [field_regs]
    for reg in registrations:
        reg_type = reg.get("_type", "")
        if reg_type.startswith("list_") and "_field" in reg_type:
            sid = reg.get("setting_id", "")
            if sid not in list_fields:
                list_fields[sid] = []
            list_fields[sid].append(reg)

    # Second pass: build tabs/groups/settings
    for reg in registrations:
        reg_type = reg.get("_type", "")

        if reg_type.startswith("list_") and "_field" in reg_type:
            continue  # already collected above

        tab_id = reg.get("tab_id", "general")
        group_id = reg.get("group_id", reg.get("setting_id", "default"))

        if tab_id not in tabs_map:
            tabs_map[tab_id] = Tab(
                tab_id=tab_id,
                name=loc_map.get(f"{mod_id}__{tab_id}_name", tab_id),
            )
            tab_order.append(tab_id)

        gkey = (tab_id, group_id)
        if gkey not in groups_map:
            g = Group(
                group_id=group_id,
                name=loc_map.get(f"{mod_id}__{group_id}_name", group_id),
            )
            groups_map[gkey] = g
            group_order.append(gkey)
            tabs_map[tab_id].groups.append(g)

        setting = _reg_to_setting(reg, mod_id, loc_map, list_fields)
        if setting:
            groups_map[gkey].settings.append(setting)

    model = ModModel(
        mod_id=mod_id,
        file_prefix=prefix or mod_id,
        mod_name=loc_map.get(f"{mod_id}_name", mod_id),
        mod_desc=loc_map.get(f"{mod_id}_desc", ""),
        metadata_name=meta.get("name", ""),
        metadata_id=meta.get("id", ""),
        metadata_version=meta.get("version", "0.1"),
        metadata_short_description=meta.get("short_description", ""),
        metadata_tags=meta.get("tags", ["Utilities"]),
        metadata_game_version=meta.get("supported_game_version", "1.1.*"),
        tabs=[tabs_map[tid] for tid in tab_order],
    )

    return model, warnings


def _parse_prefix(on_action: str) -> str:
    """Extract file prefix from on_action content."""
    m = re.search(r"(\w+)_on_register_mod", on_action)
    if m:
        return m.group(1)
    m = re.search(r"(\w+)_register_mod\s*=\s*yes", on_action)
    if m:
        return m.group(1)
    return ""


def _parse_localization(content: str) -> dict:
    """Parse l_english YAML into a key->value map."""
    result = {}
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("#") or line.startswith("l_english"):
            continue
        m = re.match(r'(\S+):\s*"(.*)"', line)
        if m:
            result[m.group(1)] = m.group(2)
    return result


def _parse_registrations(content: str, warnings: list) -> list:
    """Extract cmm_register_* blocks from effects content."""
    registrations = []
    pattern = re.compile(
        r"(cmm_register_(?:global_)?(?:bool_setting|button_setting|numeric_setting|"
        r"slider_setting|dropdown_setting|text_setting|settings_list|"
        r"list_bool_field|list_dropdown_field|list_numeric_field))\s*=\s*\{",
        re.IGNORECASE,
    )

    pos = 0
    while pos < len(content):
        m = pattern.search(content, pos)
        if not m:
            break

        func_name = m.group(1)
        block_start = m.end()
        block_end = _find_closing_brace(content, block_start)
        if block_end < 0:
            warnings.append(f"Unclosed block for {func_name} at position {m.start()}")
            pos = block_start
            continue

        block = content[block_start:block_end]
        params = _parse_params(block)

        # Determine type
        reg_type = _func_to_type(func_name)
        params["_type"] = reg_type
        params["_is_global"] = "global" in func_name
        registrations.append(params)

        pos = block_end + 1

    return registrations


def _func_to_type(func_name: str) -> str:
    """Map registration function name to setting type."""
    fn = func_name.lower()
    if "list_bool_field" in fn:
        return "list_bool_field"
    if "list_dropdown_field" in fn:
        return "list_dropdown_field"
    if "list_numeric_field" in fn:
        return "list_numeric_field"
    if "settings_list" in fn:
        return "list"
    if "bool_setting" in fn:
        return "bool"
    if "button_setting" in fn:
        return "button"
    if "numeric_setting" in fn:
        return "numeric"
    if "slider_setting" in fn:
        return "slider"
    if "dropdown_setting" in fn:
        return "dropdown"
    if "text_setting" in fn:
        return "text"
    return "unknown"


def _find_closing_brace(content: str, start: int) -> int:
    depth = 1
    i = start
    while i < len(content):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _parse_params(block: str) -> dict:
    """Extract key = value pairs from a block."""
    result = {}
    for line in block.split("\n"):
        line = line.strip()
        if line.startswith("#"):
            continue
        m = re.match(r"(\w+)\s*=\s*(.+)", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            result[key] = val
    return result


def _reg_to_setting(
    reg: dict, mod_id: str, loc_map: dict, list_fields: dict
) -> Setting:
    """Convert a registration dict to a Setting."""
    reg_type = reg.get("_type", "")
    if reg_type.startswith("list_") and "_field" in reg_type:
        return None  # fields handled separately

    sid = reg.get("setting_id", "")
    is_global = reg.get("_is_global", False)
    qid = f"{mod_id}__{sid}"

    setting = Setting(
        setting_id=sid,
        setting_type=reg_type,
        is_global=is_global,
        name=loc_map.get(f"{qid}_name", sid),
        desc=loc_map.get(f"{qid}_desc", ""),
    )

    if reg_type == "bool":
        setting.default_value = _to_int(reg.get("default_value", "0"))
    elif reg_type == "button":
        setting.button_text = loc_map.get(f"{qid}_text", "Run")
    elif reg_type in ("numeric", "slider"):
        setting.default_value = _to_float(reg.get("default_value", "0"))
        setting.min_value = _to_float(reg.get("min_value", "0"))
        setting.max_value = _to_float(reg.get("max_value", "100"))
        setting.step_value = _to_float(reg.get("step_value", "1"))
    elif reg_type == "dropdown":
        setting.default_index = _to_int(reg.get("default_index", "1"))
        setting.option_count = _to_int(reg.get("option_count", "1"))
        options = []
        for i in range(1, setting.option_count + 1):
            oname = loc_map.get(f"{qid}_option_{i}_name", f"Option {i}")
            options.append(DropdownOption(index=i, name=oname))
        setting.options = options
    elif reg_type == "text":
        setting.character_limit = _to_int(reg.get("character_limit", "42"))
        setting.quote_text = _to_int(reg.get("quote_text", "0"))
    elif reg_type == "list":
        setting.item_count = _to_int(reg.get("item_count", "1"))
        setting.is_ordered = _to_int(reg.get("is_ordered", "0"))
        setting.item_column_name = loc_map.get(f"{qid}_item_column_name", "Item")

        item_names = []
        for i in range(1, setting.item_count + 1):
            iname = loc_map.get(f"{qid}_item_{i}_name", f"Item {i}")
            item_names.append(iname)
        setting.item_names = item_names

        fields = []
        for freg in list_fields.get(sid, []):
            fld = _parse_list_field(freg, mod_id, sid, loc_map)
            if fld:
                fields.append(fld)
        setting.fields = fields

    return setting


def _parse_list_field(
    reg: dict, mod_id: str, setting_id: str, loc_map: dict
) -> ListField:
    fid = reg.get("field_id", "")
    ftype_raw = reg.get("_type", "")
    if "bool" in ftype_raw:
        ftype = "bool"
    elif "dropdown" in ftype_raw:
        ftype = "dropdown"
    elif "numeric" in ftype_raw:
        ftype = "numeric"
    else:
        return None

    fqid = f"{mod_id}__{setting_id}__{fid}"
    field = ListField(
        field_id=fid,
        field_type=ftype,
        name=loc_map.get(f"{fqid}_name", fid),
    )

    if ftype == "bool":
        field.default_value = _to_int(reg.get("default_value", "0"))
    elif ftype == "dropdown":
        field.default_index = _to_int(reg.get("default_index", "1"))
        field.option_count = _to_int(reg.get("option_count", "1"))
        options = []
        for i in range(1, field.option_count + 1):
            oname = loc_map.get(f"{fqid}_option_{i}_name", f"Option {i}")
            options.append(DropdownOption(index=i, name=oname))
        field.options = options
    elif ftype == "numeric":
        field.default_value = _to_float(reg.get("default_value", "0"))
        field.min_value = _to_float(reg.get("min_value", "0"))
        field.max_value = _to_float(reg.get("max_value", "10"))
        field.step_value = _to_float(reg.get("step_value", "1"))

    return field


def _parse_metadata(content: str, warnings: list) -> dict:
    if not content.strip():
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        warnings.append(f"Could not parse metadata.json: {e}")
        return {}


def _to_int(s) -> int:
    try:
        return int(float(str(s)))
    except (TypeError, ValueError):
        return 0


def _to_float(s) -> float:
    try:
        f = float(str(s))
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return 0
