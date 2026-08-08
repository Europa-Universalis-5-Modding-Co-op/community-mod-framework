"""Parser: existing Paradox mod files -> ModModel."""

import base64
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
    noinspection = False

    # Directories that contain separate mods or non-mod content
    _skip_dirs = {"submods", "tools", "docs", "assets", "node_modules", ".git"}

    def _in_skip_dir(path: Path) -> bool:
        rel = path.relative_to(directory)
        return any(part in _skip_dirs for part in rel.parts)

    texts = {}
    for f in directory.rglob("*.txt"):
        if _in_skip_dir(f):
            continue
        try:
            texts[f] = decode_bom(f.read_bytes())
        except Exception as e:
            warnings.append(f"Could not read {f}: {e}")

    for f, text in texts.items():
        if "on_action" in f.name.lower() and "cmf_on_mod_registration" in text:
            on_action_content = text
            break

    # The editor writes exactly one effects file and one scripted GUI file. When those
    # are present, read only them: a mod's hand-written siblings hold registration calls
    # of their own, and folding those into the model duplicates them on the next export.
    prefix = _parse_prefix(on_action_content)
    owned_effects = directory / "in_game/common/scripted_effects" / f"{prefix}_cmm_effects.txt"
    owned_gui = directory / "in_game/common/scripted_guis" / f"{prefix}_cmm_scripted_gui.txt"
    outside = {}

    if prefix and owned_effects in texts:
        effects_content = texts[owned_effects]
        if effects_content.lstrip().startswith("#noinspection ALL"):
            noinspection = True
        if owned_gui in texts:
            gui_content = texts[owned_gui]

        for f, text in texts.items():
            if f == owned_effects or f == owned_gui or "cmm_register_" not in text:
                continue
            outside[f.relative_to(directory).as_posix()] = text
    else:
        for f, text in texts.items():
            name = f.name.lower()
            if "on_action" in name and "cmf_on_mod_registration" in text:
                continue
            if "scripted_gui" in str(f.parent).lower() or "scripted_gui" in name:
                if "_on_changed" in text:
                    gui_content += "\n" + text
            elif "effect" in name or "effect" in str(f.parent).lower():
                if "cmm_register_" in text:
                    if text.lstrip().startswith("#noinspection ALL"):
                        noinspection = True
                    effects_content += "\n" + text

    for f in directory.rglob("*_l_english.yml"):
        if _in_skip_dir(f):
            continue
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
        loc_content, metadata_content, warnings,
        noinspection=noinspection,
        directory=directory,
        outside=outside,
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
    loc: str, metadata: str, warnings: list,
    noinspection: bool = False,
    directory: Path = None,
    outside: dict = None,
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
    requires_unrestricted_tools_settings = _parse_requires_unrestricted_tools_settings(effects)
    multiselector_settings = _parse_dropdown_multiselector_settings(effects)
    field_loc_overrides = _parse_field_localization_overrides(effects)
    sgui_settings = _parse_sgui_settings(effects)
    sgui_conditions = _parse_sgui_conditions(gui)

    # Build tabs/groups/settings from registrations
    tabs_map = {}  # tab_id -> Tab
    groups_map = {}  # (tab_id, group_id) -> Group
    tab_order = []
    group_order = []

    # First pass: collect all list fields, item values, and field disables
    list_fields = {}  # setting_id -> [field_regs]
    list_item_values = {}  # setting_id -> {item_number: value}
    list_field_disables = {}  # (setting_id, field_id) -> [item_number]
    list_item_hides = {}  # setting_id -> [item_number]
    list_data_values = {}  # (setting_id, field_id) -> {item_number: value}
    list_text_values = {}  # (setting_id, field_id) -> {item_number: localization key}
    list_field_defaults = {}  # (setting_id, field_id) -> {item_number: value}
    for reg in registrations:
        reg_type = reg.get("_type", "")
        if reg_type == "list_item_hide":
            sid = reg.get("setting_id", "")
            item = _to_int(reg.get("item", "0"))
            if sid and item > 0:
                if sid not in list_item_hides:
                    list_item_hides[sid] = []
                list_item_hides[sid].append(item)
        elif reg_type == "list_field_disable":
            sid = reg.get("setting_id", "")
            fid = reg.get("field_id", "")
            item = _to_int(reg.get("item", "0"))
            if sid and fid and item > 0:
                key = (sid, fid)
                if key not in list_field_disables:
                    list_field_disables[key] = []
                list_field_disables[key].append(item)
        elif reg_type == "list_field_default":
            sid = reg.get("setting_id", "")
            fid = reg.get("field_id", "")
            item = _to_int(reg.get("item", "0"))
            value = reg.get("value", "")
            if sid and fid and item > 0 and value != "":
                key = (sid, fid)
                if key not in list_field_defaults:
                    list_field_defaults[key] = {}
                list_field_defaults[key][item] = _to_float(value)
        elif reg_type.startswith("list_") and "_field" in reg_type:
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
        elif reg_type == "list_data_value":
            sid = reg.get("setting_id", "")
            fid = reg.get("field_id", "")
            item = _to_int(reg.get("item", "0"))
            value = reg.get("value", "")
            if sid and fid and item > 0 and value != "":
                key = (sid, fid)
                if key not in list_data_values:
                    list_data_values[key] = {}
                list_data_values[key][item] = _to_float(value)
        elif reg_type == "list_text_value":
            sid = reg.get("setting_id", "")
            fid = reg.get("field_id", "")
            item = _to_int(reg.get("item", "0"))
            value = reg.get("value", "")
            if sid and fid and item > 0 and value:
                key = (sid, fid)
                if key not in list_text_values:
                    list_text_values[key] = {}
                list_text_values[key][item] = value[5:] if value.startswith("flag:") else value

    # Second pass: build tabs/groups/settings
    subtab_parents = {}  # tab_id -> parent tab_id
    for reg in registrations:
        reg_type = reg.get("_type", "")

        if reg_type.startswith("list_") and "_field" in reg_type:
            continue  # already collected above
        if reg_type == "list_item_value":
            continue  # already collected above
        if reg_type == "list_data_value":
            continue  # already collected above
        if reg_type == "list_text_value":
            continue  # already collected above
        if reg_type == "list_field_disable":
            continue  # already collected above
        if reg_type == "list_item_hide":
            continue  # already collected above
        if reg_type == "subtab":
            child = reg.get("tab_id", "")
            parent = reg.get("parent_tab_id", "")
            if not child or not parent:
                continue
            subtab_parents[child] = parent
            # The parent holds no settings of its own, so nothing else creates it.
            if parent not in tabs_map:
                tabs_map[parent] = Tab(
                    tab_id=parent,
                    name=loc_map.get(f"{mod_id}__{parent}_name", parent),
                )
                tab_order.append(parent)
            continue

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
            list_field_disables, list_item_hides, list_data_values,
            list_text_values, list_field_defaults, field_loc_overrides,
        )
        if setting:
            # Deduplicate: skip if same setting_id already exists in this group
            # (handles if/else branches that register the same setting conditionally)
            existing_ids = {s.setting_id for s in groups_map[gkey].settings}
            if setting.setting_id not in existing_ids:
                groups_map[gkey].settings.append(setting)

    # Parse custom on_changed effects from effects and GUI content
    custom_effects = _parse_custom_effects(effects, gui)
    callback_cases = _parse_callback_cases(effects)
    known_flags = set()
    for gkey in group_order:
        group = groups_map[gkey]
        for setting in group.settings:
            qid = f"{mod_id}__{setting.setting_id}"
            known_flags.add(qid)
            if qid in custom_effects:
                info = custom_effects[qid]
                setting.on_changed_effect = info["effect"]
                setting.pass_value_param = info.get("param")
                if info.get("no_pass"):
                    setting.no_pass_value = True
                # A case that calls a custom effect and never syncs the alias means the
                # effect does the sync itself, and usually needs the old value first.
                if setting.alias and "cmm_sync_" not in callback_cases.get(qid, ""):
                    setting.alias_synced_by_effect = True
            if setting.setting_id in no_reset_settings:
                setting.no_reset = True
            if setting.setting_id in requires_unrestricted_tools_settings:
                setting.requires_unrestricted_tools = True
            if setting.setting_id in multiselector_settings:
                setting.multiselector = True
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

    # Load banner icon and background if they exist
    banner_icon = ""
    banner_background = ""
    if directory and mod_id:
        icons_dir = directory / "main_menu" / "gfx" / "interface" / "icons" / "mods"
        icon_path = icons_dir / f"{mod_id}_banner_logo.dds"
        bg_path = icons_dir / f"{mod_id}_banner_background.dds"

        if icon_path.is_file():
            try:
                file_data = icon_path.read_bytes()
                encoded = base64.b64encode(file_data).decode('ascii')
                banner_icon = f"data:image/vnd.ms-dds;base64,{encoded}"
            except Exception as e:
                warnings.append(f"Could not read icon file: {e}")

        if bg_path.is_file():
            try:
                file_data = bg_path.read_bytes()
                encoded = base64.b64encode(file_data).decode('ascii')
                banner_background = f"data:image/vnd.ms-dds;base64,{encoded}"
            except Exception as e:
                warnings.append(f"Could not read background file: {e}")

    for child, parent in subtab_parents.items():
        if child in tabs_map:
            tabs_map[child].parent_tab_id = parent

    # A setting registered somewhere the editor does not rewrite is invisible here, and moving
    # it into the model would register it twice. Re-registering a field the owned file already
    # declares is a normal runtime override, so only unknown settings are worth reporting.
    known_ids = {f.split("__", 1)[1] for f in known_flags if "__" in f}
    for rel, text in (outside or {}).items():
        for reg in _parse_registrations(text, []):
            rtype = reg.get("_type", "")
            if rtype in ("unknown",) or "_field" in rtype or rtype.startswith(("list_item", "list_data", "list_text", "list_field")):
                continue
            sid = reg.get("setting_id", "")
            if sid and sid not in known_ids:
                warnings.append(
                    f"{rel} registers setting '{sid}' outside {prefix}_cmm_effects.txt, so it is "
                    f"not shown here. Move it into {prefix}_cmm_effects.txt to edit it."
                )
                known_ids.add(sid)

    lobby_banner = "cmf_register_lobby_banner" in on_action
    register_hook_extra = _parse_register_hook_extra(on_action, prefix)
    callback_extra = _parse_callback_extra(effects, known_flags)

    # Keep the toolkit's trailing " Dev" install marker out of the in-game menu name.
    meta_name = (meta.get("name") or "").removesuffix(" Dev")

    from .generator import METADATA_MANAGED_KEYS
    metadata_extra = {k: v for k, v in meta.items() if k not in METADATA_MANAGED_KEYS}

    model = ModModel(
        mod_id=mod_id,
        file_prefix=prefix or mod_id,
        mod_name=loc_map.get(f"{mod_id}_name", "") or meta_name or mod_id,
        mod_desc=loc_map.get(f"{mod_id}_desc", "") or meta.get("short_description", ""),
        banner_icon=banner_icon,
        banner_background=banner_background,
        lobby_banner=lobby_banner,
        register_hook_extra=register_hook_extra,
        callback_extra=callback_extra,
        metadata_name=meta.get("name", ""),
        metadata_id=meta.get("id", ""),
        metadata_version=meta.get("version", "0.1"),
        metadata_short_description=meta.get("short_description", ""),
        metadata_tags=meta.get("tags", ["Utilities"]),
        metadata_game_version=meta.get("supported_game_version", "1.1.*"),
        metadata_relationships=[
            r for r in meta.get("relationships", [])
            if r.get("id") != "community_mod_framework"
        ],
        metadata_extra=metadata_extra,
        metadata_key_order=list(meta.keys()),
        noinspection=noinspection,
        emit_flag_keys=loc_map.get(mod_id, "") == mod_id if mod_id else True,
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


def _parse_register_hook_extra(on_action: str, prefix: str) -> str:
    """Capture modder-added effects in the <prefix>_on_register_cmf_mod leaf, preserving everything but the editor-owned <prefix>_register_cmf_mod call."""
    if not prefix:
        return ""
    leaf = re.search(re.escape(prefix) + r"_on_register_cmf_mod\s*=\s*\{", on_action)
    if not leaf:
        return ""
    leaf_end = _find_closing_brace(on_action, leaf.end())
    if leaf_end < 0:
        return ""
    body = on_action[leaf.end():leaf_end]
    eff = re.search(r"\beffect\s*=\s*\{", body)
    if not eff:
        return ""
    eff_end = _find_closing_brace(body, eff.end())
    if eff_end < 0:
        return ""
    inner = body[eff.end():eff_end]
    own = f"{prefix}_register_cmf_mod = yes"
    kept = [ln for ln in inner.splitlines() if ln.strip() != own]
    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept)


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


def _parse_requires_unrestricted_tools_settings(content: str) -> set:
    """Extract cmm_set_requires_unrestricted_tools_enabled blocks -> set of setting_ids."""
    result = set()
    pattern = re.compile(r"cmm_set_requires_unrestricted_tools_enabled\s*=\s*\{", re.IGNORECASE)
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


def _parse_dropdown_multiselector_settings(content: str) -> set:
    """Extract cmm_set_dropdown_multiselector blocks -> set of setting_ids."""
    result = set()
    pattern = re.compile(r"cmm_set_dropdown_multiselector\s*=\s*\{", re.IGNORECASE)
    for m in pattern.finditer(content):
        block_end = _find_closing_brace(content, m.end())
        if block_end < 0:
            continue
        block = content[m.end():block_end]
        params = _parse_params(block)
        composite = params.get("setting", "")
        if "__" in composite:
            result.add(composite.split("__", 1)[1])
    return result


def _parse_field_localization_overrides(content: str) -> dict:
    """Extract cmm_set_list_field_localization blocks -> {(setting_id, field_id): {name, root}}."""
    result = {}
    pattern = re.compile(r"cmm_set_list_field_localization\s*=\s*\{", re.IGNORECASE)
    for m in pattern.finditer(content):
        block_end = _find_closing_brace(content, m.end())
        if block_end < 0:
            continue
        block = content[m.end():block_end]
        params = _parse_params(block)
        sid = params.get("setting_id", "")
        fid = params.get("field_id", "")
        if sid and fid:
            result[(sid, fid)] = {
                "name": params.get("name", ""),
                "root": params.get("root", ""),
            }
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
    setting aliases.  Returns a dict keyed by template field key
    (``prefix_i$i$_fN``).  Each value is either:

    * ``{"alias": "<template>"}`` — all items follow a ``$i$`` pattern
    * ``{"item_aliases": {1: "a1", 2: "a2", ...}}`` — per-item aliases
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

    # Group by (prefix, slot) so we can inspect all items for a field
    groups = {}  # (prefix, slot_str) -> {item_num: alias}
    for field_key, alias_val in raw.items():
        m2 = re.match(r"(.+)_i(\d+)_f(\d+)$", field_key)
        if m2:
            key = (m2.group(1), m2.group(3))
            item_num = int(m2.group(2))
            if key not in groups:
                groups[key] = {}
            groups[key][item_num] = alias_val

    aliases = {}
    for (prefix, slot_str), items in groups.items():
        template_key = f"{prefix}_i$i$_f{slot_str}"
        # Check if all aliases follow the same $i$ template
        templates = set()
        for item_num, alias_val in items.items():
            templates.add(re.sub(r'(?<!\d)' + str(item_num) + r'(?!\d)', "$i$", alias_val, count=1))
        if len(templates) == 1:
            # All items produce the same template — store as template alias
            aliases[template_key] = {"alias": templates.pop()}
        else:
            # Per-item aliases — each item has a unique alias
            aliases[template_key] = {"item_aliases": items}
    return aliases


def _find_callback_switch(effects: str) -> Tuple[int, int]:
    """Locate the switch body inside the generated callback handler. (-1, -1) when absent."""
    cb = re.search(r"^\w+_handle_(?:cmf_)?callback\s*=\s*\{", effects, re.MULTILINE)
    if not cb:
        return -1, -1
    cb_end = _find_closing_brace(effects, cb.end())
    if cb_end < 0:
        return -1, -1
    sw = re.search(r"\bswitch\s*=\s*\{", effects[cb.end():cb_end])
    if not sw:
        return -1, -1
    start = cb.end() + sw.end()
    end = _find_closing_brace(effects, start)
    return (start, end) if end >= 0 else (-1, -1)


def _parse_callback_cases(effects: str) -> dict:
    """Extract each `flag:<key> = { ... }` case of the callback switch -> its raw body."""
    start, end = _find_callback_switch(effects)
    if start < 0:
        return {}
    body = effects[start:end]
    cases = {}
    for fm in re.finditer(r"flag:(\w+)\s*=\s*\{", body):
        fe = _find_closing_brace(body, fm.end())
        if fe < 0:
            continue
        cases[fm.group(1)] = body[fm.end():fe]
    return cases


def _parse_callback_extra(effects: str, known_flags: set) -> str:
    """Capture callback cases the editor does not own, such as an action bar element's.

    Returns the source lines verbatim, so their indentation and any leading comment
    survive the round trip.
    """
    start, end = _find_callback_switch(effects)
    if start < 0:
        return ""
    body = effects[start:end]
    lines = body.split("\n")

    # Map each case's opening line index to the line index just past its closing brace.
    kept = []
    depth = 0
    case_flag = None
    case_start = 0
    for idx, line in enumerate(lines):
        if depth == 0:
            m = re.match(r"\s*flag:(\w+)\s*=\s*\{", line)
            if m:
                case_flag = m.group(1)
                case_start = idx
        depth += line.count("{") - line.count("}")
        if case_flag is not None and depth == 0:
            if case_flag not in known_flags:
                head = case_start
                while head > 0 and lines[head - 1].strip().startswith("#"):
                    head -= 1
                kept.extend(lines[head:idx + 1])
            case_flag = None

    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept)


def _parse_custom_effects(effects: str, gui: str = "") -> dict:
    """Parse custom on_changed effect info from effects and GUI content.

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

    # 3. List _on_changed blocks from scripted GUI content
    if gui:
        on_changed_gui_pat = re.compile(r"^(\w+)_on_changed\s*=\s*\{", re.MULTILINE)
        for m in on_changed_gui_pat.finditer(gui):
            qid = m.group(1)
            if qid in result:
                continue
            block_end = _find_closing_brace(gui, m.end())
            if block_end < 0:
                continue
            block = gui[m.end():block_end]
            if "cmm_apply_list_change" not in block:
                continue
            # Find the effect = { ... } sub-block to avoid matching is_shown/is_valid content
            effect_m = re.search(r"\beffect\s*=\s*\{", block)
            if not effect_m:
                continue
            effect_end = _find_closing_brace(block, effect_m.end())
            if effect_end < 0:
                continue
            effect_block = block[effect_m.end():effect_end]
            # Find custom effect calls (effect_name = yes) within the effect block
            _skip = {"cmm_apply_list_change", "always"}
            for line in effect_block.split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("}"):
                    continue
                em = re.match(r"(\w+)\s*=\s*yes\s*$", line)
                if em and em.group(1) not in _skip:
                    result[qid] = {"effect": em.group(1), "no_pass": True}
                    break

    return result


def _parse_registrations(content: str, warnings: list) -> list:
    """Extract cmm_register_* blocks from effects content."""
    registrations = []
    pattern = re.compile(
        r"(cmm_register_(?:global_)?(?:bool_setting|button_setting|numeric_setting|"
        r"slider_setting|dropdown_setting|text_setting|settings_list|"
        r"settings_list_from_list|"
        r"list_bool_field|list_dropdown_field|list_numeric_field|list_slider_field|list_data_field|"
        r"list_button_field|list_text_field|subtab)|"
        r"cmm_set_list_item_value|cmm_set_list_data_value|cmm_set_list_text_value|cmm_set_list_field_default_for_item|cmm_disable_list_field_for_item|cmm_hide_list_item)\s*=\s*\{",
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

        # Skip macro-parameterized blocks (dead branch suppression)
        if any("$" in str(v) for k, v in params.items() if not k.startswith("_")):
            pos = block_end + 1
            continue

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
    if "list_slider_field" in fn:
        return "list_slider_field"
    if "list_data_field" in fn:
        return "list_data_field"
    if "list_button_field" in fn:
        return "list_button_field"
    if "list_text_field" in fn:
        return "list_text_field"
    if "register_subtab" in fn:
        return "subtab"
    if "settings_list_from_list" in fn:
        return "list_from_list"
    if "settings_list" in fn:
        return "list"
    if "set_list_item_value" in fn:
        return "list_item_value"
    if "set_list_data_value" in fn:
        return "list_data_value"
    if "set_list_text_value" in fn:
        return "list_text_value"
    if "set_list_field_default_for_item" in fn:
        return "list_field_default"
    if "disable_list_field_for_item" in fn:
        return "list_field_disable"
    if "hide_list_item" in fn:
        return "list_item_hide"
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
    """Extract key = value pairs from a block.

    Handles both multi-line (one pair per line) and single-line
    (multiple pairs on one line) formats.
    """
    result = {}
    # Strip comments
    cleaned = "\n".join(
        l for l in block.split("\n")
        if not l.strip().startswith("#")
    )
    # Find all key = value pairs where value is a non-whitespace token.
    # This handles single-line blocks like: mod_id = lsq setting_id = foo item = 1
    for m in re.finditer(r"(\w+)\s*=\s*(\S+)", cleaned):
        result[m.group(1)] = m.group(2)
    return result


def _reg_to_setting(
    reg: dict, mod_id: str, loc_map: dict, list_fields: dict,
    list_item_values: dict = None,
    setting_aliases: dict = None,
    inverted_aliases: set = None,
    field_aliases: dict = None,
    option_aliases: dict = None,
    list_field_disables: dict = None,
    list_item_hides: dict = None,
    list_data_values: dict = None,
    list_text_values: dict = None,
    list_field_defaults: dict = None,
    loc_overrides: dict = None,
) -> Setting:
    """Convert a registration dict to a Setting."""
    reg_type = reg.get("_type", "")
    if reg_type.startswith("list_") and "_field" in reg_type:
        return None  # fields handled separately
    if reg_type == "list_item_value":
        return None  # item values handled separately
    if reg_type == "list_data_value":
        return None  # data values handled separately
    if reg_type == "list_text_value":
        return None  # text values handled separately
    if reg_type == "subtab":
        return None  # sub-tab parents handled separately
    if reg_type == "list_field_disable":
        return None  # field disables handled separately
    if reg_type == "list_item_hide":
        return None  # item hides handled separately

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
            item_descs = []
            for i in range(1, setting.item_count + 1):
                item_names.append(loc_map.get(f"{qid}_i{i}_name", f"Item {i}"))
                item_descs.append(loc_map.get(f"{qid}_i{i}_desc", ""))
            setting.item_names = item_names
            if any(item_descs):
                setting.item_descs = item_descs

        # Collect item values
        values_map = (list_item_values or {}).get(sid, {})
        if values_map:
            item_values = []
            count = setting.item_count or 1
            for i in range(1, count + 1):
                item_values.append(values_map.get(i, ""))
            setting.item_values = item_values

        # Collect hidden items
        hidden = (list_item_hides or {}).get(sid)
        if hidden:
            setting.hidden_items = sorted(hidden)

        fields = []
        for fi, freg in enumerate(list_fields.get(sid, [])):
            fld = _parse_list_field(
                freg, mod_id, sid, loc_map, fi, field_aliases,
                list_field_disables, loc_overrides,
            )
            if fld:
                # Attach data values if this is a data field
                if fld.field_type == "data":
                    dv_map = (list_data_values or {}).get((sid, fld.field_id))
                    if dv_map:
                        count = setting.item_count or 1
                        fld.item_data_values = [dv_map.get(i, "") for i in range(1, count + 1)]
                elif fld.field_type == "text":
                    tv_map = (list_text_values or {}).get((sid, fld.field_id))
                    if tv_map:
                        count = setting.item_count or 1
                        fld.item_text_values = [
                            loc_map.get(tv_map[i], "") if i in tv_map else ""
                            for i in range(1, count + 1)
                        ]
                # Attach per-item defaults for interactive fields
                elif fld.field_type in ("bool", "dropdown", "numeric", "slider"):
                    def_map = (list_field_defaults or {}).get((sid, fld.field_id))
                    if def_map:
                        count = setting.item_count or 1
                        fld.item_default_values = [def_map.get(i, "") for i in range(1, count + 1)]
                fields.append(fld)
        setting.fields = fields

    return setting


def _parse_list_field(
    reg: dict, mod_id: str, setting_id: str, loc_map: dict,
    field_index: int = 0, field_aliases: dict = None,
    list_field_disables: dict = None, loc_overrides: dict = None,
) -> ListField:
    fid = reg.get("field_id", "")
    ftype_raw = reg.get("_type", "")
    if "bool" in ftype_raw:
        ftype = "bool"
    elif "dropdown" in ftype_raw:
        ftype = "dropdown"
    elif "slider" in ftype_raw:
        ftype = "slider"
    elif "numeric" in ftype_raw:
        ftype = "numeric"
    elif "data" in ftype_raw:
        ftype = "data"
    elif "button" in ftype_raw:
        ftype = "button"
    elif "text" in ftype_raw:
        ftype = "text"
    else:
        return None

    fqid = f"{mod_id}__{setting_id}__{fid}"

    # Localization key override from cmm_set_list_field_localization
    override = (loc_overrides or {}).get((setting_id, fid))
    name_key = (override.get("name") if override else "") or f"{fqid}_name"
    root = (override.get("root") if override else "") or fqid

    # Look up field alias (template or per-item)
    slot = field_index + 1
    alias_key = f"{mod_id}__{setting_id}_i$i$_f{slot}"
    alias_entry = (field_aliases or {}).get(alias_key)
    alias = ""
    item_aliases = None
    if isinstance(alias_entry, dict):
        alias = alias_entry.get("alias", "")
        ia = alias_entry.get("item_aliases")
        if ia:
            # Convert {1: "a1", 2: "a2"} to list ordered by item number
            max_item = max(ia.keys())
            item_aliases = [ia.get(i, "") for i in range(1, max_item + 1)]
    elif isinstance(alias_entry, str):
        # Backwards compat (shouldn't happen with new parser)
        alias = alias_entry

    # Look up disabled items for this field
    disabled_items = (list_field_disables or {}).get((setting_id, fid))
    if disabled_items:
        disabled_items = sorted(disabled_items)

    field = ListField(
        field_id=fid,
        field_type=ftype,
        name=loc_map.get(name_key, fid),
        desc=loc_map.get(f"{root}_desc", ""),
        alias=alias,
        item_aliases=item_aliases,
        disabled_items=disabled_items,
        loc_name_key=override.get("name", "") if override else "",
        loc_root_key=override.get("root", "") if override else "",
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
    elif ftype in ("numeric", "slider"):
        field.default_value = _to_float(reg.get("default_value", "0"))
        field.min_value = _to_float(reg.get("min_value", "0"))
        field.max_value = _to_float(reg.get("max_value", "10"))
        field.step_value = _to_float(reg.get("step_value", "1"))
    elif ftype == "data":
        field.default_value = _to_float(reg.get("default_value", "0"))
    elif ftype == "button":
        field.button_text = loc_map.get(f"{root}_text", "")

    # Format display — reconstruct $VALUE$ format from prefix/postfix loc keys
    pfx = loc_map.get(f"{root}_prefix", "")
    sfx = loc_map.get(f"{root}_postfix", "")
    if pfx or sfx:
        field.display_format = f"{pfx}$VALUE${sfx}"
    pfx_high = loc_map.get(f"{root}_prefix_high", "")
    sfx_high = loc_map.get(f"{root}_postfix_high", "")
    if pfx_high or sfx_high:
        field.display_format_high = f"{pfx_high}$VALUE${sfx_high}"
    pfx_low = loc_map.get(f"{root}_prefix_low", "")
    sfx_low = loc_map.get(f"{root}_postfix_low", "")
    if pfx_low or sfx_low:
        field.display_format_low = f"{pfx_low}$VALUE${sfx_low}"

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
