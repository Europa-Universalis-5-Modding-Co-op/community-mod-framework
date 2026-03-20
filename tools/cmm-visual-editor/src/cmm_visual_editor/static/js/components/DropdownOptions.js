const DropdownOptionsComponent = {
    props: ['setting', 'modId'],
    template: `
    <div class="dropdown-options">
        <h5>Options</h5>
        <div v-for="(opt, i) in (setting.options || [])" :key="i" class="dropdown-option-row">
            <div class="field-row compact">
                <label class="compact-label">{{ i + 1 }}</label>
                <input v-model="opt.name" :placeholder="'Option ' + (i + 1)">
                <input v-model="opt.desc" placeholder="description (optional)">
            </div>
            <div v-if="modId && setting.setting_id" class="option-alias-area">
                <template v-if="editingOption !== i">
                    <span class="setting-accessor" @click="copyAccessor(i)" :title="'Click to copy: ' + optionAccessor(i)">
                        <code>{{ optionAccessor(i) }}</code>
                        <span v-if="copiedOption === i" class="copied-flash">Copied!</span>
                    </span>
                    <button class="btn-icon btn-alias-edit" @click="startEdit(i)" :title="opt.alias ? 'Edit option alias' : 'Add option alias'">&#9998;</button>
                </template>
                <template v-else>
                    <span class="alias-edit-group">
                        <span class="accessor-prefix">{{ aliasFunc }}:</span>
                        <input class="alias-edit-input" v-model="aliasInput" @keyup.enter="confirmEdit(i)" @keyup.escape="cancelEdit" ref="aliasInput" placeholder="has_variable">
                        <button class="btn-icon" @click="confirmEdit(i)" title="Confirm">&#10003;</button>
                        <button class="btn-icon" @click="cancelEdit" title="Cancel">&#10005;</button>
                        <button v-if="opt.alias" class="btn-icon btn-danger" @click="clearAlias(i)" title="Remove alias">&#8634;</button>
                    </span>
                </template>
            </div>
        </div>
    </div>
    `,
    data() {
        return { editingOption: -1, aliasInput: '', copiedOption: -1 };
    },
    computed: {
        qid() {
            return `${this.modId}__${this.setting.setting_id}`;
        },
        mapFunc() {
            return this.setting.is_global ? 'global_variable_map' : 'variable_map';
        },
        aliasFunc() {
            return this.setting.is_global ? 'has_global_variable' : 'has_variable';
        },
    },
    methods: {
        optionAccessor(i) {
            const opt = (this.setting.options || [])[i];
            const index = i + 1;
            if (opt && opt.alias) {
                return `${this.aliasFunc} = ${opt.alias}`;
            }
            return `"${this.mapFunc}(cmm|flag:${this.qid})" = ${index}`;
        },
        copyAccessor(i) {
            const text = this.optionAccessor(i);
            if (!text) return;
            navigator.clipboard.writeText(text);
            this.copiedOption = i;
            setTimeout(() => { this.copiedOption = -1; }, 1200);
        },
        startEdit(i) {
            const opt = (this.setting.options || [])[i];
            this.aliasInput = (opt && opt.alias) || '';
            this.editingOption = i;
            this.$nextTick(() => {
                const refs = this.$refs.aliasInput;
                if (refs) {
                    const el = Array.isArray(refs) ? refs[0] : refs;
                    if (el) el.focus();
                }
            });
        },
        confirmEdit(i) {
            const opt = (this.setting.options || [])[i];
            if (!opt) return;
            const val = this.aliasInput.replace(/[^a-z0-9_]/gi, '').toLowerCase();
            opt.alias = val || '';
            this.editingOption = -1;
        },
        cancelEdit() {
            this.editingOption = -1;
        },
        clearAlias(i) {
            const opt = (this.setting.options || [])[i];
            if (opt) opt.alias = '';
            this.editingOption = -1;
        },
    },
};
