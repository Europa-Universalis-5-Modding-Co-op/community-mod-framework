const SettingEditorComponent = {
    props: ['setting', 'index', 'total', 'modId', 'collapseSignal'],
    emits: ['remove', 'move-up', 'move-down', 'toggle-all'],
    template: `
    <div class="setting-card" :class="{collapsed: collapsed}">
        <div class="setting-card-header" @click="toggleCollapse($event)" title="Click to collapse/expand. Shift+click to toggle all.">
            <span class="collapse-indicator">{{ collapsed ? '&#9654;' : '&#9660;' }}</span>
            <span class="setting-type-badge" :class="setting.setting_type">{{ setting.setting_type }}</span>
            <span class="setting-title">{{ setting.name || setting.setting_id || 'New Setting' }}</span>
            <span v-if="setting.is_global" class="global-badge">Global</span>
            <span v-if="accessor" class="accessor-group">
                <span class="accessor-label">{{ accessorLabel }}</span>
                <template v-if="!editingAlias">
                    <span class="setting-accessor" @click="copyAccessor" :title="'Click to copy: ' + accessor">
                        <code>{{ accessor }}</code>
                        <span v-if="copied" class="copied-flash">Copied!</span>
                    </span>
                    <button class="btn-icon btn-alias-edit" @click="startEditAlias" title="Edit accessor alias">&#9998;</button>
                </template>
                <template v-else>
                    <span class="alias-edit-group">
                        <span class="accessor-prefix">{{ accessorPrefix }}:</span>
                        <input class="alias-edit-input" v-model="aliasInput" @keyup.enter="confirmAlias" @keyup.escape="cancelAlias" ref="aliasInput" :placeholder="defaultAccessorKey">
                        <button class="btn-icon" @click="confirmAlias" title="Confirm">&#10003;</button>
                        <button class="btn-icon" @click="cancelAlias" title="Cancel">&#10005;</button>
                        <button v-if="setting.alias" class="btn-icon btn-danger" @click="clearAlias" title="Remove alias">&#8634;</button>
                    </span>
                </template>
            </span>
            <div class="setting-actions">
                <button v-if="setting.setting_type === 'list' && modId && setting.setting_id && (setting.fields||[]).length" class="btn btn-sm btn-copy-template" @click="copyLoopTemplate" title="Copy iteration template to clipboard">
                    {{ copiedTemplate ? 'Copied!' : 'Copy Loop Template' }}
                </button>
                <button class="btn-icon" @click="$emit('move-up')" :disabled="index === 0" title="Move up">&#9650;</button>
                <button class="btn-icon" @click="$emit('move-down')" :disabled="index === total - 1" title="Move down">&#9660;</button>
                <button class="btn-icon btn-danger" @click="$emit('remove')" title="Remove">&times;</button>
            </div>
        </div>

        <div class="setting-card-body" v-show="!collapsed">
            <div class="field-grid">
                <div class="field-row">
                    <label>Setting ID <span class="required">*</span></label>
                    <input v-model="setting.setting_id" placeholder="my_setting" @input="sanitizeId">
                </div>
                <div class="field-row">
                    <label>Type</label>
                    <select v-model="setting.setting_type" @change="onTypeChange">
                        <option value="bool">Bool (Toggle)</option>
                        <option value="button">Button</option>
                        <option value="numeric">Numeric (Stepper)</option>
                        <option value="slider">Slider</option>
                        <option value="dropdown">Dropdown</option>
                        <option value="text">Text Input</option>
                        <option value="list">Settings List</option>
                    </select>
                </div>
                <div class="field-row" v-if="setting.setting_type !== 'list'">
                    <label>Display Name</label>
                    <input v-model="setting.name" :placeholder="setting.setting_id || 'My Setting'">
                </div>
                <div class="field-row" v-if="setting.setting_type !== 'list'">
                    <label>Description</label>
                    <input v-model="setting.desc" placeholder="What this setting does.">
                </div>
            </div>

            <div class="checkbox-grid" v-if="settingFlags.length">
                <div class="field-row" v-for="flag in settingFlags" :key="flag.key">
                    <label class="checkbox-label">
                        <input type="checkbox" v-model="setting[flag.key]">
                        {{ flag.label }}
                        <span class="field-hint">{{ flag.hint }}</span>
                    </label>
                </div>
            </div>

            <div v-if="showSguiConditions" class="type-fields sgui-fields">
                <div class="field-row">
                    <label>Visible Condition <span class="field-hint">(is_shown)</span></label>
                    <textarea v-model="setting.visible" rows="2" placeholder='e.g. "variable_map(cmm|flag:my_mod__my_toggle)" >= 1' class="code-textarea"></textarea>
                    <span class="field-hint">Paradox trigger. Setting is hidden when this evaluates to false.</span>
                </div>
                <div class="field-row">
                    <label>Enabled Condition <span class="field-hint">(is_valid)</span></label>
                    <textarea v-model="setting.enabled" rows="2" placeholder='e.g. has_variable = my_flag' class="code-textarea"></textarea>
                    <span class="field-hint">Paradox trigger. Setting is greyed out when this evaluates to false.</span>
                </div>
            </div>

            <!-- Bool -->
            <div v-if="setting.setting_type === 'bool'" class="type-fields">
                <div class="field-row">
                    <label>Default Value</label>
                    <select v-model.number="setting.default_value">
                        <option :value="0">Off (0)</option>
                        <option :value="1">On (1)</option>
                    </select>
                </div>
            </div>

            <!-- Button -->
            <div v-if="setting.setting_type === 'button'" class="type-fields">
                <div class="field-row">
                    <label>Button Text</label>
                    <input v-model="setting.button_text" placeholder="Run">
                </div>
            </div>

            <!-- Numeric / Slider -->
            <div v-if="setting.setting_type === 'numeric' || setting.setting_type === 'slider'" class="type-fields">
                <div class="field-grid">
                    <div class="field-row">
                        <label>Default</label>
                        <input type="number" v-model.number="setting.default_value">
                    </div>
                    <div class="field-row">
                        <label>Min</label>
                        <input type="number" v-model.number="setting.min_value">
                    </div>
                    <div class="field-row">
                        <label>Max</label>
                        <input type="number" v-model.number="setting.max_value">
                    </div>
                    <div class="field-row">
                        <label>Step</label>
                        <input type="number" v-model.number="setting.step_value" min="1">
                    </div>
                </div>
                <div class="field-row">
                    <label>Display Format</label>
                    <input v-model="setting.display_format" placeholder="e.g. $VALUE$%">
                    <span class="field-hint">Use $VALUE$ as placeholder (e.g. "$VALUE$%", "$$VALUE$", "+ $VALUE$ gold")</span>
                </div>
            </div>

            <!-- Dropdown -->
            <div v-if="setting.setting_type === 'dropdown'" class="type-fields">
                <div class="field-grid">
                    <div class="field-row">
                        <label>Default Index</label>
                        <input type="number" v-model.number="setting.default_index" min="1" :max="setting.option_count||1">
                    </div>
                    <div class="field-row">
                        <label>Option Count</label>
                        <input type="number" v-model.number="setting.option_count" min="1" @input="syncOptions">
                    </div>
                </div>
                <dropdown-options :setting="setting" :mod-id="modId"></dropdown-options>
            </div>

            <!-- Text -->
            <div v-if="setting.setting_type === 'text'" class="type-fields">
                <div class="field-grid">
                    <div class="field-row">
                        <label>Character Limit</label>
                        <input type="number" v-model.number="setting.character_limit" min="1">
                    </div>
                    <div class="field-row">
                        <label>Quote Text</label>
                        <select v-model.number="setting.quote_text">
                            <option :value="0">No (raw text)</option>
                            <option :value="1">Yes (wrap in quotes)</option>
                        </select>
                    </div>
                </div>
                <p class="field-hint">Text settings are singleplayer-only.</p>
            </div>

            <!-- List -->
            <div v-if="setting.setting_type === 'list'" class="type-fields">
                <list-editor :setting="setting" :mod-id="modId"></list-editor>
            </div>

            <!-- Callback -->
            <div class="type-fields callback-fields">
                <div class="field-grid">
                    <div class="field-row">
                        <label>Custom On Changed Effect</label>
                        <input v-model="setting.on_changed_effect" placeholder="my_custom_effect">
                        <span class="field-hint">Optional effect to call when this setting changes</span>
                    </div>
                    <div class="field-row" v-if="setting.on_changed_effect && !['button', 'list'].includes(setting.setting_type)">
                        <label>Parameter Name</label>
                        <div class="input-with-inline-check">
                            <input v-model="setting.pass_value_param" placeholder="value" :disabled="setting.no_pass_value">
                            <label class="inline-checkbox">
                                <input type="checkbox" v-model="setting.no_pass_value">
                                No argument
                            </label>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    `,
    data() {
        return { copied: false, copiedTemplate: false, editingAlias: false, aliasInput: '', collapsed: false };
    },
    watch: {
        collapseSignal(val) {
            if (val) this.collapsed = val.collapsed;
        },
    },
    computed: {
        canBeGlobal() {
            return this.setting.setting_type !== 'text';
        },
        showSguiConditions() {
            return this.setting.scripted_gui || this.setting.setting_type === 'list';
        },
        defaultAccessorKey() {
            if (!this.modId || !this.setting.setting_id) return '';
            return `${this.modId}__${this.setting.setting_id}`;
        },
        hasAlias() {
            return !!this.setting.alias;
        },
        accessor() {
            if (!this.modId || !this.setting.setting_id) return '';
            if (['button', 'list'].includes(this.setting.setting_type)) return '';
            if (this.hasAlias) {
                if (this.setting.setting_type === 'bool') {
                    const func = this.setting.is_global ? 'has_global_variable' : 'has_variable';
                    return `${func} = ${this.setting.alias}`;
                }
                const prefix = this.setting.is_global ? 'global_var' : 'var';
                return `${prefix}:${this.setting.alias}`;
            }
            const mapFunc = this.setting.is_global ? 'global_variable_map' : 'variable_map';
            return `"${mapFunc}(cmm|flag:${this.defaultAccessorKey})"`;
        },
        settingFlags() {
            const flags = [];
            if (this.canBeGlobal) {
                flags.push({ key: 'is_global', label: 'Global Setting', hint: '(Host-only in multiplayer, shared across all players)' });
            }
            if (this.setting.setting_type !== 'button') {
                flags.push({ key: 'no_reset', label: 'No Reset', hint: '(Excluded from the Reset to Defaults button)' });
            }
            if (this.setting.setting_type === 'bool' && this.hasAlias) {
                flags.push({ key: 'alias_inverted', label: 'Inverted Alias', hint: '(Variable absent when enabled, present when disabled)' });
            }
            if (this.setting.setting_type !== 'list') {
                flags.push({ key: 'scripted_gui', label: 'Scripted GUI', hint: '(Enable is_shown / is_valid conditions)' });
            }
            return flags;
        },
        accessorLabel() {
            if (this.hasAlias) return this.setting.alias_inverted ? "Alias (synced, inverted):" : "Alias (synced):";
            if (!this.setting.is_global) return "To Access the Setting's Value (Country Scope):";
            return "To Access the Setting's Value:";
        },
    },
    methods: {
        toggleCollapse(e) {
            if (e.target.closest('button, input, .accessor-group')) return;
            if (e.shiftKey) {
                this.$emit('toggle-all', !this.collapsed);
                return;
            }
            this.collapsed = !this.collapsed;
        },
        copyLoopTemplate() {
            const qid = `${this.modId}__${this.setting.setting_id}`;
            const fields = this.setting.fields || [];
            const itemCount = this.setting.list_source ? 'N' : (this.setting.item_count || 1);
            const hasValues = (this.setting.item_values || []).some(v => v) || !!this.setting.list_source;
            const lines = [];
            lines.push(`cmm_for_each_list_item = {`);
            lines.push(`\tsetting = ${qid}`);
            lines.push(`\teffect = ${qid.replace('__', '_')}_each_item`);
            lines.push(`}`);
            lines.push(``);
            lines.push(`${qid.replace('__', '_')}_each_item = {`);
            lines.push(`\t# $i$ is the resolved item number (1-${itemCount})`);
            if (hasValues) {
                lines.push(`\t# scope:cmm_list_current_item_value  (attached game object)`);
            }
            for (let fi = 0; fi < fields.length; fi++) {
                const slot = fi + 1;
                const ftype = fields[fi].field_type;
                const fid = fields[fi].field_id || `field_${slot}`;
                const itemAliases = fields[fi].item_aliases;
                const hasPerItem = itemAliases && itemAliases.some(a => a);
                if (fields[fi].alias) {
                    const prefix = this.setting.is_global ? 'global_var' : 'var';
                    lines.push(`\t# ${prefix}:${fields[fi].alias}  (${fid}, ${ftype})`);
                } else {
                    lines.push(`\t# "variable_map(cmm|flag:$setting$_i$i$_f${slot})"  (${fid}, ${ftype})`);
                }
                if (hasPerItem) {
                    const prefix = this.setting.is_global ? 'global_var' : 'var';
                    lines.push(`\t# Per-item aliases for ${fid}:`);
                    for (let ii = 0; ii < itemAliases.length; ii++) {
                        if (itemAliases[ii]) {
                            const name = (this.setting.item_names || [])[ii] || `Item ${ii + 1}`;
                            lines.push(`\t#   ${name}: ${prefix}:${itemAliases[ii]}`);
                        }
                    }
                }
            }
            lines.push(`}`);
            navigator.clipboard.writeText(lines.join('\n'));
            this.copiedTemplate = true;
            setTimeout(() => { this.copiedTemplate = false; }, 1200);
        },
        copyAccessor() {
            if (!this.accessor) return;
            navigator.clipboard.writeText(this.accessor);
            this.copied = true;
            setTimeout(() => { this.copied = false; }, 1200);
        },
        sanitizeId() {
            this.setting.setting_id = this.setting.setting_id.replace(/[^a-zA-Z0-9_]/g, '');
        },
        onTypeChange() {
            if (['text', 'list'].includes(this.setting.setting_type)) {
                this.setting.is_global = false;
            }
        },
        startEditAlias() {
            this.aliasInput = this.setting.alias || this.defaultAccessorKey;
            this.editingAlias = true;
            this.$nextTick(() => { if (this.$refs.aliasInput) this.$refs.aliasInput.focus(); });
        },
        confirmAlias() {
            const val = this.aliasInput.replace(/[^a-zA-Z0-9_$]/g, '');
            this.setting.alias = val || '';
            this.editingAlias = false;
        },
        cancelAlias() {
            this.editingAlias = false;
        },
        clearAlias() {
            this.setting.alias = '';
            this.editingAlias = false;
        },
        syncOptions() {
            const count = Math.max(1, this.setting.option_count || 1);
            this.setting.option_count = count;
            if (!this.setting.options) this.setting.options = [];
            while (this.setting.options.length < count) {
                const i = this.setting.options.length + 1;
                this.setting.options.push({ index: i, name: `Option ${i}`, desc: '', alias: '' });
            }
            while (this.setting.options.length > count) {
                this.setting.options.pop();
            }
            for (let i = 0; i < this.setting.options.length; i++) {
                this.setting.options[i].index = i + 1;
            }
        },
    },
};
