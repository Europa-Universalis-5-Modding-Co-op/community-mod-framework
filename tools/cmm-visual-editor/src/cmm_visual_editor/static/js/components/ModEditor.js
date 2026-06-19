const ModEditorComponent = {
    props: ['state'],
    emits: ['update'],
    data() {
        return {
            iconFileName: '',
            backgroundFileName: '',
        };
    },
    template: `
    <div class="section">
        <div class="section-header"><h3>Mod Configuration</h3></div>
        <div class="field-row">
            <label>Mod ID <span class="required">*</span></label>
            <input v-model="state.mod_id" placeholder="my_mod" @input="onModIdChange">
            <span class="field-hint">Letters, numbers, underscores only. Used in all generated identifiers.</span>
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
        <div class="field-row">
            <label>Mod Icon</label>
            <input type="file" @change="onModIconChange" ref="modIconInput">
            <span class="field-hint" v-if="state.mod_icon">{{ getIconFileName() }}</span>
        </div>
        <div class="field-row">
            <label>Mod Background</label>
            <input type="file" @change="onModBackgroundChange" ref="modBackgroundInput">
            <span class="field-hint" v-if="state.mod_background">{{ getBackgroundFileName() }}</span>
        </div>
        <div class="field-row">
            <label>Lobby Banner</label>
            <input type="checkbox" v-model="state.lobby_banner">
            <span class="field-hint">Show this mod's icon as a banner in the pre-game lobby.</span>
        </div>
        <div class="field-row">
            <label>Post-Registration Effect</label>
            <input type="checkbox" v-model="state.post_registration">
            <span class="field-hint">Calls {{ (state.file_prefix || state.mod_id || 'my_mod') }}_cmm_post_registration right after registration, on every menu open. You write that effect yourself in a separate file; the editor only emits the call.</span>
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
    mounted() {
        // Set initial filenames when component is loaded
        this.updateFileNames();
    },
    watch: {
        'state.mod_id'() {
            this.updateFileNames();
        },
        'state.mod_icon'() {
            if (!this.iconFileName) {
                this.updateFileNames();
            }
        },
        'state.mod_background'() {
            if (!this.backgroundFileName) {
                this.updateFileNames();
            }
        },
    },
    methods: {
        onModIdChange() {
            this.state.mod_id = this.state.mod_id.replace(/[^a-zA-Z0-9_]/g, '');
        },
        onTagsChange(e) {
            this.state.metadata_tags = e.target.value.split(',').map(t => t.trim()).filter(Boolean);
        },
        async onModIconChange(e) {
            const file = e.target.files[0];
            if (file) {
                this.iconFileName = file.name;
                const reader = new FileReader();
                reader.onload = (evt) => {
                    this.state.mod_icon = evt.target.result; // base64 data URL
                };
                reader.readAsDataURL(file);
            }
        },
        async onModBackgroundChange(e) {
            const file = e.target.files[0];
            if (file) {
                this.backgroundFileName = file.name;
                const reader = new FileReader();
                reader.onload = (evt) => {
                    this.state.mod_background = evt.target.result; // base64 data URL
                };
                reader.readAsDataURL(file);
            }
        },
        getIconFileName() {
            if (this.iconFileName) {
                return this.iconFileName;
            }
            if (this.state.mod_id) {
                return `${this.state.mod_id}.dds`;
            }
            return '✓ File selected';
        },
        getBackgroundFileName() {
            if (this.backgroundFileName) {
                return this.backgroundFileName;
            }
            if (this.state.mod_id) {
                return `${this.state.mod_id}_background.dds`;
            }
            return '✓ File selected';
        },
        updateFileNames() {
            // Reset filenames when mod_id changes or on initial load
            if (this.state.mod_icon && !this.iconFileName && this.state.mod_id) {
                this.iconFileName = `${this.state.mod_id}.dds`;
            }
            if (this.state.mod_background && !this.backgroundFileName && this.state.mod_id) {
                this.backgroundFileName = `${this.state.mod_id}_background.dds`;
            }
        },
    },
};
