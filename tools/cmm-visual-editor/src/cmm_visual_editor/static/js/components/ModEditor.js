const ModEditorComponent = {
    props: ['state'],
    emits: ['update'],
    template: `
    <div class="section">
        <div class="section-header"><h3>Mod Configuration</h3></div>
        <div class="field-row">
            <label>Mod ID <span class="required">*</span></label>
            <input v-model="state.mod_id" placeholder="my_mod" @input="onModIdChange">
            <span class="field-hint">Lowercase, underscores only. Used in all generated identifiers.</span>
        </div>
        <div class="field-row">
            <label>File Prefix</label>
            <input v-model="state.file_prefix" :placeholder="state.mod_id || 'my_mod'">
            <span class="field-hint">Defaults to Mod ID. Used for generated filenames.</span>
        </div>
        <div class="field-row">
            <label>Mod Name <span class="required">*</span></label>
            <input v-model="state.mod_name" placeholder="My Mod">
        </div>
        <div class="field-row">
            <label>Mod Description</label>
            <input v-model="state.mod_desc" placeholder="A brief description of your mod.">
        </div>

        <details class="metadata-section">
            <summary>Metadata (metadata.json)</summary>
            <div class="field-row">
                <label>Display Name</label>
                <input v-model="state.metadata_name" :placeholder="state.mod_name || 'My Mod'">
            </div>
            <div class="field-row">
                <label>Mod ID (dotted)</label>
                <input v-model="state.metadata_id" placeholder="your.mod.id">
            </div>
            <div class="field-row">
                <label>Version</label>
                <input v-model="state.metadata_version" placeholder="0.1">
            </div>
            <div class="field-row">
                <label>Short Description</label>
                <input v-model="state.metadata_short_description" :placeholder="state.mod_desc">
            </div>
            <div class="field-row">
                <label>Game Version</label>
                <input v-model="state.metadata_game_version" placeholder="1.1.*">
            </div>
            <div class="field-row">
                <label>Tags (comma-separated)</label>
                <input :value="state.metadata_tags.join(', ')" @input="onTagsChange">
            </div>
        </details>
    </div>
    `,
    methods: {
        onModIdChange() {
            this.state.mod_id = this.state.mod_id.replace(/[^a-z0-9_]/gi, '').toLowerCase();
        },
        onTagsChange(e) {
            this.state.metadata_tags = e.target.value.split(',').map(t => t.trim()).filter(Boolean);
        },
    },
};
