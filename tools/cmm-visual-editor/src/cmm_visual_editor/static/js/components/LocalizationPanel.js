const LocalizationPanelComponent = {
    props: ['state'],
    computed: {
        locKeys() {
            const modId = this.state.mod_id;
            if (!modId) return [];
            const keys = [];

            keys.push({ key: `${modId}_name`, value: this.state.mod_name, category: 'Mod' });
            keys.push({ key: `${modId}_desc`, value: this.state.mod_desc, category: 'Mod' });

            for (const tab of (this.state.tabs || [])) {
                keys.push({ key: `${modId}__${tab.tab_id}_name`, value: tab.name, category: 'Tabs' });
                for (const group of (tab.groups || [])) {
                    keys.push({ key: `${modId}__${group.group_id}_name`, value: group.name, category: 'Groups' });
                    for (const s of (group.settings || [])) {
                        const qid = `${modId}__${s.setting_id}`;
                        keys.push({ key: `${qid}_name`, value: s.name, category: 'Settings' });
                        keys.push({ key: `${qid}_desc`, value: s.desc, category: 'Settings' });
                        if (s.setting_type === 'button') {
                            keys.push({ key: `${qid}_text`, value: s.button_text || '', category: 'Settings' });
                        }
                        if (s.setting_type === 'dropdown') {
                            for (const opt of (s.options || [])) {
                                keys.push({ key: `${qid}_option_${opt.index}_name`, value: opt.name, category: 'Dropdown Options' });
                            }
                        }
                        if (s.setting_type === 'list') {
                            keys.push({ key: `${qid}_item_column_name`, value: s.item_column_name || '', category: 'List' });
                            for (let i = 0; i < (s.item_names || []).length; i++) {
                                keys.push({ key: `${qid}_item_${i + 1}_name`, value: s.item_names[i], category: 'List' });
                            }
                            for (const f of (s.fields || [])) {
                                const fqid = `${qid}__${f.field_id}`;
                                keys.push({ key: `${fqid}_name`, value: f.name, category: 'List Fields' });
                                if (f.field_type === 'dropdown') {
                                    for (const opt of (f.options || [])) {
                                        keys.push({ key: `${fqid}_option_${opt.index}_name`, value: opt.name, category: 'List Field Options' });
                                    }
                                }
                            }
                        }
                    }
                }
            }
            return keys;
        },
    },
    template: `
    <div class="loc-panel">
        <h3>Localization Keys</h3>
        <p class="loc-hint">All keys are auto-derived from IDs. Edit values in the Editor panel.</p>
        <table class="loc-table">
            <thead>
                <tr>
                    <th>Key</th>
                    <th>Value</th>
                    <th>Category</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in locKeys" :key="item.key" :class="{'loc-missing': !item.value}">
                    <td class="loc-key">{{ item.key }}</td>
                    <td>{{ item.value || '(empty)' }}</td>
                    <td class="loc-cat">{{ item.category }}</td>
                </tr>
            </tbody>
        </table>
        <div v-if="!locKeys.length" class="empty-state">Set a Mod ID to see localization keys.</div>
    </div>
    `,
};
