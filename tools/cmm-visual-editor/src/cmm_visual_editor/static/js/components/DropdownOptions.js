const DropdownOptionsComponent = {
    props: ['setting'],
    template: `
    <div class="dropdown-options">
        <h5>Options</h5>
        <div v-for="(opt, i) in (setting.options || [])" :key="i" class="field-row compact">
            <label class="compact-label">{{ i + 1 }}</label>
            <input v-model="opt.name" :placeholder="'Option ' + (i + 1)">
            <input class="option-alias-input" v-model="opt.alias" @input="sanitizeAlias(opt)" placeholder="alias (has_variable)">
        </div>
    </div>
    `,
    methods: {
        sanitizeAlias(opt) {
            opt.alias = (opt.alias || '').replace(/[^a-z0-9_]/gi, '').toLowerCase();
        },
    },
};
