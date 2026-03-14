const CodePanelComponent = {
    props: ['state'],
    data() {
        return {
            activeFile: 'on_action',
        };
    },
    computed: {
        files() {
            return CMMGenerator.generateAll(this.state);
        },
        fileKeys() {
            return Object.keys(this.files);
        },
        fileLabels() {
            const labels = {};
            for (const key of this.fileKeys) {
                const parts = key.split('/');
                labels[key] = parts[parts.length - 1];
            }
            return labels;
        },
        fileTabs() {
            return [
                { key: 'on_action', match: 'on_action' },
                { key: 'effects', match: 'scripted_effects' },
                { key: 'scripted_gui', match: 'scripted_guis' },
                { key: 'localization', match: 'localization' },
                { key: 'metadata', match: 'metadata.json' },
            ];
        },
        currentFileKey() {
            for (const fk of this.fileKeys) {
                const tab = this.fileTabs.find(t => t.key === this.activeFile);
                if (tab && fk.includes(tab.match)) return fk;
            }
            return this.fileKeys[0] || '';
        },
        currentContent() {
            return this.files[this.currentFileKey] || '// No content generated. Set a Mod ID to begin.';
        },
    },
    template: `
    <div class="code-panel">
        <div class="code-tabs">
            <button v-for="tab in fileTabs" :key="tab.key"
                class="code-tab" :class="{active: activeFile === tab.key}"
                @click="activeFile = tab.key">
                {{ tab.key }}
            </button>
        </div>
        <div class="code-file-path">{{ currentFileKey }}</div>
        <pre class="code-content"><code>{{ currentContent }}</code></pre>
    </div>
    `,
};
