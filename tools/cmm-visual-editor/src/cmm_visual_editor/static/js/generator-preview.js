/**
 * Client-side code generator for instant preview.
 * Mirrors the Python generator.py logic.
 */
const CMMGenerator = {
    generateAll(state) {
        const prefix = state.file_prefix || state.mod_id;
        const modId = state.mod_id;
        if (!modId) return {};
        return {
            [`in_game/common/on_action/${prefix}_cmm_on_action.txt`]: this.genOnAction(prefix),
            [`in_game/common/scripted_effects/${prefix}_cmm_effects.txt`]: this.genEffects(state),
            [`in_game/common/scripted_guis/${prefix}_cmm_scripted_gui.txt`]: this.genScriptedGuis(state),
            [`main_menu/localization/english/${prefix}_cmm_l_english.yml`]: this.genLocalization(state),
            ['.metadata/metadata.json']: this.genMetadata(state),
        };
    },

    genOnAction(prefix) {
        return `# Hook this mod into CMM shared registration on_action.
cmm_on_mod_registration = {
\ton_actions = {
\t\t${prefix}_on_register_mod
\t}
}

${prefix}_on_register_mod = {
\teffect = {
\t\t${prefix}_register_mod = yes
\t}
}
`;
    },

    genEffects(state) {
        const prefix = state.file_prefix || state.mod_id;
        const modId = state.mod_id;
        const lines = [];
        lines.push('# Root scope: country.');
        lines.push(`${prefix}_register_mod = {`);

        let first = true;
        for (const tab of (state.tabs || [])) {
            for (const group of (tab.groups || [])) {
                for (const setting of (group.settings || [])) {
                    if (!first) lines.push('');
                    first = false;
                    this._emitRegistration(lines, modId, tab.tab_id, group.group_id, setting);
                }
            }
        }
        lines.push('}');

        // List iteration boilerplate
        for (const tab of (state.tabs || [])) {
            for (const group of (tab.groups || [])) {
                for (const setting of (group.settings || [])) {
                    if (setting.setting_type === 'list' && (setting.fields || []).length > 0) {
                        this._emitListIterationBoilerplate(lines, modId, setting);
                    }
                }
            }
        }

        // Text effects
        for (const tab of (state.tabs || [])) {
            for (const group of (tab.groups || [])) {
                for (const setting of (group.settings || [])) {
                    if (setting.setting_type === 'text') {
                        const qid = `${modId}__${setting.setting_id}`;
                        lines.push('');
                        lines.push(`${qid}_on_changed = {`);
                        if (setting.on_changed_effect) {
                            if (!setting.no_pass_value) {
                                const param = setting.pass_value_param || 'value';
                                lines.push(`\t${setting.on_changed_effect} = {`);
                                lines.push(`\t\t${param} = $text$`);
                                lines.push(`\t}`);
                            } else {
                                lines.push(`\t${setting.on_changed_effect} = yes`);
                            }
                        } else {
                            lines.push(`\t# Custom text handling effect. Uses $text$ parameter.`);
                            lines.push(`\t# Replace this placeholder with your actual effect logic.`);
                            lines.push(`\tlog = "Text submitted: $text$"`);
                        }
                        lines.push('}');
                    }
                }
            }
        }

        return lines.join('\n') + '\n';
    },

    _emitRegistration(lines, modId, tabId, groupId, setting) {
        const st = setting.setting_type;
        if (st === 'list') {
            const listSource = setting.list_source || '';
            if (listSource) {
                lines.push(`\tcmm_register_settings_list_from_list = {`);
                lines.push(`\t\tmod_id = ${modId}`);
                lines.push(`\t\tsetting_id = ${setting.setting_id}`);
                lines.push(`\t\ttab_id = ${tabId}`);
                lines.push(`\t\tis_ordered = ${setting.is_ordered || 0}`);
                lines.push(`\t\tlist = ${listSource}`);
                lines.push(`\t}`);
            } else {
                lines.push(`\tcmm_register_settings_list = {`);
                lines.push(`\t\tmod_id = ${modId}`);
                lines.push(`\t\tsetting_id = ${setting.setting_id}`);
                lines.push(`\t\ttab_id = ${tabId}`);
                lines.push(`\t\titem_count = ${setting.item_count || 1}`);
                lines.push(`\t\tis_ordered = ${setting.is_ordered || 0}`);
                lines.push(`\t}`);

                for (let i = 0; i < (setting.item_values || []).length; i++) {
                    const val = setting.item_values[i];
                    if (val) {
                        lines.push('');
                        lines.push(`\tcmm_set_list_item_value = {`);
                        lines.push(`\t\tmod_id = ${modId}`);
                        lines.push(`\t\tsetting_id = ${setting.setting_id}`);
                        lines.push(`\t\titem = ${i + 1}`);
                        lines.push(`\t\tvalue = ${val}`);
                        lines.push(`\t}`);
                    }
                }
            }
            for (const field of (setting.fields || [])) {
                lines.push('');
                this._emitListField(lines, modId, setting.setting_id, field);
            }
            return;
        }

        const prefixMap = { bool: 'bool_setting', button: 'button_setting', numeric: 'numeric_setting', slider: 'slider_setting', dropdown: 'dropdown_setting', text: 'text_setting' };
        const funcName = prefixMap[st] || st;
        const regFunc = (setting.is_global && !['text', 'list'].includes(st)) ? `cmm_register_global_${funcName}` : `cmm_register_${funcName}`;

        lines.push(`\t${regFunc} = {`);
        lines.push(`\t\tmod_id = ${modId}`);
        lines.push(`\t\tsetting_id = ${setting.setting_id}`);
        lines.push(`\t\ttab_id = ${tabId}`);
        lines.push(`\t\tgroup_id = ${groupId}`);

        if (st === 'bool') {
            lines.push(`\t\tdefault_value = ${setting.default_value || 0}`);
        } else if (st === 'button') {
            // no extra params
        } else if (st === 'numeric' || st === 'slider') {
            lines.push(`\t\tdefault_value = ${this._num(setting.default_value, 0)}`);
            lines.push(`\t\tmin_value = ${this._num(setting.min_value, 0)}`);
            lines.push(`\t\tmax_value = ${this._num(setting.max_value, 100)}`);
            lines.push(`\t\tstep_value = ${this._num(setting.step_value, 1)}`);
        } else if (st === 'dropdown') {
            lines.push(`\t\tdefault_index = ${setting.default_index || 1}`);
            lines.push(`\t\toption_count = ${setting.option_count || 1}`);
        } else if (st === 'text') {
            lines.push(`\t\tcharacter_limit = ${setting.character_limit || 42}`);
            lines.push(`\t\tquote_text = ${setting.quote_text || 0}`);
        }
        lines.push(`\t}`);
    },

    _emitListField(lines, modId, settingId, field) {
        const ft = field.field_type;
        if (ft === 'bool') {
            lines.push(`\tcmm_register_list_bool_field = {`);
            lines.push(`\t\tmod_id = ${modId}`);
            lines.push(`\t\tsetting_id = ${settingId}`);
            lines.push(`\t\tfield_id = ${field.field_id}`);
            lines.push(`\t\tdefault_value = ${field.default_value || 0}`);
            lines.push(`\t}`);
        } else if (ft === 'dropdown') {
            lines.push(`\tcmm_register_list_dropdown_field = {`);
            lines.push(`\t\tmod_id = ${modId}`);
            lines.push(`\t\tsetting_id = ${settingId}`);
            lines.push(`\t\tfield_id = ${field.field_id}`);
            lines.push(`\t\tdefault_index = ${field.default_index || 1}`);
            lines.push(`\t\toption_count = ${field.option_count || 1}`);
            lines.push(`\t}`);
        } else if (ft === 'numeric') {
            lines.push(`\tcmm_register_list_numeric_field = {`);
            lines.push(`\t\tmod_id = ${modId}`);
            lines.push(`\t\tsetting_id = ${settingId}`);
            lines.push(`\t\tfield_id = ${field.field_id}`);
            lines.push(`\t\tdefault_value = ${this._num(field.default_value, 0)}`);
            lines.push(`\t\tmin_value = ${this._num(field.min_value, 0)}`);
            lines.push(`\t\tmax_value = ${this._num(field.max_value, 10)}`);
            lines.push(`\t\tstep_value = ${this._num(field.step_value, 1)}`);
            lines.push(`\t}`);
        }
    },

    _emitListIterationBoilerplate(lines, modId, setting) {
        const qid = `${modId}__${setting.setting_id}`;
        const itemCount = setting.list_source ? 'N' : (setting.item_count || 1);
        const fields = setting.fields || [];
        const hasValues = (setting.item_values || []).some(v => v) || !!setting.list_source;

        lines.push('');
        lines.push(`# ─── How to iterate: ${qid} ───`);
        lines.push(`# Call cmm_for_each_list_item to loop through items. It calls your effect`);
        lines.push(`# with $i$ set to the item number, so you can use it in variable names.`);
        if (hasValues) {
            lines.push(`# scope:cmm_list_current_item_value holds the attached game object scope.`);
        }
        lines.push(`# Scope: country`);
        lines.push(`#`);
        lines.push(`# cmm_for_each_list_item = {`);
        lines.push(`#     setting = ${qid}`);
        lines.push(`#     effect = ${qid}_each_item`);
        lines.push(`# }`);
        lines.push(`#`);
        lines.push(`# ${qid}_each_item = {`);
        lines.push(`#     # $i$ is the resolved item number (1-${itemCount})`);
        if (hasValues) {
            lines.push(`#     # scope:cmm_list_current_item_value  (attached game object)`);
        }
        for (let fi = 0; fi < fields.length; fi++) {
            const slot = fi + 1;
            const ftype = fields[fi].field_type;
            const fid = fields[fi].field_id || `field_${slot}`;
            lines.push(`#     # var:$setting$_item_$i$_field_${slot}  (${fid}, ${ftype})`);
        }
        lines.push(`# }`);
    },

    genScriptedGuis(state) {
        const modId = state.mod_id;
        const blocks = [];
        for (const tab of (state.tabs || [])) {
            for (const group of (tab.groups || [])) {
                for (const setting of (group.settings || [])) {
                    if (setting.setting_type === 'text') continue;
                    const qid = `${modId}__${setting.setting_id}`;
                    blocks.push(this._genCallback(setting, qid));
                }
            }
        }
        return blocks.join('\n\n') + '\n';
    },

    _genCallback(setting, qid) {
        const st = setting.setting_type;
        const varPrefix = setting.is_global ? 'global_var' : 'var';
        const lines = [];
        lines.push(`${qid}_on_changed = {`);
        lines.push(`\tscope = country`);
        lines.push('');
        lines.push(`\teffect = {`);

        if (st === 'bool') {
            lines.push(`\t\tcmm_toggle_bool_setting = {`);
            lines.push(`\t\t\tsetting = ${qid}`);
            lines.push(`\t\t}`);
        } else if (st === 'button') {
            // no CMM helper for buttons
        } else if (st === 'numeric') {
            lines.push(`\t\tcmm_apply_numeric_change = {`);
            lines.push(`\t\t\tsetting = ${qid}`);
            lines.push(`\t\t}`);
        } else if (st === 'slider') {
            lines.push(`\t\tcmm_apply_slider_change = {`);
            lines.push(`\t\t\tsetting = ${qid}`);
            lines.push(`\t\t}`);
        } else if (st === 'dropdown') {
            lines.push(`\t\tcmm_apply_dropdown_change = {`);
            lines.push(`\t\t\tsetting = ${qid}`);
            lines.push(`\t\t}`);
        } else if (st === 'list') {
            lines.push(`\t\tcmm_apply_list_change = {`);
            lines.push(`\t\t\tsetting = ${qid}`);
            lines.push(`\t\t}`);
        }

        // Custom effect call
        if (setting.on_changed_effect) {
            lines.push('');
            if (!setting.no_pass_value && !['button', 'list'].includes(st)) {
                const param = setting.pass_value_param || 'value';
                lines.push(`\t\t${setting.on_changed_effect} = {`);
                lines.push(`\t\t\t${param} = ${varPrefix}:${qid}`);
                lines.push(`\t\t}`);
            } else {
                lines.push(`\t\t${setting.on_changed_effect} = yes`);
            }
        } else if (st === 'button') {
            lines.push(`\t\t# Button effect`);
        }

        lines.push(`\t}`);
        lines.push(`}`);
        return lines.join('\n');
    },

    genLocalization(state) {
        const modId = state.mod_id;
        const lines = [];
        lines.push('l_english:');
        lines.push(' # Mod');
        lines.push(` ${modId}_name: "${this._esc(state.mod_name)}"`);
        lines.push(` ${modId}_desc: "${this._esc(state.mod_desc)}"`);

        if (state.tabs && state.tabs.length) {
            lines.push('');
            lines.push(' # Tabs');
            for (const tab of state.tabs) {
                lines.push(` ${modId}__${tab.tab_id}_name: "${this._esc(tab.name)}"`);
            }

            const seenGroups = {};
            for (const tab of state.tabs) {
                for (const group of (tab.groups || [])) {
                    if (!seenGroups[group.group_id]) {
                        seenGroups[group.group_id] = group.name;
                    }
                }
            }
            if (Object.keys(seenGroups).length) {
                lines.push('');
                lines.push(' # Groups');
                for (const [gid, gname] of Object.entries(seenGroups)) {
                    lines.push(` ${modId}__${gid}_name: "${this._esc(gname)}"`);
                }
            }

            for (const tab of state.tabs) {
                for (const group of (tab.groups || [])) {
                    if (group.settings && group.settings.length) {
                        lines.push('');
                        lines.push(` # ${tab.name || tab.tab_id} Tab - ${group.name || group.group_id}`);
                        for (const s of group.settings) {
                            this._emitSettingLoc(lines, modId, s);
                        }
                    }
                }
            }
        }

        return lines.join('\n') + '\n';
    },

    _emitSettingLoc(lines, modId, setting) {
        const qid = `${modId}__${setting.setting_id}`;
        lines.push(` ${qid}_name: "${this._esc(setting.name)}"`);
        lines.push(` ${qid}_desc: "${this._esc(setting.desc)}"`);

        if (setting.setting_type === 'button') {
            lines.push(` ${qid}_text: "${this._esc(setting.button_text || 'Run')}"`);
        } else if (setting.setting_type === 'dropdown') {
            for (const opt of (setting.options || [])) {
                lines.push(` ${qid}_option_${opt.index}_name: "${this._esc(opt.name)}"`);
            }
        } else if (setting.setting_type === 'list') {
            lines.push(` ${qid}_item_column_name: "${this._esc(setting.item_column_name || 'Item')}"`);
            if (!setting.list_source) {
                for (let i = 0; i < (setting.item_names || []).length; i++) {
                    lines.push(` ${qid}_item_${i + 1}_name: "${this._esc(setting.item_names[i])}"`);
                }
            }
            for (const field of (setting.fields || [])) {
                const fqid = `${qid}__${field.field_id}`;
                lines.push(` ${fqid}_name: "${this._esc(field.name)}"`);
                if (field.field_type === 'dropdown') {
                    for (const opt of (field.options || [])) {
                        lines.push(` ${fqid}_option_${opt.index}_name: "${this._esc(opt.name)}"`);
                    }
                }
            }
        }
    },

    genMetadata(state) {
        return JSON.stringify({
            name: state.metadata_name || state.mod_name,
            id: state.metadata_id,
            version: state.metadata_version,
            game_id: "eu5",
            supported_game_version: state.metadata_game_version,
            short_description: state.metadata_short_description || state.mod_desc,
            tags: state.metadata_tags,
            relationships: [{
                rel_type: "dependency",
                id: "community.mod.framework",
                display_name: "Community Mod Framework",
                resource_type: "mod",
                version: "*",
            }],
            game_custom_data: {},
        }, null, 4);
    },

    _num(v, def) {
        const n = Number(v);
        return isNaN(n) ? def : (n === Math.floor(n) ? n : n);
    },

    _esc(s) {
        if (!s) return '';
        return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    },
};
