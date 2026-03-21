/**
 * Client-side code generator for instant preview.
 * Mirrors the Python generator.py logic.
 */
const CMMGenerator = {
    generateAll(state) {
        const prefix = state.file_prefix || state.mod_id;
        const modId = state.mod_id;
        if (!modId) return {};
        const hasLists = (state.tabs || []).some(t =>
            (t.groups || []).some(g =>
                (g.settings || []).some(s => s.setting_type === 'list')
            )
        );
        const files = {
            [`in_game/common/on_action/${prefix}_cmm_on_action.txt`]: this.genOnAction(prefix),
            [`in_game/common/scripted_effects/${prefix}_cmm_effects.txt`]: this.genEffects(state),
            [`main_menu/localization/english/${prefix}_cmm_l_english.yml`]: this.genLocalization(state),
            ['.metadata/metadata.json']: this.genMetadata(state),
        };
        if (hasLists) {
            files[`in_game/common/scripted_guis/${prefix}_cmm_scripted_gui.txt`] = this.genScriptedGuis(state);
        }
        return files;
    },

    genOnAction(prefix) {
        return `# Hook this mod into CMF shared registration on_action.
cmf_on_mod_registration = {
\ton_actions = {
\t\t${prefix}_on_register_cmf_mod
\t}
}

${prefix}_on_register_cmf_mod = {
\teffect = {
\t\t${prefix}_register_cmf_mod = yes
\t}
}

# Unified callback hook for setting changes, alert clicks, action bar clicks.
cmf_on_callback = {
\ton_actions = {
\t\t${prefix}_on_cmf_callback
\t}
}

${prefix}_on_cmf_callback = {
\teffect = {
\t\t${prefix}_handle_cmf_callback = yes
\t}
}
`;
    },

    genEffects(state) {
        const prefix = state.file_prefix || state.mod_id;
        const modId = state.mod_id;
        const lines = [];
        lines.push('# Root scope: country.');
        lines.push(`${prefix}_register_cmf_mod = {`);

        let firstTab = true;
        for (const tab of (state.tabs || [])) {
            const hasSettings = (tab.groups || []).some(g => (g.settings || []).length > 0);
            if (!hasSettings) continue;
            if (!firstTab) lines.push('');
            firstTab = false;
            lines.push(`\t# ${tab.name || tab.tab_id} (${tab.tab_id}) Tab`);
            let firstGroup = true;
            for (const group of (tab.groups || [])) {
                if (!(group.settings || []).length) continue;
                if (!firstGroup) lines.push('');
                firstGroup = false;
                lines.push(`\t## ${group.name || group.group_id} (${group.group_id}) Group`);
                let firstSetting = true;
                for (const setting of (group.settings || [])) {
                    if (!firstSetting) lines.push('');
                    firstSetting = false;
                    this._emitRegistration(lines, modId, tab.tab_id, group.group_id, setting);
                }
            }
        }
        lines.push('}');

        // List iteration boilerplate
        for (const tab of (state.tabs || [])) {
            let tabHeaderEmitted = false;
            for (const group of (tab.groups || [])) {
                let groupHeaderEmitted = false;
                for (const setting of (group.settings || [])) {
                    if (setting.setting_type === 'list' && (setting.fields || []).length > 0) {
                        if (!tabHeaderEmitted) {
                            lines.push('');
                            lines.push(`# ${tab.name || tab.tab_id} (${tab.tab_id}) Tab`);
                            tabHeaderEmitted = true;
                        }
                        if (!groupHeaderEmitted) {
                            lines.push(`## ${group.name || group.group_id} (${group.group_id}) Group`);
                            groupHeaderEmitted = true;
                        }
                        this._emitListIterationBoilerplate(lines, modId, setting);
                    }
                }
            }
        }

        // Callback handler effect
        this._emitCallbackHandler(lines, state);

        // Text effects
        for (const tab of (state.tabs || [])) {
            let tabHeaderEmitted = false;
            for (const group of (tab.groups || [])) {
                let groupHeaderEmitted = false;
                for (const setting of (group.settings || [])) {
                    if (setting.setting_type === 'text') {
                        if (!tabHeaderEmitted) {
                            lines.push('');
                            lines.push(`# ${tab.name || tab.tab_id} (${tab.tab_id}) Tab`);
                            tabHeaderEmitted = true;
                        }
                        if (!groupHeaderEmitted) {
                            lines.push(`## ${group.name || group.group_id} (${group.group_id}) Group`);
                            groupHeaderEmitted = true;
                        }
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

    _settingHasAlias(setting, modId) {
        const alias = (setting.alias || '').trim();
        if (!alias) return '';
        const defaultKey = `${modId}__${setting.setting_id}`;
        return alias === defaultKey ? '' : alias;
    },

    _fieldHasAlias(field, modId, settingId, slot) {
        const alias = (field.alias || '').trim();
        if (!alias) return '';
        const defaultKey = `${modId}__${settingId}_i$i$_f${slot}`;
        return alias === defaultKey ? '' : alias;
    },

    _getOptionAliases(setting) {
        const aliases = [];
        for (const opt of (setting.options || [])) {
            const a = (opt.alias || '').trim();
            if (a) aliases.push([opt.index, a]);
        }
        return aliases;
    },

    _emitOptionAliasSync(lines, setting, qid, indent) {
        const aliases = this._getOptionAliases(setting);
        if (!aliases.length) return;
        for (const [idx, alias] of aliases) {
            lines.push(`${indent}cmm_sync_dropdown_option_alias = {`);
            lines.push(`${indent}\tsetting = ${qid}`);
            lines.push(`${indent}\tindex = ${idx}`);
            lines.push(`${indent}\talias = ${alias}`);
            lines.push(`${indent}}`);
        }
    },

    _emitRegistration(lines, modId, tabId, groupId, setting) {
        const st = setting.setting_type;
        const qid = `${modId}__${setting.setting_id}`;
        if (st === 'list') {
            const listSource = setting.list_source || '';
            const globalPrefix = setting.is_global ? 'global_' : '';
            if (listSource) {
                lines.push(`\tcmm_register_${globalPrefix}settings_list_from_list = {`);
                lines.push(`\t\tmod_id = ${modId}`);
                lines.push(`\t\tsetting_id = ${setting.setting_id}`);
                lines.push(`\t\ttab_id = ${tabId}`);
                lines.push(`\t\tis_ordered = ${setting.is_ordered || 0}`);
                lines.push(`\t\tlist = ${listSource}`);
                lines.push(`\t}`);
            } else {
                lines.push(`\tcmm_register_${globalPrefix}settings_list = {`);
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

            // List field alias sync (static lists only)
            if (!listSource) {
                const itemCount = setting.item_count || 1;
                for (let fi = 0; fi < (setting.fields || []).length; fi++) {
                    const field = setting.fields[fi];
                    const slot = fi + 1;
                    const alias = this._fieldHasAlias(field, modId, setting.setting_id, slot);
                    if (alias) {
                        lines.push('');
                        lines.push(`\t# Sync list field alias: ${field.field_id}`);
                        for (let i = 1; i <= itemCount; i++) {
                            const resolvedField = `${qid}_i${i}_f${slot}`;
                            const resolvedAlias = alias.replace(/\$i\$/g, String(i));
                            lines.push(`\tcmm_sync_setting_alias = {`);
                            lines.push(`\t\tsetting = ${resolvedField}`);
                            lines.push(`\t\talias = ${resolvedAlias}`);
                            lines.push(`\t}`);
                        }
                    }
                }
            }
            return;
        }

        const prefixMap = { bool: 'bool_setting', button: 'button_setting', numeric: 'numeric_setting', slider: 'slider_setting', dropdown: 'dropdown_setting', text: 'text_setting' };
        const funcName = prefixMap[st] || st;
        const regFunc = (setting.is_global && st !== 'text') ? `cmm_register_global_${funcName}` : `cmm_register_${funcName}`;

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

        // Setting alias sync
        const alias = this._settingHasAlias(setting, modId);
        if (alias && st !== 'button') {
            const syncFunc = st === 'bool' ? 'cmm_sync_bool_alias' : 'cmm_sync_setting_alias';
            lines.push(`\t${syncFunc} = {`);
            lines.push(`\t\tsetting = ${qid}`);
            lines.push(`\t\talias = ${alias}`);
            lines.push(`\t}`);
        }

        // Dropdown option alias sync
        if (st === 'dropdown') {
            this._emitOptionAliasSync(lines, setting, qid, '\t');
        }
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
            lines.push(`#     # "variable_map(cmm|flag:$setting$_i$i$_f${slot})"  (${fid}, ${ftype})`);
        }
        lines.push(`# }`);
    },

    genScriptedGuis(state) {
        const modId = state.mod_id;
        const lines = [];
        let firstBlock = true;
        for (const tab of (state.tabs || [])) {
            let tabHeaderEmitted = false;
            for (const group of (tab.groups || [])) {
                let groupHeaderEmitted = false;
                for (const setting of (group.settings || [])) {
                    if (setting.setting_type !== 'list') continue;
                    if (!firstBlock) lines.push('');
                    firstBlock = false;
                    if (!tabHeaderEmitted) {
                        lines.push(`# ${tab.name || tab.tab_id} (${tab.tab_id}) Tab`);
                        tabHeaderEmitted = true;
                    }
                    if (!groupHeaderEmitted) {
                        lines.push(`## ${group.name || group.group_id} (${group.group_id}) Group`);
                        groupHeaderEmitted = true;
                    }
                    const qid = `${modId}__${setting.setting_id}`;
                    lines.push(this._genListCallback(qid));
                }
            }
        }
        return lines.join('\n') + '\n';
    },

    _genListCallback(qid) {
        const lines = [];
        lines.push(`${qid}_on_changed = {`);
        lines.push(`\tscope = country`);
        lines.push('');
        lines.push(`\teffect = {`);
        lines.push(`\t\tcmm_apply_list_change = {`);
        lines.push(`\t\t\tsetting = ${qid}`);
        lines.push(`\t\t}`);
        lines.push(`\t}`);
        lines.push(`}`);
        return lines.join('\n');
    },

    _emitCallbackHandler(lines, state) {
        const prefix = state.file_prefix || state.mod_id;
        const modId = state.mod_id;

        // Collect cases with tab/group context
        const cases = [];
        for (const tab of (state.tabs || [])) {
            for (const group of (tab.groups || [])) {
                for (const setting of (group.settings || [])) {
                    const st = setting.setting_type;
                    if (st === 'text' || st === 'list') continue;
                    const qid = `${modId}__${setting.setting_id}`;
                    const alias = st !== 'button' ? this._settingHasAlias(setting, modId) : '';
                    const optionAliases = st === 'dropdown' ? this._getOptionAliases(setting) : [];
                    const customEffect = setting.on_changed_effect || '';
                    if (alias || optionAliases.length || customEffect) {
                        cases.push({ tabId: tab.tab_id, tabName: tab.name || tab.tab_id, groupId: group.group_id, groupName: group.name || group.group_id, qid, st, alias, optionAliases, customEffect });
                    }
                }
            }
        }

        lines.push('');
        lines.push(`# Callback handler for cmf_on_callback.`);
        lines.push(`# var:cmf_callback is the flag of the setting, alert, or action bar element that was interacted with.`);
        lines.push(`# Scope: country`);
        lines.push(`${prefix}_handle_cmf_callback = {`);
        lines.push(`\tswitch = {`);
        lines.push(`\t\ttrigger = var:cmf_callback`);

        if (cases.length) {
            let currentTab = null;
            let currentGroup = null;
            for (const c of cases) {
                if (c.tabId !== currentTab) {
                    lines.push(`\t\t# ${c.tabName} (${c.tabId}) Tab`);
                    currentTab = c.tabId;
                    currentGroup = null;
                }
                if (c.groupId !== currentGroup) {
                    lines.push(`\t\t## ${c.groupName} (${c.groupId}) Group`);
                    currentGroup = c.groupId;
                }
                lines.push(`\t\tflag:${c.qid} = {`);
                if (c.alias) {
                    const syncFunc = c.st === 'bool' ? 'cmm_sync_bool_alias' : 'cmm_sync_setting_alias';
                    lines.push(`\t\t\t${syncFunc} = {`);
                    lines.push(`\t\t\t\tsetting = ${c.qid}`);
                    lines.push(`\t\t\t\talias = ${c.alias}`);
                    lines.push(`\t\t\t}`);
                }
                for (const [idx, optAlias] of c.optionAliases) {
                    lines.push(`\t\t\tcmm_sync_dropdown_option_alias = {`);
                    lines.push(`\t\t\t\tsetting = ${c.qid}`);
                    lines.push(`\t\t\t\tindex = ${idx}`);
                    lines.push(`\t\t\t\talias = ${optAlias}`);
                    lines.push(`\t\t\t}`);
                }
                if (c.customEffect) {
                    lines.push(`\t\t\t${c.customEffect} = yes`);
                }
                lines.push(`\t\t}`);
            }
        } else {
            lines.push(`\t\t# flag:${modId}__my_setting = {`);
            lines.push(`\t\t# \t# Custom side effects when this setting changes`);
            lines.push(`\t\t# }`);
        }

        lines.push(`\t}`);
        lines.push(`}`);
    },

    genLocalization(state) {
        const modId = state.mod_id;
        const lines = [];
        lines.push('l_english:');
        lines.push(' # Mod');
        lines.push(` ${modId}_name: "${this._esc(state.mod_name)}"`);
        lines.push(` ${modId}_desc: "${this._esc(state.mod_desc)}"`);

        // Tabs, groups, and settings
        const seenGroups = new Set();
        for (const tab of (state.tabs || [])) {
            const hasContent = (tab.groups || []).some(g => (g.settings || []).length > 0);
            if (!hasContent) continue;
            lines.push('');
            lines.push(` # ${tab.name || tab.tab_id} (${tab.tab_id}) Tab`);
            lines.push(` ${modId}__${tab.tab_id}_name: "${this._esc(tab.name || tab.tab_id)}"`);

            for (const group of (tab.groups || [])) {
                if (!(group.settings || []).length) continue;
                lines.push(` ## ${group.name || group.group_id} (${group.group_id}) Group`);
                if (!seenGroups.has(group.group_id)) {
                    seenGroups.add(group.group_id);
                    lines.push(` ${modId}__${group.group_id}_name: "${this._esc(group.name || group.group_id)}"`);
                    if (group.desc) {
                        lines.push(` ${modId}__${group.group_id}_desc: "${this._esc(group.desc)}"`);
                    }
                }
                for (const s of group.settings) {
                    this._emitSettingLoc(lines, modId, s);
                }
            }
        }

        // Self-referencing flag keys (suppress engine localization warnings)
        const flagKeys = [modId];
        for (const tab of (state.tabs || [])) {
            flagKeys.push(`${modId}__${tab.tab_id}`);
        }
        const seenFlagGroupIds = new Set();
        for (const tab of (state.tabs || [])) {
            for (const group of (tab.groups || [])) {
                if (!seenFlagGroupIds.has(group.group_id)) {
                    seenFlagGroupIds.add(group.group_id);
                    flagKeys.push(`${modId}__${group.group_id}`);
                }
            }
        }
        for (const tab of (state.tabs || [])) {
            for (const group of (tab.groups || [])) {
                for (const s of (group.settings || [])) {
                    flagKeys.push(`${modId}__${s.setting_id}`);
                    if (s.setting_type === 'list') {
                        for (const field of (s.fields || [])) {
                            flagKeys.push(`${modId}__${s.setting_id}__${field.field_id}`);
                        }
                    }
                }
            }
        }

        lines.push('');
        lines.push(' # Optional: self-referencing flag keys to suppress IDE warnings (safe to remove)');
        for (const key of flagKeys) {
            lines.push(` ${key}: "${key}"`);
        }

        return lines.join('\n') + '\n';
    },

    _emitSettingLoc(lines, modId, setting) {
        const qid = `${modId}__${setting.setting_id}`;

        if (setting.setting_type === 'list') {
            // Lists use the group name as their display name; no setting-level name/desc.
            lines.push(` ${qid}_item_column_name: "${this._esc(setting.item_column_name || 'Item')}"`);
            if (!setting.list_source) {
                for (let i = 0; i < (setting.item_names || []).length; i++) {
                    lines.push(` ${qid}_i${i + 1}_name: "${this._esc(setting.item_names[i])}"`);
                }
            }
            for (const field of (setting.fields || [])) {
                const fqid = `${qid}__${field.field_id}`;
                lines.push(` ${fqid}_name: "${this._esc(field.name || field.field_id)}"`);
                if (field.field_type === 'dropdown') {
                    for (const opt of (field.options || [])) {
                        lines.push(` ${fqid}_option_${opt.index}_name: "${this._esc(opt.name)}"`);
                        if (opt.desc) {
                            lines.push(` ${fqid}_option_${opt.index}_desc: "${this._esc(opt.desc)}"`);
                        }
                    }
                }
            }
            return;
        }

        lines.push(` ${qid}_name: "${this._esc(setting.name || setting.setting_id)}"`);
        lines.push(` ${qid}_desc: "${this._esc(setting.desc)}"`);

        if ((setting.setting_type === 'numeric' || setting.setting_type === 'slider') && setting.display_format) {
            const fmt = this._esc(setting.display_format).replace(/\$VALUE\$/g, `[CMMV('${qid}')]`);
            lines.push(` ${qid}_format: "${fmt}"`);
        }

        if (setting.setting_type === 'button') {
            lines.push(` ${qid}_text: "${this._esc(setting.button_text || 'Run')}"`);
        } else if (setting.setting_type === 'dropdown') {
            for (const opt of (setting.options || [])) {
                lines.push(` ${qid}_option_${opt.index}_name: "${this._esc(opt.name)}"`);
                if (opt.desc) {
                    lines.push(` ${qid}_option_${opt.index}_desc: "${this._esc(opt.desc)}"`);
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
