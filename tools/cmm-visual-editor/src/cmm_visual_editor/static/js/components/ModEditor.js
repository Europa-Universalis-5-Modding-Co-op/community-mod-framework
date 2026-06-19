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
            <label class="checkbox-label">
                <input type="checkbox" v-model="state.lobby_banner">
                Lobby Banner
            </label>
            <span class="field-hint">Show this mod's icon as a banner in the pre-game lobby.</span>
        </div>
        <div class="field-row" v-if="state.lobby_banner">
            <label>Banner Icon</label>
            <div class="file-picker">
                <input type="file" @change="onBannerIconChange" ref="bannerIconInput" class="file-input-hidden">
                <button type="button" class="btn btn-sm" @click="$refs.bannerIconInput.click()">Choose Image...</button>
                <span class="file-picker-name">{{ state.banner_icon ? getBannerIconFileName() : 'No image chosen' }}</span>
            </div>
        </div>
        <div class="field-row" v-if="state.lobby_banner">
            <label>Banner Background</label>
            <div class="file-picker">
                <input type="file" @change="onBannerBackgroundChange" ref="bannerBackgroundInput" class="file-input-hidden">
                <button type="button" class="btn btn-sm" @click="$refs.bannerBackgroundInput.click()">Choose Image...</button>
                <span class="file-picker-name">{{ state.banner_background ? getBannerBackgroundFileName() : 'No image chosen' }}</span>
            </div>
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
        'state.banner_icon'() {
            if (!this.iconFileName) {
                this.updateFileNames();
            }
        },
        'state.banner_background'() {
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
        async onBannerIconChange(e) {
            const file = e.target.files[0];
            if (file) {
                this.iconFileName = file.name;
                const reader = new FileReader();
                reader.onload = (evt) => {
                    this.state.banner_icon = evt.target.result; // base64 data URL
                };
                reader.readAsDataURL(file);
            }
        },
        async onBannerBackgroundChange(e) {
            const file = e.target.files[0];
            if (file) {
                this.backgroundFileName = file.name;
                const reader = new FileReader();
                reader.onload = (evt) => {
                    this.state.banner_background = evt.target.result; // base64 data URL
                };
                reader.readAsDataURL(file);
            }
        },
        getBannerIconFileName() {
            if (this.iconFileName) {
                return this.iconFileName;
            }
            if (this.state.mod_id) {
                return `${this.state.mod_id}_banner_logo.dds`;
            }
            return 'File selected';
        },
        getBannerBackgroundFileName() {
            if (this.backgroundFileName) {
                return this.backgroundFileName;
            }
            if (this.state.mod_id) {
                return `${this.state.mod_id}_banner_background.dds`;
            }
            return 'File selected';
        },
        updateFileNames() {
            // Reset filenames when mod_id changes or on initial load
            if (this.state.banner_icon && !this.iconFileName && this.state.mod_id) {
                this.iconFileName = `${this.state.mod_id}_banner_logo.dds`;
            }
            if (this.state.banner_background && !this.backgroundFileName && this.state.mod_id) {
                this.backgroundFileName = `${this.state.mod_id}_banner_background.dds`;
            }
        },
    },
};
