const ListEditorComponent = {
    props: ['setting', 'modId'],
    template: `
    <div class="list-editor">
        <div class="field-grid">
            <div class="field-row">
                <label>Item Count (1-20)</label>
                <input type="number" v-model.number="setting.item_count" min="1" max="20" @input="syncItemNames">
            </div>
            <div class="field-row">
                <label>Ordered</label>
                <select v-model.number="setting.is_ordered">
                    <option :value="1">Yes (row move controls)</option>
                    <option :value="0">No (static order)</option>
                </select>
            </div>
        </div>
        <div class="field-row">
            <label>Item Column Name</label>
            <input v-model="setting.item_column_name" placeholder="Item">
        </div>

        <div class="subsection">
            <h5>Item Names</h5>
            <div v-for="(name, i) in setting.item_names" :key="i" class="field-row compact">
                <label class="compact-label">{{ i + 1 }}</label>
                <input :value="name" @input="setting.item_names[i] = $event.target.value" :placeholder="'Item ' + (i+1)">
            </div>
        </div>

        <div class="subsection">
            <div class="section-header">
                <h5>Fields (max 5)</h5>
                <button class="btn btn-sm" @click="addField" :disabled="(setting.fields||[]).length >= 5">+ Add Field</button>
            </div>
            <div v-for="(field, fi) in (setting.fields||[])" :key="fi" class="field-card">
                <div class="field-card-header">
                    <span class="setting-type-badge" :class="field.field_type">{{ field.field_type }}</span>
                    <span>{{ field.name || field.field_id || 'Field ' + (fi+1) }}</span>
                    <span v-if="fieldAccessor(fi)" class="accessor-group">
                        <span class="accessor-label">Field Slot {{ fi + 1 }} Value (per item):</span>
                        <span class="setting-accessor" @click="copyFieldAccessor(fi)" :title="'Click to copy: ' + fieldAccessor(fi)">
                            <code>{{ fieldAccessor(fi) }}</code>
                            <span v-if="copiedField === fi" class="copied-flash">Copied!</span>
                        </span>
                    </span>
                    <button class="btn-icon btn-danger" @click="removeField(fi)">&times;</button>
                </div>
                <div class="field-grid">
                    <div class="field-row">
                        <label>Field ID</label>
                        <input v-model="field.field_id" placeholder="enabled" @input="sanitizeFieldId(field)">
                    </div>
                    <div class="field-row">
                        <label>Type</label>
                        <select v-model="field.field_type" @change="onFieldTypeChange(field)">
                            <option value="bool">Bool</option>
                            <option value="dropdown">Dropdown</option>
                            <option value="numeric">Numeric</option>
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
                    </div>
                </div>

                <!-- Numeric field -->
                <div v-if="field.field_type === 'numeric'" class="field-grid">
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
                </div>
            </div>
        </div>
    </div>
    `,
    data() {
        return { copiedField: -1 };
    },
    methods: {
        fieldAccessor(fi) {
            if (!this.modId || !this.setting.setting_id) return '';
            const slot = fi + 1;
            return `var:${this.modId}__${this.setting.setting_id}_item_$i$_field_${slot}`;
        },
        copyFieldAccessor(fi) {
            const text = this.fieldAccessor(fi);
            if (!text) return;
            navigator.clipboard.writeText(text);
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
            field.field_id = field.field_id.replace(/[^a-z0-9_]/gi, '').toLowerCase();
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
                field.options.push({ index: i, name: `Option ${i}` });
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
