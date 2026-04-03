const ListEditorComponent = {
    props: ['setting', 'modId'],
    template: `
    <div class="list-editor">
        <div class="field-grid">
            <div class="field-row">
                <label>List Source</label>
                <select v-model="listMode" @change="onListModeChange">
                    <option value="static">Static (fixed item count)</option>
                    <option value="from_list">From Variable List</option>
                </select>
            </div>
            <div class="field-row">
                <label>Ordered</label>
                <select v-model.number="setting.is_ordered">
                    <option :value="1">Yes (row move controls)</option>
                    <option :value="0">No (static order)</option>
                </select>
            </div>
            <div class="field-row">
                <label>Item Column Name</label>
                <input v-model="setting.item_column_name" placeholder="Item">
            </div>
            <div v-if="listMode === 'static'" class="field-row">
                <label>Item Count (1-20)</label>
                <input type="number" v-model.number="setting.item_count" min="1" max="20" @input="syncItemNames">
            </div>
            <div v-if="listMode === 'from_list'" class="field-row">
                <label>Variable List Name</label>
                <input v-model="setting.list_source" placeholder="my_buildings_list">
            </div>
        </div>

        <div v-if="listMode === 'static'" class="subsection">
            <h5>Items</h5>
            <div v-for="(name, i) in setting.item_names" :key="i" class="field-row compact list-item-row">
                <label class="compact-label">{{ i + 1 }}</label>
                <input :value="name" @input="setting.item_names[i] = $event.target.value" :placeholder="'Item ' + (i+1)" class="item-name-input">
                <input :value="(setting.item_values||[])[i] || ''" @input="setItemValue(i, $event.target.value)" placeholder="value (e.g. building_type:fine_cloth_guild)" class="item-value-input">
            </div>
        </div>

        <div class="subsection">
            <div class="section-header">
                <h5>Fields (max 5)</h5>
                <button class="btn btn-sm" @click="addField" :disabled="(setting.fields||[]).length >= 5">+ Add Field</button>
            </div>
            <div v-for="(field, fi) in (setting.fields||[])" :key="fi" class="field-card">
                <div class="field-card-header" @click="toggleFieldCollapsed(fi)" style="cursor: pointer;">
                    <span class="collapse-indicator">{{ isFieldCollapsed(fi) ? '&#9654;' : '&#9660;' }}</span>
                    <span class="setting-type-badge" :class="field.field_type">{{ field.field_type }}</span>
                    <span class="field-card-title">{{ field.name || field.field_id || 'Field ' + (fi+1) }}</span>
                    <span v-if="fieldAccessor(fi)" class="accessor-group">
                        <span class="accessor-label">{{ fieldAccessorLabel(fi) }}</span>
                        <template v-if="editingFieldAlias !== fi">
                            <span v-if="hasItemAliases(fi)" class="setting-accessor" @click.stop="copyFieldAccessor(fi)" title="Click to copy all per-item aliases">
                                <code>per-item</code>
                                <span v-if="copiedField === fi" class="copied-flash">Copied!</span>
                            </span>
                            <span v-else class="setting-accessor" @click.stop="copyFieldAccessor(fi)" :title="'Click to copy: ' + fieldAccessor(fi)">
                                <code>{{ fieldAccessor(fi) }}</code>
                                <span v-if="copiedField === fi" class="copied-flash">Copied!</span>
                            </span>
                            <button v-if="!hasItemAliases(fi)" class="btn-icon btn-alias-edit" @click.stop="startEditFieldAlias(fi)" title="Edit accessor alias">&#9998;</button>
                        </template>
                        <template v-else>
                            <span class="alias-edit-group" @click.stop>
                                <span class="accessor-prefix">var:</span>
                                <input class="alias-edit-input" v-model="fieldAliasInput" @keyup.enter="confirmFieldAlias(fi)" @keyup.escape="cancelFieldAlias" ref="fieldAliasInput" :placeholder="defaultFieldAccessorKey(fi)">
                                <button class="btn-icon" @click="confirmFieldAlias(fi)" title="Confirm">&#10003;</button>
                                <button class="btn-icon" @click="cancelFieldAlias" title="Cancel">&#10005;</button>
                                <button v-if="field.alias" class="btn-icon btn-danger" @click="clearFieldAlias(fi)" title="Remove alias">&#8634;</button>
                            </span>
                        </template>
                    </span>
                    <button class="btn-icon btn-danger" @click.stop="removeField(fi)">&times;</button>
                </div>
                <div v-show="!isFieldCollapsed(fi)">
                    <div class="field-grid">
                        <div class="field-row">
                            <label>Field ID <span class="required">*</span></label>
                            <input v-model="field.field_id" placeholder="enabled" @input="sanitizeFieldId(field)">
                        </div>
                        <div class="field-row">
                            <label>Type</label>
                            <select v-model="field.field_type" @change="onFieldTypeChange(field)">
                                <option value="bool">Bool</option>
                                <option value="dropdown">Dropdown</option>
                                <option value="numeric">Numeric</option>
                                <option value="slider">Slider</option>
                            </select>
                        </div>
                        <div class="field-row">
                            <label>Name</label>
                            <input v-model="field.name" placeholder="Field Name">
                        </div>
                    </div>

                    <!-- Bool field -->
                    <div v-if="field.field_type === 'bool'" class="field-row">
                        <label>Default</label>
                        <select v-model.number="field.default_value">
                            <option :value="0">Off (0)</option>
                            <option :value="1">On (1)</option>
                        </select>
                    </div>

                    <!-- Dropdown field -->
                    <div v-if="field.field_type === 'dropdown'">
                        <div class="field-grid">
                            <div class="field-row">
                                <label>Default Index</label>
                                <input type="number" v-model.number="field.default_index" min="1">
                            </div>
                            <div class="field-row">
                                <label>Option Count</label>
                                <input type="number" v-model.number="field.option_count" min="1" @input="syncFieldOptions(field)">
                            </div>
                        </div>
                        <div v-for="(opt, oi) in (field.options||[])" :key="oi" class="field-row compact">
                            <label class="compact-label">{{ oi + 1 }}</label>
                            <input v-model="opt.name" :placeholder="'Option ' + (oi+1)">
                            <input v-model="opt.desc" placeholder="description (optional)">
                        </div>
                    </div>

                    <!-- Numeric / Slider field -->
                    <div v-if="field.field_type === 'numeric' || field.field_type === 'slider'" class="field-grid">
                        <div class="field-row">
                            <label>Default</label>
                            <input type="number" v-model.number="field.default_value">
                        </div>
                        <div class="field-row">
                            <label>Min</label>
                            <input type="number" v-model.number="field.min_value">
                        </div>
                        <div class="field-row">
                            <label>Max</label>
                            <input type="number" v-model.number="field.max_value">
                        </div>
                        <div class="field-row">
                            <label>Step</label>
                            <input type="number" v-model.number="field.step_value" min="1">
                        </div>
                        <div class="field-row">
                            <label>Format</label>
                            <input type="text" v-model="field.display_format" placeholder='e.g. $VALUE$%'>
                        </div>
                    </div>

                    <!-- Per-item field visibility (static lists only) -->
                    <div v-if="listMode === 'static' && field.field_id && (setting.item_count || 1) > 1" class="per-item-aliases">
                        <h6 class="collapsible-header" @click="togglePerItemSection(fi, 'visibility')">
                            <span class="collapse-indicator">{{ isPerItemSectionOpen(fi, 'visibility') ? '&#9660;' : '&#9654;' }}</span>
                            Per-Item Visibility
                        </h6>
                        <div v-show="isPerItemSectionOpen(fi, 'visibility')">
                            <div v-for="(name, ii) in (setting.item_names || [])" :key="'vis-'+ii" class="field-row compact list-item-row">
                                <label class="compact-label">{{ ii + 1 }}</label>
                                <span class="item-alias-name">{{ name || 'Item ' + (ii+1) }}</span>
                                <label class="item-visibility-toggle">
                                    <input type="checkbox" :checked="isItemFieldEnabled(fi, ii)" @change="toggleItemFieldEnabled(fi, ii)">
                                    <span class="item-visibility-label">{{ isItemFieldEnabled(fi, ii) ? 'Shown' : 'Hidden' }}</span>
                                </label>
                            </div>
                        </div>
                    </div>

                    <!-- Per-item aliases (static lists only) -->
                    <div v-if="listMode === 'static' && field.field_id" class="per-item-aliases">
                        <h6 class="collapsible-header" @click="togglePerItemSection(fi, 'aliases')">
                            <span class="collapse-indicator">{{ isPerItemSectionOpen(fi, 'aliases') ? '&#9660;' : '&#9654;' }}</span>
                            Per-Item Aliases
                        </h6>
                        <div v-show="isPerItemSectionOpen(fi, 'aliases')">
                            <div v-for="(name, ii) in (setting.item_names || [])" :key="ii" class="field-row compact list-item-row">
                                <label class="compact-label">{{ ii + 1 }}</label>
                                <span class="item-alias-name">{{ name || 'Item ' + (ii+1) }}</span>
                                <input :value="getItemAlias(fi, ii)" @input="setItemAlias(fi, ii, $event.target.value)" placeholder="alias (optional)" class="item-alias-input">
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    `,
    data() {
        return {
            copiedField: -1,
            listMode: this.setting.list_source ? 'from_list' : 'static',
            editingFieldAlias: -1,
            fieldAliasInput: '',
            collapsedFields: {},       // fi -> true if collapsed
            perItemSections: {},       // "fi:type" -> true if open
        };
    },
    methods: {
        isFieldCollapsed(fi) {
            return !!this.collapsedFields[fi];
        },
        toggleFieldCollapsed(fi) {
            this.collapsedFields = { ...this.collapsedFields, [fi]: !this.collapsedFields[fi] };
        },
        isPerItemSectionOpen(fi, type) {
            return !!this.perItemSections[`${fi}:${type}`];
        },
        togglePerItemSection(fi, type) {
            const key = `${fi}:${type}`;
            this.perItemSections = { ...this.perItemSections, [key]: !this.perItemSections[key] };
        },
        defaultFieldAccessorKey(fi) {
            if (!this.modId || !this.setting.setting_id) return '';
            const slot = fi + 1;
            return `${this.modId}__${this.setting.setting_id}_i$i$_f${slot}`;
        },
        hasItemAliases(fi) {
            const field = (this.setting.fields || [])[fi];
            return field && field.item_aliases && field.item_aliases.some(a => a);
        },
        fieldAccessor(fi) {
            if (!this.modId || !this.setting.setting_id) return '';
            const field = (this.setting.fields || [])[fi];
            if (this.hasItemAliases(fi)) {
                return 'per-item';
            }
            const defaultKey = this.defaultFieldAccessorKey(fi);
            if (field && field.alias) {
                const prefix = this.setting.is_global ? 'global_var' : 'var';
                return `${prefix}:${field.alias}`;
            }
            const mapFunc = this.setting.is_global ? 'global_variable_map' : 'variable_map';
            return `"${mapFunc}(cmm|flag:${defaultKey})"`;
        },
        fieldAccessorLabel(fi) {
            const field = (this.setting.fields || [])[fi];
            if (this.hasItemAliases(fi)) {
                const count = field.item_aliases.filter(a => a).length;
                return `Per-item aliases (${count} set):`;
            }
            if (field && field.alias) {
                return `Alias (synced, per item):`;
            }
            return `Field Slot ${fi + 1} Value (per item):`;
        },
        startEditFieldAlias(fi) {
            const field = (this.setting.fields || [])[fi];
            this.fieldAliasInput = (field && field.alias) || this.defaultFieldAccessorKey(fi);
            this.editingFieldAlias = fi;
            this.$nextTick(() => {
                const refs = this.$refs.fieldAliasInput;
                if (refs) {
                    const el = Array.isArray(refs) ? refs[0] : refs;
                    if (el) el.focus();
                }
            });
        },
        confirmFieldAlias(fi) {
            const field = (this.setting.fields || [])[fi];
            if (!field) return;
            const val = this.fieldAliasInput.replace(/[^a-zA-Z0-9_$]/g, '');
            field.alias = val || '';
            // Clear per-item aliases when setting a template alias
            if (val) field.item_aliases = null;
            this.editingFieldAlias = -1;
        },
        cancelFieldAlias() {
            this.editingFieldAlias = -1;
        },
        clearFieldAlias(fi) {
            const field = (this.setting.fields || [])[fi];
            if (field) field.alias = '';
            this.editingFieldAlias = -1;
        },
        copyFieldAccessor(fi) {
            const field = (this.setting.fields || [])[fi];
            if (this.hasItemAliases(fi)) {
                // Copy all per-item aliases as a list
                const prefix = this.setting.is_global ? 'global_var' : 'var';
                const lines = field.item_aliases
                    .map((a, i) => a ? `${prefix}:${a}` : `# item ${i + 1}: no alias`)
                    .join('\n');
                navigator.clipboard.writeText(lines);
            } else {
                const text = this.fieldAccessor(fi);
                if (!text) return;
                navigator.clipboard.writeText(text);
            }
            this.copiedField = fi;
            setTimeout(() => { this.copiedField = -1; }, 1200);
        },
        syncItemNames() {
            const count = Math.max(1, Math.min(20, this.setting.item_count || 1));
            this.setting.item_count = count;
            if (!this.setting.item_names) this.setting.item_names = [];
            while (this.setting.item_names.length < count) {
                this.setting.item_names.push(`Item ${String.fromCharCode(65 + this.setting.item_names.length)}`);
            }
            while (this.setting.item_names.length > count) {
                this.setting.item_names.pop();
            }
            // Sync item_values array length
            if (!this.setting.item_values) this.setting.item_values = [];
            while (this.setting.item_values.length < count) {
                this.setting.item_values.push('');
            }
            while (this.setting.item_values.length > count) {
                this.setting.item_values.pop();
            }
            // Sync per-item disabled_items arrays on all fields (remove out-of-range items)
            for (const field of (this.setting.fields || [])) {
                if (field.disabled_items) {
                    field.disabled_items = field.disabled_items.filter(i => i >= 1 && i <= count);
                    if (field.disabled_items.length === 0) field.disabled_items = null;
                }
            }
            // Sync per-item alias arrays on all fields
            for (const field of (this.setting.fields || [])) {
                if (field.item_aliases) {
                    while (field.item_aliases.length < count) {
                        field.item_aliases.push('');
                    }
                    while (field.item_aliases.length > count) {
                        field.item_aliases.pop();
                    }
                }
            }
        },
        isItemFieldEnabled(fi, itemIndex) {
            const field = (this.setting.fields || [])[fi];
            if (!field || !field.disabled_items) return true;
            return !field.disabled_items.includes(itemIndex + 1);
        },
        toggleItemFieldEnabled(fi, itemIndex) {
            const field = (this.setting.fields || [])[fi];
            if (!field) return;
            const item = itemIndex + 1;  // 1-based
            if (!field.disabled_items) {
                field.disabled_items = [];
            }
            const idx = field.disabled_items.indexOf(item);
            if (idx >= 0) {
                field.disabled_items.splice(idx, 1);
            } else {
                field.disabled_items.push(item);
                field.disabled_items.sort((a, b) => a - b);
            }
            // Trigger reactivity
            field.disabled_items = [...field.disabled_items];
            // Clean up empty array
            if (field.disabled_items.length === 0) {
                field.disabled_items = null;
            }
        },
        getItemAlias(fi, itemIndex) {
            const field = (this.setting.fields || [])[fi];
            if (!field || !field.item_aliases) return '';
            return field.item_aliases[itemIndex] || '';
        },
        setItemAlias(fi, itemIndex, value) {
            const field = (this.setting.fields || [])[fi];
            if (!field) return;
            if (!field.item_aliases) {
                field.item_aliases = [];
            }
            const count = this.setting.item_count || 1;
            while (field.item_aliases.length < count) {
                field.item_aliases.push('');
            }
            const sanitized = value.replace(/[^a-zA-Z0-9_]/g, '');
            field.item_aliases[itemIndex] = sanitized;
            // Trigger reactivity by replacing the array
            field.item_aliases = [...field.item_aliases];
            // Clear template alias when setting per-item aliases
            if (sanitized) field.alias = '';
        },
        setItemValue(index, value) {
            if (!this.setting.item_values) this.setting.item_values = [];
            while (this.setting.item_values.length <= index) {
                this.setting.item_values.push('');
            }
            this.setting.item_values[index] = value;
        },
        onListModeChange() {
            if (this.listMode === 'from_list') {
                this.setting.list_source = this.setting.list_source || '';
            } else {
                this.setting.list_source = '';
            }
        },
        addField() {
            if (!this.setting.fields) this.setting.fields = [];
            if (this.setting.fields.length >= 5) return;
            this.setting.fields.push({
                field_id: '',
                field_type: 'bool',
                name: '',
                default_value: 0,
                default_index: 1,
                option_count: 3,
                options: [
                    { index: 1, name: 'Option 1' },
                    { index: 2, name: 'Option 2' },
                    { index: 3, name: 'Option 3' },
                ],
                min_value: 0,
                max_value: 10,
                step_value: 1,
            });
        },
        removeField(i) {
            this.setting.fields.splice(i, 1);
        },
        sanitizeFieldId(field) {
            field.field_id = field.field_id.replace(/[^a-zA-Z0-9_]/g, '');
        },
        onFieldTypeChange(field) {
            // Reset defaults based on type
        },
        syncFieldOptions(field) {
            const count = Math.max(1, field.option_count || 1);
            field.option_count = count;
            if (!field.options) field.options = [];
            while (field.options.length < count) {
                const i = field.options.length + 1;
                field.options.push({ index: i, name: `Option ${i}`, desc: '', alias: '' });
            }
            while (field.options.length > count) {
                field.options.pop();
            }
            for (let i = 0; i < field.options.length; i++) {
                field.options[i].index = i + 1;
            }
        },
    },
};
