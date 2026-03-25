"""Code generator: ModModel -> Paradox script files."""

import json
import re
from pathlib import Path
from .encoding import decode_bom
from .models import ModModel, Setting, ListField


def generate_all(model: ModModel) -> dict:
    """Generate all output files from a ModModel. Returns {filepath: content}."""
    prefix = model.file_prefix or model.mod_id
    mod_id = model.mod_id
    noinspect = "#noinspection ALL\n" if model.noinspection else ""

    files = {}
    if mod_id:
        files[f"in_game/common/on_action/{prefix}_cmm_on_actions.txt"] = noinspect + _gen_on_action(prefix)
        files[f"in_game/common/scripted_effects/{prefix}_cmm_effects.txt"] = noinspect + _gen_effects(model)
        has_sgui = any(
            s.setting_type == "list" or s.scripted_gui
            for t in model.tabs for g in t.groups for s in g.settings
        )
        if has_sgui:
            files[f"in_game/common/scripted_guis/{prefix}_cmm_scripted_gui.txt"] = noinspect + _gen_scripted_guis(model)
        files[f"main_menu/localization/english/{prefix}_cmm_l_english.yml"] = noinspect + _gen_localization(model)
        files[".metadata/metadata.json"] = _gen_metadata(model)

    return files


def _gen_on_action(prefix: str) -> str:
    return (
        f"# Hook this mod into CMF shared registration on_action.\n"
        f"cmf_on_mod_registration = {{\n"
        f"\ton_actions = {{\n"
        f"\t\t{prefix}_on_register_cmf_mod\n"
        f"\t}}\n"
        f"}}\n"
        f"\n"
        f"{prefix}_on_register_cmf_mod = {{\n"
        f"\teffect = {{\n"
        f"\t\t{prefix}_register_cmf_mod = yes\n"
        f"\t}}\n"
        f"}}\n"
        f"\n"
        f"# Unified callback hook for setting changes, alert clicks, action bar clicks.\n"
        f"cmf_on_callback = {{\n"
        f"\ton_actions = {{\n"
        f"\t\t{prefix}_on_cmf_callback\n"
        f"\t}}\n"
        f"}}\n"
        f"\n"
        f"{prefix}_on_cmf_callback = {{\n"
        f"\teffect = {{\n"
        f"\t\t{prefix}_handle_cmf_callback = yes\n"
        f"\t}}\n"
        f"}}\n"
    )


def _gen_effects(model: ModModel) -> str:
    prefix = model.file_prefix or model.mod_id
    mod_id = model.mod_id
    lines = []
    lines.append(f"# Root scope: country.")
    lines.append(f"{prefix}_register_cmf_mod = {{")

    first_tab = True
    for tab in model.tabs:
        if not any(s for g in tab.groups for s in g.settings):
            continue
        if not first_tab:
            lines.append("")
        first_tab = False
        lines.append(f"\t# {tab.name or tab.tab_id} ({tab.tab_id}) Tab")
        first_group = True
        for group in tab.groups:
            if not group.settings:
                continue
            if not first_group:
                lines.append("")
            first_group = False
            lines.append(f"\t## {group.name or group.group_id} ({group.group_id}) Group")
            first_setting = True
            for setting in group.settings:
                if not first_setting:
                    lines.append("")
                first_setting = False
                _emit_registration(lines, mod_id, tab.tab_id, group.group_id, setting)

    lines.append("}")

    # List iteration boilerplate (commented-out reference for mod authors)
    for tab in model.tabs:
        tab_header_emitted = False
        for group in tab.groups:
            group_header_emitted = False
            for setting in group.settings:
                if setting.setting_type == "list" and setting.fields:
                    if not tab_header_emitted:
                        lines.append("")
                        lines.append(f"# {tab.name or tab.tab_id} ({tab.tab_id}) Tab")
                        tab_header_emitted = True
                    if not group_header_emitted:
                        lines.append(f"## {group.name or group.group_id} ({group.group_id}) Group")
                        group_header_emitted = True
                    _emit_list_iteration_boilerplate(lines, mod_id, setting)

    # Callback handler effect
    _emit_callback_handler(lines, model)

    # Text setting effects (text callbacks are scripted effects, not scripted GUIs)
    for tab in model.tabs:
        tab_header_emitted = False
        for group in tab.groups:
            group_header_emitted = False
            for setting in group.settings:
                if setting.setting_type == "text":
                    if not tab_header_emitted:
                        lines.append("")
                        lines.append(f"# {tab.name or tab.tab_id} ({tab.tab_id}) Tab")
                        tab_header_emitted = True
                    if not group_header_emitted:
                        lines.append(f"## {group.name or group.group_id} ({group.group_id}) Group")
                        group_header_emitted = True
                    qid = f"{mod_id}__{setting.setting_id}"
                    lines.append("")
                    lines.append(f"{qid}_on_changed = {{")
                    if setting.on_changed_effect:
                        if not setting.no_pass_value:
                            param = setting.pass_value_param or "value"
                            lines.append(f"\t{setting.on_changed_effect} = {{")
                            lines.append(f"\t\t{param} = $text$")
                            lines.append(f"\t}}")
                        else:
                            lines.append(f"\t{setting.on_changed_effect} = yes")
                    else:
                        lines.append(f"\t# Custom text handling effect. Uses $text$ parameter.")
                        lines.append(f"\t# Replace this placeholder with your actual effect logic.")
                        lines.append(f"\tlog = \"Text submitted: $text$\"")
                    lines.append("}")

    return "\n".join(lines) + "\n"


def _emit_callback_handler(lines: list, model: ModModel):
    """Generate {prefix}_handle_cmf_callback effect with alias sync and custom effect cases."""
    prefix = model.file_prefix or model.mod_id
    mod_id = model.mod_id

    # Collect cases with tab/group context
    cases = []
    for tab in model.tabs:
        for group in tab.groups:
            for setting in group.settings:
                st = setting.setting_type
                if st in ("text", "list"):
                    continue
                qid = f"{mod_id}__{setting.setting_id}"
                alias = _setting_has_alias(setting, mod_id) if st != "button" else ""
                alias_inverted = setting.alias_inverted if st == "bool" else False
                option_aliases = _get_option_aliases(setting) if st == "dropdown" else []
                custom_effect = setting.on_changed_effect or ""
                if alias or option_aliases or custom_effect:
                    cases.append((tab.tab_id, tab.name or tab.tab_id, group.group_id, group.name or group.group_id, qid, st, alias, alias_inverted, option_aliases, custom_effect))

    lines.append("")
    lines.append(f"# Callback handler for cmf_on_callback.")
    lines.append(f"# var:cmf_callback is the flag of the setting, alert, or action bar element that was interacted with.")
    lines.append(f"# Scope: country")
    lines.append(f"{prefix}_handle_cmf_callback = {{")
    lines.append(f"\tswitch = {{")
    lines.append(f"\t\ttrigger = var:cmf_callback")

    if cases:
        current_tab = None
        current_group = None
        for tab_id, tab_name, group_id, group_name, qid, st, alias, alias_inverted, option_aliases, custom_effect in cases:
            if tab_id != current_tab:
                lines.append(f"\t\t# {tab_name} ({tab_id}) Tab")
                current_tab = tab_id
                current_group = None
            if group_id != current_group:
                lines.append(f"\t\t## {group_name} ({group_id}) Group")
                current_group = group_id
            lines.append(f"\t\tflag:{qid} = {{")
            if alias:
                if st == "bool":
                    sync_func = "cmm_sync_bool_alias_inverted" if alias_inverted else "cmm_sync_bool_alias"
                else:
                    sync_func = "cmm_sync_setting_alias"
                lines.append(f"\t\t\t{sync_func} = {{")
                lines.append(f"\t\t\t\tsetting = {qid}")
                lines.append(f"\t\t\t\talias = {alias}")
                lines.append(f"\t\t\t}}")
            for idx, opt_alias in option_aliases:
                lines.append(f"\t\t\tcmm_sync_dropdown_option_alias = {{")
                lines.append(f"\t\t\t\tsetting = {qid}")
                lines.append(f"\t\t\t\tindex = {idx}")
                lines.append(f"\t\t\t\talias = {opt_alias}")
                lines.append(f"\t\t\t}}")
            if custom_effect:
                lines.append(f"\t\t\t{custom_effect} = yes")
            lines.append(f"\t\t}}")
    else:
        lines.append(f"\t\t# flag:{mod_id}__my_setting = {{")
        lines.append(f"\t\t# \t# Custom side effects when this setting changes")
        lines.append(f"\t\t# }}")

    lines.append(f"\t}}")
    lines.append(f"}}")


def _get_option_aliases(setting: Setting) -> list:
    """Return list of (index, alias) for dropdown options that have aliases."""
    aliases = []
    for opt in (setting.options or []):
        a = (getattr(opt, 'alias', '') or '').strip()
        if a:
            aliases.append((opt.index, a))
    return aliases


def _emit_option_alias_sync(lines: list, setting: Setting, qid: str, indent: str = "\t"):
    """Emit cmm_sync_dropdown_option_alias calls for aliased options."""
    aliases = _get_option_aliases(setting)
    if not aliases:
        return
    for idx, alias in aliases:
        lines.append(f"{indent}cmm_sync_dropdown_option_alias = {{")
        lines.append(f"{indent}\tsetting = {qid}")
        lines.append(f"{indent}\tindex = {idx}")
        lines.append(f"{indent}\talias = {alias}")
        lines.append(f"{indent}}}")


def _setting_has_alias(setting: Setting, mod_id: str) -> str:
    """Return the alias if the setting has one, else empty."""
    return (setting.alias or "").strip()


def _field_has_alias(field: ListField, mod_id: str, setting_id: str, slot: int) -> str:
    """Return the alias if the field has one, else empty."""
    return (field.alias or "").strip()


def _emit_registration(lines: list, mod_id: str, tab_id: str, group_id: str, setting: Setting):
    st = setting.setting_type
    is_global = setting.is_global
    qid = f"{mod_id}__{setting.setting_id}"

    if st == "list":
        list_source = setting.list_source or ""
        global_prefix = "global_" if is_global else ""
        if list_source:
            # From-list registration
            lines.append(f"\tcmm_register_{global_prefix}settings_list_from_list = {{")
            lines.append(f"\t\tmod_id = {mod_id}")
            lines.append(f"\t\tsetting_id = {setting.setting_id}")
            lines.append(f"\t\ttab_id = {tab_id}")
            lines.append(f"\t\tis_ordered = {_int(setting.is_ordered, 0)}")
            lines.append(f"\t\tlist = {list_source}")
            lines.append(f"\t}}")
        else:
            # Static list registration
            lines.append(f"\tcmm_register_{global_prefix}settings_list = {{")
            lines.append(f"\t\tmod_id = {mod_id}")
            lines.append(f"\t\tsetting_id = {setting.setting_id}")
            lines.append(f"\t\ttab_id = {tab_id}")
            lines.append(f"\t\titem_count = {_int(setting.item_count, 1)}")
            lines.append(f"\t\tis_ordered = {_int(setting.is_ordered, 0)}")
            lines.append(f"\t}}")

            # Item values
            for i, val in enumerate(setting.item_values or [], start=1):
                if val:
                    lines.append("")
                    lines.append(f"\tcmm_set_list_item_value = {{")
                    lines.append(f"\t\tmod_id = {mod_id}")
                    lines.append(f"\t\tsetting_id = {setting.setting_id}")
                    lines.append(f"\t\titem = {i}")
                    lines.append(f"\t\tvalue = {val}")
                    lines.append(f"\t}}")

        # List fields
        for field in (setting.fields or []):
            lines.append("")
            _emit_list_field(lines, mod_id, setting.setting_id, field)

        # List field alias sync (static lists only - item count known)
        if not list_source:
            item_count = _int(setting.item_count, 1)
            for fi, field in enumerate(setting.fields or []):
                slot = fi + 1
                item_aliases = field.item_aliases or []
                alias = _field_has_alias(field, mod_id, setting.setting_id, slot)
                if item_aliases or alias:
                    lines.append("")
                    lines.append(f"\t# Sync list field alias: {field.field_id}")
                    for i in range(1, item_count + 1):
                        resolved_field = f"{qid}_i{i}_f{slot}"
                        # Per-item alias takes precedence over template
                        per_item = (item_aliases[i - 1] if i - 1 < len(item_aliases) else "").strip()
                        if per_item:
                            resolved_alias = per_item
                        elif alias:
                            resolved_alias = alias.replace("$i$", str(i))
                        else:
                            continue
                        lines.append(f"\tcmm_sync_setting_alias = {{")
                        lines.append(f"\t\tsetting = {resolved_field}")
                        lines.append(f"\t\talias = {resolved_alias}")
                        lines.append(f"\t}}")

    if st == "list":
        if setting.no_reset:
            lines.append(f"\tcmm_set_no_reset = {{")
            lines.append(f"\t\tmod_id = {mod_id}")
            lines.append(f"\t\tsetting_id = {setting.setting_id}")
            lines.append(f"\t}}")
        return

    # Determine registration function name
    prefix_map = {
        "bool": "bool_setting",
        "button": "button_setting",
        "numeric": "numeric_setting",
        "slider": "slider_setting",
        "dropdown": "dropdown_setting",
        "text": "text_setting",
    }
    func_name = prefix_map.get(st, st)
    if is_global and st != "text":
        reg_func = f"cmm_register_global_{func_name}"
    else:
        reg_func = f"cmm_register_{func_name}"

    lines.append(f"\t{reg_func} = {{")
    lines.append(f"\t\tmod_id = {mod_id}")
    lines.append(f"\t\tsetting_id = {setting.setting_id}")
    lines.append(f"\t\ttab_id = {tab_id}")
    lines.append(f"\t\tgroup_id = {group_id}")

    if st == "bool":
        lines.append(f"\t\tdefault_value = {_int(setting.default_value, 0)}")
    elif st == "button":
        pass  # no extra params
    elif st in ("numeric", "slider"):
        lines.append(f"\t\tdefault_value = {_num(setting.default_value, 0)}")
        lines.append(f"\t\tmin_value = {_num(setting.min_value, 0)}")
        lines.append(f"\t\tmax_value = {_num(setting.max_value, 100)}")
        lines.append(f"\t\tstep_value = {_num(setting.step_value, 1)}")
    elif st == "dropdown":
        lines.append(f"\t\tdefault_index = {_int(setting.default_index, 1)}")
        lines.append(f"\t\toption_count = {_int(setting.option_count, 1)}")
    elif st == "text":
        lines.append(f"\t\tcharacter_limit = {_int(setting.character_limit, 42)}")
        lines.append(f"\t\tquote_text = {_int(setting.quote_text, 0)}")

    lines.append(f"\t}}")

    # Setting alias sync (runs each registration = menu open)
    alias = _setting_has_alias(setting, mod_id)
    if alias and st not in ("button",):
        if st == "bool":
            sync_func = "cmm_sync_bool_alias_inverted" if setting.alias_inverted else "cmm_sync_bool_alias"
        else:
            sync_func = "cmm_sync_setting_alias"
        lines.append(f"\t{sync_func} = {{")
        lines.append(f"\t\tsetting = {qid}")
        lines.append(f"\t\talias = {alias}")
        lines.append(f"\t}}")

    # Dropdown option alias sync (runs each registration = menu open)
    if st == "dropdown":
        _emit_option_alias_sync(lines, setting, qid, indent="\t")

    # Scripted GUI (is_shown / is_valid)
    if setting.scripted_gui:
        lines.append(f"\tcmm_add_scripted_gui = {{")
        lines.append(f"\t\tmod_id = {mod_id}")
        lines.append(f"\t\tsetting_id = {setting.setting_id}")
        lines.append(f"\t}}")

    # No reset
    if setting.no_reset:
        lines.append(f"\tcmm_set_no_reset = {{")
        lines.append(f"\t\tmod_id = {mod_id}")
        lines.append(f"\t\tsetting_id = {setting.setting_id}")
        lines.append(f"\t}}")


def _emit_list_field(lines: list, mod_id: str, setting_id: str, field: ListField):
    ft = field.field_type
    if ft == "bool":
        lines.append(f"\tcmm_register_list_bool_field = {{")
        lines.append(f"\t\tmod_id = {mod_id}")
        lines.append(f"\t\tsetting_id = {setting_id}")
        lines.append(f"\t\tfield_id = {field.field_id}")
        lines.append(f"\t\tdefault_value = {_int(field.default_value, 0)}")
        lines.append(f"\t}}")
    elif ft == "dropdown":
        lines.append(f"\tcmm_register_list_dropdown_field = {{")
        lines.append(f"\t\tmod_id = {mod_id}")
        lines.append(f"\t\tsetting_id = {setting_id}")
        lines.append(f"\t\tfield_id = {field.field_id}")
        lines.append(f"\t\tdefault_index = {_int(field.default_index, 1)}")
        lines.append(f"\t\toption_count = {_int(field.option_count, 1)}")
        lines.append(f"\t}}")
    elif ft == "numeric":
        lines.append(f"\tcmm_register_list_numeric_field = {{")
        lines.append(f"\t\tmod_id = {mod_id}")
        lines.append(f"\t\tsetting_id = {setting_id}")
        lines.append(f"\t\tfield_id = {field.field_id}")
        lines.append(f"\t\tdefault_value = {_num(field.default_value, 0)}")
        lines.append(f"\t\tmin_value = {_num(field.min_value, 0)}")
        lines.append(f"\t\tmax_value = {_num(field.max_value, 10)}")
        lines.append(f"\t\tstep_value = {_num(field.step_value, 1)}")
        lines.append(f"\t}}")
    elif ft == "slider":
        lines.append(f"\tcmm_register_list_slider_field = {{")
        lines.append(f"\t\tmod_id = {mod_id}")
        lines.append(f"\t\tsetting_id = {setting_id}")
        lines.append(f"\t\tfield_id = {field.field_id}")
        lines.append(f"\t\tdefault_value = {_num(field.default_value, 0)}")
        lines.append(f"\t\tmin_value = {_num(field.min_value, 0)}")
        lines.append(f"\t\tmax_value = {_num(field.max_value, 10)}")
        lines.append(f"\t\tstep_value = {_num(field.step_value, 1)}")
        lines.append(f"\t}}")


def _emit_list_iteration_boilerplate(lines: list, mod_id: str, setting: Setting):
    """Emit a commented-out iteration template for a list setting."""
    qid = f"{mod_id}__{setting.setting_id}"
    fields = setting.fields or []
    has_values = any(v for v in (setting.item_values or [])) or bool(setting.list_source)
    item_count = _int(setting.item_count, 1) if not setting.list_source else "N"

    lines.append("")
    lines.append(f"# ─── How to iterate: {qid} ───")
    lines.append(f"# Call cmm_for_each_list_item to loop through items. It calls your effect")
    lines.append(f"# with $i$ set to the item number, so you can use it in variable names.")
    if has_values:
        lines.append(f"# scope:cmm_list_current_item_value holds the attached game object scope.")
    lines.append(f"# Scope: country")
    lines.append(f"#")
    lines.append(f"# cmm_for_each_list_item = {{")
    lines.append(f"#     setting = {qid}")
    lines.append(f"#     effect = {qid}_each_item")
    lines.append(f"# }}")
    lines.append(f"#")
    lines.append(f"# {qid}_each_item = {{")
    lines.append(f"#     # $i$ is the resolved item number (1-{item_count})")
    if has_values:
        lines.append(f"#     # scope:cmm_list_current_item_value  (attached game object)")
    for fi, field in enumerate(fields):
        slot = fi + 1
        ftype = field.field_type
        fid = field.field_id or f"field_{slot}"
        item_aliases = field.item_aliases or []
        has_per_item = any(a for a in item_aliases)
        if field.alias:
            prefix = "global_var" if setting.is_global else "var"
            lines.append(f'#     # {prefix}:{field.alias}  ({fid}, {ftype})')
        else:
            lines.append(f'#     # "variable_map(cmm|flag:$setting$_i$i$_f{slot})"  ({fid}, {ftype})')
        if has_per_item:
            prefix = "global_var" if setting.is_global else "var"
            lines.append(f'#     # Per-item aliases for {fid}:')
            for ii, ia in enumerate(item_aliases):
                if ia:
                    item_names = setting.item_names or []
                    name = item_names[ii] if ii < len(item_names) else f"Item {ii + 1}"
                    lines.append(f'#     #   {name}: {prefix}:{ia}')
    lines.append(f"# }}")


def _gen_scripted_guis(model: ModModel) -> str:
    mod_id = model.mod_id
    lines = []
    first_block = True

    for tab in model.tabs:
        tab_header_emitted = False
        for group in tab.groups:
            group_header_emitted = False
            for setting in group.settings:
                is_list = setting.setting_type == "list"
                if not is_list and not setting.scripted_gui:
                    continue
                if not first_block:
                    lines.append("")
                first_block = False
                if not tab_header_emitted:
                    lines.append(f"# {tab.name or tab.tab_id} ({tab.tab_id}) Tab")
                    tab_header_emitted = True
                if not group_header_emitted:
                    lines.append(f"## {group.name or group.group_id} ({group.group_id}) Group")
                    group_header_emitted = True
                qid = f"{mod_id}__{setting.setting_id}"
                if is_list:
                    lines.append(_gen_list_callback_block(qid, setting.visible, setting.enabled))
                else:
                    lines.append(_gen_setting_sgui_block(qid, setting.visible, setting.enabled))

    return "\n".join(lines) + "\n"


def _gen_list_callback_block(qid: str, visible: str = None, enabled: str = None) -> str:
    lines = []
    lines.append(f"{qid}_on_changed = {{")
    lines.append(f"\tscope = country")
    if visible:
        lines.append(f"")
        lines.append(f"\tis_shown = {{")
        for vline in visible.strip().splitlines():
            lines.append(f"\t\t{vline.strip()}")
        lines.append(f"\t}}")
    if enabled:
        lines.append(f"")
        lines.append(f"\tis_valid = {{")
        for eline in enabled.strip().splitlines():
            lines.append(f"\t\t{eline.strip()}")
        lines.append(f"\t}}")
    lines.append(f"")
    lines.append(f"\teffect = {{")
    lines.append(f"\t\tcmm_apply_list_change = {{")
    lines.append(f"\t\t\tsetting = {qid}")
    lines.append(f"\t\t}}")
    lines.append(f"\t}}")
    lines.append(f"}}")
    return "\n".join(lines)


def _gen_setting_sgui_block(qid: str, visible: str = None, enabled: str = None) -> str:
    lines = []
    lines.append(f"{qid}_on_changed = {{")
    lines.append(f"\tscope = country")
    if visible:
        lines.append(f"")
        lines.append(f"\tis_shown = {{")
        for vline in visible.strip().splitlines():
            lines.append(f"\t\t{vline.strip()}")
        lines.append(f"\t}}")
    if enabled:
        lines.append(f"")
        lines.append(f"\tis_valid = {{")
        for eline in enabled.strip().splitlines():
            lines.append(f"\t\t{eline.strip()}")
        lines.append(f"\t}}")
    lines.append(f"\teffect = {{ }}")
    lines.append(f"}}")
    return "\n".join(lines)


def _gen_localization(model: ModModel) -> str:
    mod_id = model.mod_id
    lines = []
    lines.append("l_english:")

    # Mod
    lines.append(" # Mod")
    lines.append(f' {mod_id}_name: "{_esc(model.mod_name)}"')
    lines.append(f' {mod_id}_desc: "{_esc(model.mod_desc)}"')

    # Tabs, groups, and settings
    seen_groups = set()
    for tab in model.tabs:
        if not any(g.settings for g in tab.groups):
            continue
        lines.append("")
        lines.append(f" # {tab.name or tab.tab_id} ({tab.tab_id}) Tab")
        lines.append(f' {mod_id}__{tab.tab_id}_name: "{_esc(tab.name or tab.tab_id)}"')

        for group in tab.groups:
            if not group.settings:
                continue
            lines.append(f" ## {group.name or group.group_id} ({group.group_id}) Group")
            if (tab.tab_id, group.group_id) not in seen_groups:
                seen_groups.add((tab.tab_id, group.group_id))
                lines.append(f' {mod_id}__{tab.tab_id}__{group.group_id}_name: "{_esc(group.name or group.group_id)}"')
                if group.desc:
                    lines.append(f' {mod_id}__{tab.tab_id}__{group.group_id}_desc: "{_esc(group.desc)}"')

            for setting in group.settings:
                _emit_setting_loc(lines, mod_id, setting)

    # Self-referencing flag keys (optional, safe to remove — no EU5 errors/warnings will occur)
    flag_keys = [mod_id]
    for tab in model.tabs:
        flag_keys.append(f"{mod_id}__{tab.tab_id}")
    seen_flag_groups = set()
    for tab in model.tabs:
        for group in tab.groups:
            if (tab.tab_id, group.group_id) not in seen_flag_groups:
                seen_flag_groups.add((tab.tab_id, group.group_id))
                flag_keys.append(f"{mod_id}__{tab.tab_id}__{group.group_id}")
    for tab in model.tabs:
        for group in tab.groups:
            for setting in group.settings:
                flag_keys.append(f"{mod_id}__{setting.setting_id}")
                if setting.setting_type == "list":
                    for field in (setting.fields or []):
                        flag_keys.append(f"{mod_id}__{setting.setting_id}__{field.field_id}")

    lines.append("")
    lines.append(" # Optional: self-referencing flag keys to suppress IDE warnings (safe to remove if you want)")
    for key in flag_keys:
        lines.append(f' {key}: "{key}"')

    return "\n".join(lines) + "\n"


def _emit_setting_loc(lines: list, mod_id: str, setting: Setting):
    qid = f"{mod_id}__{setting.setting_id}"
    st = setting.setting_type

    if st == "list":
        # Lists use the group name as their display name; no setting-level name/desc.
        lines.append(f' {qid}_item_column_name: "{_esc(setting.item_column_name or "Item")}"')
        if not setting.list_source:
            for i, name in enumerate(setting.item_names or [], start=1):
                lines.append(f' {qid}_i{i}_name: "{_esc(name)}"')

        for field in (setting.fields or []):
            fqid = f"{qid}__{field.field_id}"
            lines.append(f' {fqid}_name: "{_esc(field.name or field.field_id)}"')
            if field.field_type == "dropdown":
                for opt in (field.options or []):
                    lines.append(f' {fqid}_option_{opt.index}_name: "{_esc(opt.name)}"')
                    if opt.desc:
                        lines.append(f' {fqid}_option_{opt.index}_desc: "{_esc(opt.desc)}"')
        return

    lines.append(f' {qid}_name: "{_esc(setting.name or setting.setting_id)}"')
    lines.append(f' {qid}_desc: "{_esc(setting.desc)}"')

    if st in ("numeric", "slider") and setting.display_format:
        fmt = _esc(setting.display_format).replace("$VALUE$", f"[CMMV('{qid}')]")
        lines.append(f' {qid}_format: "{fmt}"')

    if st == "button":
        lines.append(f' {qid}_text: "{_esc(setting.button_text or "Run")}"')

    elif st == "dropdown":
        for opt in (setting.options or []):
            lines.append(f' {qid}_option_{opt.index}_name: "{_esc(opt.name)}"')
            if opt.desc:
                lines.append(f' {qid}_option_{opt.index}_desc: "{_esc(opt.desc)}"')


def _gen_metadata(model: ModModel) -> str:
    data = {
        "name": model.metadata_name or model.mod_name,
        "id": model.metadata_id,
        "version": model.metadata_version,
        "game_id": "eu5",
        "supported_game_version": model.metadata_game_version,
        "short_description": model.metadata_short_description or model.mod_desc,
        "tags": model.metadata_tags,
        "relationships": [
            {
                "rel_type": "dependency",
                "id": "community_mod_framework",
                "display_name": "Community Mod Framework",
                "resource_type": "mod",
                "version": "2.*",
            }
        ],
        "game_custom_data": {},
    }
    return json.dumps(data, indent=4, ensure_ascii=False)


def _int(v, default=0) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _num(v, default=0):
    if v is None:
        return default
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return default


def _esc(s: str) -> str:
    """Escape a string for Paradox localization YAML."""
    if not s:
        return ""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def merge_with_existing(generated_files: dict, output_dir: Path) -> dict:
    """Merge generated files with existing ones, preserving custom callbacks."""
    merged = dict(generated_files)

    for filepath, content in generated_files.items():
        existing_path = output_dir / filepath
        if not existing_path.is_file():
            continue

        try:
            existing = decode_bom(existing_path.read_bytes())
        except Exception:
            continue

        if "scripted_gui" in filepath:
            merged[filepath] = _merge_scripted_guis(content, existing)
        elif "effects" in filepath:
            merged[filepath] = _merge_effects(content, existing)

    return merged


def _merge_scripted_guis(generated: str, existing: str) -> str:
    """Preserve existing _on_changed blocks, append only new ones."""
    existing_names = set(re.findall(r"(\w+_on_changed)\s*=\s*\{", existing))
    generated_blocks = _extract_named_blocks(generated, "_on_changed")

    new_blocks = []
    for name, block_text in generated_blocks.items():
        if name not in existing_names:
            new_blocks.append(block_text)

    if new_blocks:
        return existing.rstrip() + "\n\n" + "\n\n".join(new_blocks) + "\n"
    return existing


def _merge_effects(generated: str, existing: str) -> str:
    """Overwrite registration and callback handler blocks, preserve existing text callbacks."""
    result = generated
    existing_blocks = _extract_named_blocks(existing, "_on_changed")
    for name, existing_block in existing_blocks.items():
        gen_blocks = _extract_named_blocks(result, "_on_changed")
        if name in gen_blocks:
            result = result.replace(gen_blocks[name], existing_block)
    return result


def _extract_named_blocks(content: str, suffix: str) -> dict:
    """Extract top-level named blocks ending with suffix."""
    blocks = {}
    pattern = re.compile(rf"^(\w+{re.escape(suffix)})\s*=\s*\{{", re.MULTILINE)
    for m in pattern.finditer(content):
        name = m.group(1)
        brace_start = m.end()
        depth = 1
        i = brace_start
        while i < len(content) and depth > 0:
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
            i += 1
        if depth == 0:
            blocks[name] = content[m.start():i]
    return blocks
