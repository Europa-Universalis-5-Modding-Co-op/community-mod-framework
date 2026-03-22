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

        if "on_action" in name and "cmf_on_mod_registration" in text:
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
            loc_content += "\n" + decode_bom(raw)
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

    # Parse setting and field aliases from effects
    setting_aliases = _parse_setting_aliases(effects)
    inverted_aliases = _parse_inverted_aliases(effects)
    field_aliases = _parse_field_aliases(effects)
    option_aliases = _parse_option_aliases(effects)
    no_reset_settings = _parse_no_reset_settings(effects)
    sgui_settings = _parse_sgui_settings(effects)
    sgui_conditions = _parse_sgui_conditions(gui)

    # Build tabs/groups/settings from registrations
    tabs_map = {}  # tab_id -> Tab
    groups_map = {}  # (tab_id, group_id) -> Group
    tab_order = []
    group_order = []

    # First pass: collect all list fields and item values
    list_fields = {}  # setting_id -> [field_regs]
    list_item_values = {}  # setting_id -> {item_number: value}
    for reg in registrations:
        reg_type = reg.get("_type", "")
        if reg_type.startswith("list_") and "_field" in reg_type:
            sid = reg.get("setting_id", "")
            if sid not in list_fields:
                list_fields[sid] = []
            list_fields[sid].append(reg)
        elif reg_type == "list_item_value":
            sid = reg.get("setting_id", "")
            item = _to_int(reg.get("item", "0"))
            value = reg.get("value", "")
            if sid and item > 0 and value:
                if sid not in list_item_values:
                    list_item_values[sid] = {}
                list_item_values[sid][item] = value

    # Second pass: build tabs/groups/settings
    for reg in registrations:
        reg_type = reg.get("_type", "")

        if reg_type.startswith("list_") and "_field" in reg_type:
            continue  # already collected above
        if reg_type == "list_item_value":
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
                name=loc_map.get(f"{mod_id}__{tab_id}__{group_id}_name", group_id),
                desc=loc_map.get(f"{mod_id}__{tab_id}__{group_id}_desc", ""),
            )
            groups_map[gkey] = g
            group_order.append(gkey)
            tabs_map[tab_id].groups.append(g)

        setting = _reg_to_setting(
            reg, mod_id, loc_map, list_fields, list_item_values,
            setting_aliases, inverted_aliases, field_aliases, option_aliases,
        )
        if setting:
            groups_map[gkey].settings.append(setting)

    # Parse custom on_changed effects from effects content
    custom_effects = _parse_custom_effects(effects)
    for gkey in group_order:
        group = groups_map[gkey]
        for setting in group.settings:
            qid = f"{mod_id}__{setting.setting_id}"
            if qid in custom_effects:
                info = custom_effects[qid]
                setting.on_changed_effect = info["effect"]
                setting.pass_value_param = info.get("param")
                if info.get("no_pass"):
                    setting.no_pass_value = True
            if setting.setting_id in no_reset_settings:
                setting.no_reset = True
            if setting.setting_id in sgui_settings:
                setting.scripted_gui = True
            if qid in sgui_conditions:
                conds = sgui_conditions[qid]
                if conds.get("visible"):
                    setting.visible = conds["visible"]
                if conds.get("enabled"):
                    setting.enabled = conds["enabled"]
                # If conditions exist but scripted_gui not explicitly set (e.g. list settings),
                # still mark it for round-trip if there are conditions
                if not setting.scripted_gui and setting.setting_type != "list":
                    setting.scripted_gui = True

    model = ModModel(
        mod_id=mod_id,
        file_prefix=prefix or mod_id,
        mod_name=loc_map.get(f"{mod_id}_name", "") or meta.get("name", "") or mod_id,
        mod_desc=loc_map.get(f"{mod_id}_desc", "") or meta.get("short_description", ""),
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
    m = re.search(r"(\w+)_on_register_(?:cmf_)?mod", on_action)
    if m:
        return m.group(1)
    m = re.search(r"(\w+)_register_(?:cmf_)?mod\s*=\s*yes", on_action)
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


def _parse_option_aliases(content: str) -> dict:
    """Extract cmm_sync_dropdown_option_alias blocks -> {qid: {index: alias}}."""
    result = {}
    pattern = re.compile(
        r"cmm_sync_dropdown_option_alias\s*=\s*\{", re.IGNORECASE
    )
    for m in pattern.finditer(content):
        block_end = _find_closing_brace(content, m.end())
        if block_end < 0:
            continue
        block = content[m.end():block_end]
        params = _parse_params(block)
        setting = params.get("setting", "")
        index = _to_int(params.get("index", "0"))
        alias = params.get("alias", "")
        if setting and index > 0 and alias:
            if setting not in result:
                result[setting] = {}
            if index not in result[setting]:
                result[setting][index] = alias
    return result


def _parse_sgui_settings(content: str) -> set:
    """Extract cmm_add_scripted_gui blocks -> set of setting_ids."""
    result = set()
    pattern = re.compile(r"cmm_add_scripted_gui\s*=\s*\{", re.IGNORECASE)
    for m in pattern.finditer(content):
        block_end = _find_closing_brace(content, m.end())
        if block_end < 0:
            continue
        block = content[m.end():block_end]
        params = _parse_params(block)
        sid = params.get("setting_id", "")
        if sid:
            result.add(sid)
    return result


def _parse_sgui_conditions(gui_content: str) -> dict:
    """Extract is_shown/is_valid blocks from _on_changed scripted GUIs.

    Returns {qid: {"visible": str|None, "enabled": str|None}}.
    """
    result = {}
    pattern = re.compile(r"^(\w+)_on_changed\s*=\s*\{", re.MULTILINE)
    for m in pattern.finditer(gui_content):
        qid = m.group(1)
        block_end = _find_closing_brace(gui_content, m.end())
        if block_end < 0:
            continue
        block = gui_content[m.end():block_end]

        visible = _extract_sub_block(block, "is_shown")
        enabled = _extract_sub_block(block, "is_valid")
        if visible or enabled:
            result[qid] = {"visible": visible, "enabled": enabled}
    return result


def _extract_sub_block(block: str, name: str) -> str:
    """Extract the content of a named sub-block (e.g. is_shown = { ... })."""
    pattern = re.compile(rf"\b{re.escape(name)}\s*=\s*\{{")
    m = pattern.search(block)
    if not m:
        return None
    end = _find_closing_brace(block, m.end())
    if end < 0:
        return None
    inner = block[m.end():end]
    # Clean up: strip, remove empty lines, dedent
    lines = [l.strip() for l in inner.strip().splitlines() if l.strip()]
    return "\n".join(lines) if lines else None


def _parse_no_reset_settings(content: str) -> set:
    """Extract cmm_set_no_reset blocks -> set of setting_ids."""
    result = set()
    pattern = re.compile(r"cmm_set_no_reset\s*=\s*\{", re.IGNORECASE)
    for m in pattern.finditer(content):
        block_end = _find_closing_brace(content, m.end())
        if block_end < 0:
            continue
        block = content[m.end():block_end]
        params = _parse_params(block)
        sid = params.get("setting_id", "")
        if sid:
            result.add(sid)
    return result


def _parse_setting_aliases(content: str) -> dict:
    """Extract cmm_sync_setting_alias and cmm_sync_bool_alias blocks -> {setting_key: alias}."""
    aliases = {}
    pattern = re.compile(
        r"cmm_sync_(?:setting|bool)_alias(?:_inverted)?\s*=\s*\{", re.IGNORECASE
    )
    for m in pattern.finditer(content):
        block_end = _find_closing_brace(content, m.end())
        if block_end < 0:
            continue
        block = content[m.end():block_end]
        params = _parse_params(block)
        setting = params.get("setting", "")
        alias = params.get("alias", "")
        if setting and alias:
            if setting not in aliases:
                aliases[setting] = alias
    return aliases


def _parse_inverted_aliases(content: str) -> set:
    """Extract cmm_sync_bool_alias_inverted blocks -> set of setting keys."""
    result = set()
    pattern = re.compile(
        r"cmm_sync_bool_alias_inverted\s*=\s*\{", re.IGNORECASE
    )
    for m in pattern.finditer(content):
        block_end = _find_closing_brace(content, m.end())
        if block_end < 0:
            continue
        block = content[m.end():block_end]
        params = _parse_params(block)
        setting = params.get("setting", "")
        if setting:
            result.add(setting)
    return result


def _parse_field_aliases(content: str) -> dict:
    """Extract list field aliases from cmm_sync_setting_alias blocks.

    Distinguishes field aliases (keys ending in ``_iN_fN``) from regular
    setting aliases. Returns the alias with item number replaced back to
    ``$i$`` so it can be stored as a template.
    """
    raw = {}  # field_key -> alias (concrete item number)
    pattern = re.compile(
        r"cmm_sync_setting_alias\s*=\s*\{", re.IGNORECASE
    )
    for m in pattern.finditer(content):
        block_end = _find_closing_brace(content, m.end())
        if block_end < 0:
            continue
        block = content[m.end():block_end]
        params = _parse_params(block)
        setting = params.get("setting", "")
        alias = params.get("alias", "")
        if setting and alias:
            if re.search(r'_i\d+_f\d+$', setting):
                if setting not in raw:
                    raw[setting] = alias

    # Reconstruct template aliases from first concrete instance (i1)
    aliases = {}
    for field_key, alias_val in raw.items():
        m2 = re.match(r"(.+)_i(\d+)_f(\d+)$", field_key)
        if m2 and m2.group(2) == "1":
            template_key = f"{m2.group(1)}_i$i$_f{m2.group(3)}"
            template_alias = alias_val.replace("1", "$i$", 1)
            aliases[template_key] = template_alias
    return aliases


def _parse_custom_effects(effects: str) -> dict:
    """Parse custom on_changed effect info from effects content.

    Returns {qid: {"effect": str, "param": str|None, "no_pass": bool|None}}
    """
    result = {}

    # 1. Text setting _on_changed blocks (scripted effects, not GUIs)
    on_changed_pat = re.compile(r"^(\w+)_on_changed\s*=\s*\{", re.MULTILINE)
    for m in on_changed_pat.finditer(effects):
        qid = m.group(1)
        block_end = _find_closing_brace(effects, m.end())
        if block_end < 0:
            continue
        block = effects[m.end():block_end]

        # Skip placeholder blocks (only comments and log lines)
        code_lines = [
            l.strip() for l in block.split("\n")
            if l.strip() and not l.strip().startswith("#")
        ]
        if not code_lines or all(
            l.startswith("log ") or l.startswith("log=") for l in code_lines
        ):
            continue

        for line in code_lines:
            if line.startswith("log ") or line.startswith("log="):
                continue

            # effect_name = yes  (no_pass_value)
            m2 = re.match(r"(\w+)\s*=\s*yes\s*$", line)
            if m2:
                result[qid] = {"effect": m2.group(1), "param": None, "no_pass": True}
                break

            # effect_name = {  (passing $text$ parameter)
            m2 = re.match(r"(\w+)\s*=\s*\{", line)
            if m2:
                effect_name = m2.group(1)
                param_match = re.search(r"(\w+)\s*=\s*\$text\$", block)
                param = None
                if param_match and param_match.group(1) != "value":
                    param = param_match.group(1)
                result[qid] = {"effect": effect_name, "param": param, "no_pass": None}
                break

    # 2. _handle_callback switch cases for non-text settings
    cb_pattern = re.compile(r"^\w+_handle_(?:cmf_)?callback\s*=\s*\{", re.MULTILINE)
    cb_m = cb_pattern.search(effects)
    if cb_m:
        cb_end = _find_closing_brace(effects, cb_m.end())
        if cb_end >= 0:
            cb_block = effects[cb_m.end():cb_end]

            flag_pat = re.compile(r"flag:(\w+)\s*=\s*\{")
            for fm in flag_pat.finditer(cb_block):
                qid = fm.group(1)
                if qid in result:
                    continue  # already parsed from _on_changed
                flag_end = _find_closing_brace(cb_block, fm.end())
                if flag_end < 0:
                    continue
                flag_block = cb_block[fm.end():flag_end]

                for fline in flag_block.split("\n"):
                    fline = fline.strip()
                    if not fline or fline.startswith("#") or fline.startswith("}"):
                        continue
                    if fline.startswith("cmm_sync_"):
                        continue

                    em = re.match(r"(\w+)\s*=\s*yes\s*$", fline)
                    if em:
                        result[qid] = {"effect": em.group(1)}
                        break

    return result


def _parse_registrations(content: str, warnings: list) -> list:
    """Extract cmm_register_* blocks from effects content."""
    registrations = []
    pattern = re.compile(
        r"(cmm_register_(?:global_)?(?:bool_setting|button_setting|numeric_setting|"
        r"slider_setting|dropdown_setting|text_setting|settings_list|"
        r"settings_list_from_list|"
        r"list_bool_field|list_dropdown_field|list_numeric_field)|"
        r"cmm_set_list_item_value)\s*=\s*\{",
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
    if "settings_list_from_list" in fn:
        return "list_from_list"
    if "settings_list" in fn:
        return "list"
    if "set_list_item_value" in fn:
        return "list_item_value"
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
    reg: dict, mod_id: str, loc_map: dict, list_fields: dict,
    list_item_values: dict = None,
    setting_aliases: dict = None,
    inverted_aliases: set = None,
    field_aliases: dict = None,
    option_aliases: dict = None,
) -> Setting:
    """Convert a registration dict to a Setting."""
    reg_type = reg.get("_type", "")
    if reg_type.startswith("list_") and "_field" in reg_type:
        return None  # fields handled separately
    if reg_type == "list_item_value":
        return None  # item values handled separately

    sid = reg.get("setting_id", "")
    is_global = reg.get("_is_global", False)
    qid = f"{mod_id}__{sid}"

    # Normalize list_from_list to list
    effective_type = "list" if reg_type == "list_from_list" else reg_type

    # Look up setting alias
    alias = (setting_aliases or {}).get(qid, "")
    alias_inverted = qid in (inverted_aliases or set())

    setting = Setting(
        setting_id=sid,
        setting_type=effective_type,
        is_global=is_global,
        name=loc_map.get(f"{qid}_name", sid),
        desc=loc_map.get(f"{qid}_desc", ""),
        alias=alias,
        alias_inverted=alias_inverted,
    )

    if effective_type == "bool":
        setting.default_value = _to_int(reg.get("default_value", "0"))
    elif effective_type == "button":
        setting.button_text = loc_map.get(f"{qid}_text", "Run")
    elif effective_type in ("numeric", "slider"):
        setting.default_value = _to_float(reg.get("default_value", "0"))
        setting.min_value = _to_float(reg.get("min_value", "0"))
        setting.max_value = _to_float(reg.get("max_value", "100"))
        setting.step_value = _to_float(reg.get("step_value", "1"))
        raw_fmt = loc_map.get(f"{qid}_format", "")
        if raw_fmt:
            setting.display_format = re.sub(r"\[CMMV\('[^']*'\)\]", "$VALUE$", raw_fmt)
    elif effective_type == "dropdown":
        setting.default_index = _to_int(reg.get("default_index", "1"))
        setting.option_count = _to_int(reg.get("option_count", "1"))
        opt_alias_map = (option_aliases or {}).get(qid, {})
        options = []
        for i in range(1, setting.option_count + 1):
            oname = loc_map.get(f"{qid}_option_{i}_name", f"Option {i}")
            odesc = loc_map.get(f"{qid}_option_{i}_desc", "")
            options.append(DropdownOption(index=i, name=oname, desc=odesc, alias=opt_alias_map.get(i, "")))
        setting.options = options
    elif effective_type == "text":
        setting.character_limit = _to_int(reg.get("character_limit", "42"))
        setting.quote_text = _to_int(reg.get("quote_text", "0"))
    elif effective_type == "list":
        setting.is_ordered = _to_int(reg.get("is_ordered", "0"))
        setting.item_column_name = loc_map.get(f"{qid}_item_column_name", "Item")

        if reg_type == "list_from_list":
            setting.list_source = reg.get("list", "")
            setting.item_count = 1
            setting.item_names = []
        else:
            setting.item_count = _to_int(reg.get("item_count", "1"))
            item_names = []
            for i in range(1, setting.item_count + 1):
                iname = loc_map.get(f"{qid}_i{i}_name", f"Item {i}")
                item_names.append(iname)
            setting.item_names = item_names

        # Collect item values
        values_map = (list_item_values or {}).get(sid, {})
        if values_map:
            item_values = []
            count = setting.item_count or 1
            for i in range(1, count + 1):
                item_values.append(values_map.get(i, ""))
            setting.item_values = item_values

        fields = []
        for fi, freg in enumerate(list_fields.get(sid, [])):
            fld = _parse_list_field(
                freg, mod_id, sid, loc_map, fi, field_aliases,
            )
            if fld:
                fields.append(fld)
        setting.fields = fields

    return setting


def _parse_list_field(
    reg: dict, mod_id: str, setting_id: str, loc_map: dict,
    field_index: int = 0, field_aliases: dict = None,
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

    # Look up field alias
    slot = field_index + 1
    alias_key = f"{mod_id}__{setting_id}_i$i$_f{slot}"
    alias = (field_aliases or {}).get(alias_key, "")

    field = ListField(
        field_id=fid,
        field_type=ftype,
        name=loc_map.get(f"{fqid}_name", fid),
        alias=alias,
    )

    if ftype == "bool":
        field.default_value = _to_int(reg.get("default_value", "0"))
    elif ftype == "dropdown":
        field.default_index = _to_int(reg.get("default_index", "1"))
        field.option_count = _to_int(reg.get("option_count", "1"))
        options = []
        for i in range(1, field.option_count + 1):
            oname = loc_map.get(f"{fqid}_option_{i}_name", f"Option {i}")
            odesc = loc_map.get(f"{fqid}_option_{i}_desc", "")
            options.append(DropdownOption(index=i, name=oname, desc=odesc))
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
