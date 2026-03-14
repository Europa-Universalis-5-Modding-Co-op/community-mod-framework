const PreviewPanelComponent = {
    props: ['state'],
    data() {
        return {
            previewTabIdx: 0,
        };
    },
    computed: {
        previewTabs() {
            return this.state.tabs || [];
        },
        currentTab() {
            return this.previewTabs[this.previewTabIdx] || null;
        },
    },
    watch: {
        'state.tabs.length'() {
            if (this.previewTabIdx >= this.state.tabs.length) {
                this.previewTabIdx = Math.max(0, this.state.tabs.length - 1);
            }
        },
    },
    template: `
    <div class="cmm-preview">
        <div class="cmm-window">
            <!-- Title Bar -->
            <div class="cmm-titlebar">
                <span class="cmm-title">{{ state.mod_name || 'Mod Name' }}</span>
                <span class="cmm-close">&times;</span>
            </div>

            <div class="cmm-body">
                <!-- Left: Mod list -->
                <div class="cmm-left">
                    <div class="cmm-search">
                        <input disabled placeholder="Search mods" class="cmm-search-input">
                    </div>
                    <div class="cmm-mod-list">
                        <div class="cmm-mod-item active">
                            {{ state.mod_name || 'Mod Name' }}
                        </div>
                    </div>
                </div>

                <!-- Right: Settings -->
                <div class="cmm-right">
                    <!-- Tab bar -->
                    <div class="cmm-tab-bar" v-if="previewTabs.length">
                        <button v-for="(tab, ti) in previewTabs" :key="ti"
                            class="cmm-tab" :class="{active: previewTabIdx === ti}"
                            @click="previewTabIdx = ti">
                            {{ tab.name || tab.tab_id || 'Tab' }}
                        </button>
                    </div>

                    <div class="cmm-settings-area" v-if="currentTab">
                        <div v-for="group in (currentTab.groups || [])" :key="group.group_id" class="cmm-group">
                            <div class="cmm-group-header">
                                <span>{{ group.name || group.group_id }}</span>
                            </div>
                            <div class="cmm-group-body">
                                <div v-for="setting in (group.settings || [])" :key="setting.setting_id" class="cmm-setting-row">
                                    <!-- Bool -->
                                    <template v-if="setting.setting_type === 'bool'">
                                        <span class="cmm-setting-name">{{ setting.name || setting.setting_id }}</span>
                                        <div class="cmm-control">
                                            <div class="cmm-checkbox" :class="{checked: setting.default_value}"></div>
                                        </div>
                                    </template>

                                    <!-- Button -->
                                    <template v-if="setting.setting_type === 'button'">
                                        <span class="cmm-setting-name">{{ setting.name || setting.setting_id }}</span>
                                        <div class="cmm-control">
                                            <button class="cmm-btn">{{ setting.button_text || 'Run' }}</button>
                                        </div>
                                    </template>

                                    <!-- Numeric -->
                                    <template v-if="setting.setting_type === 'numeric'">
                                        <span class="cmm-setting-name">{{ setting.name || setting.setting_id }}</span>
                                        <div class="cmm-control cmm-numeric">
                                            <button class="cmm-step-btn">-</button>
                                            <span class="cmm-value">{{ setting.default_value }}</span>
                                            <button class="cmm-step-btn">+</button>
                                        </div>
                                    </template>

                                    <!-- Slider -->
                                    <template v-if="setting.setting_type === 'slider'">
                                        <span class="cmm-setting-name">{{ setting.name || setting.setting_id }}</span>
                                        <div class="cmm-control cmm-slider">
                                            <button class="cmm-step-btn">-</button>
                                            <div class="cmm-slider-track">
                                                <div class="cmm-slider-fill" :style="{width: sliderPercent(setting) + '%'}"></div>
                                                <div class="cmm-slider-thumb" :style="{left: sliderPercent(setting) + '%'}"></div>
                                            </div>
                                            <button class="cmm-step-btn">+</button>
                                            <span class="cmm-value">{{ setting.default_value }}</span>
                                        </div>
                                    </template>

                                    <!-- Dropdown -->
                                    <template v-if="setting.setting_type === 'dropdown'">
                                        <span class="cmm-setting-name">{{ setting.name || setting.setting_id }}</span>
                                        <div class="cmm-control">
                                            <div class="cmm-dropdown">
                                                {{ currentOptionName(setting) }}
                                                <span class="cmm-dropdown-arrow">&#9660;</span>
                                            </div>
                                        </div>
                                    </template>

                                    <!-- Text -->
                                    <template v-if="setting.setting_type === 'text'">
                                        <span class="cmm-setting-name">{{ setting.name || setting.setting_id }}</span>
                                        <div class="cmm-control cmm-text-control">
                                            <input class="cmm-text-input" disabled placeholder="Enter text" :maxlength="setting.character_limit">
                                            <button class="cmm-btn cmm-btn-sm">Apply</button>
                                        </div>
                                    </template>

                                    <!-- List -->
                                    <template v-if="setting.setting_type === 'list'">
                                        <div class="cmm-list-setting">
                                            <div class="cmm-list-header-row">
                                                <span class="cmm-list-col" v-if="setting.is_ordered" style="width:30px"></span>
                                                <span class="cmm-list-col cmm-list-item-col">{{ setting.item_column_name || 'Item' }}</span>
                                                <span class="cmm-list-col" v-for="f in (setting.fields||[])">{{ f.name || f.field_id }}</span>
                                            </div>
                                            <div v-for="(iname, ii) in (setting.item_names||[]).slice(0, setting.item_count)" :key="ii" class="cmm-list-row">
                                                <span class="cmm-list-col" v-if="setting.is_ordered" style="width:30px">
                                                    <span class="cmm-list-move">&#9650;&#9660;</span>
                                                </span>
                                                <span class="cmm-list-col cmm-list-item-col">{{ iname }}</span>
                                                <span class="cmm-list-col" v-for="f in (setting.fields||[])">
                                                    <span v-if="f.field_type==='bool'" class="cmm-checkbox" :class="{checked: f.default_value}"></span>
                                                    <span v-if="f.field_type==='dropdown'" class="cmm-mini-dropdown">{{ fieldOptionName(f) }}</span>
                                                    <span v-if="f.field_type==='numeric'" class="cmm-mini-numeric">{{ f.default_value }}</span>
                                                </span>
                                            </div>
                                        </div>
                                    </template>
                                </div>

                                <div v-if="!group.settings || !group.settings.length" class="cmm-empty">
                                    No settings in this group.
                                </div>
                            </div>
                        </div>
                    </div>
                    <div v-else class="cmm-empty-tab">
                        No tabs configured.
                    </div>
                </div>
            </div>
        </div>
    </div>
    `,
    methods: {
        sliderPercent(setting) {
            const min = setting.min_value || 0;
            const max = setting.max_value || 100;
            const val = setting.default_value || 0;
            if (max === min) return 50;
            return Math.max(0, Math.min(100, ((val - min) / (max - min)) * 100));
        },
        currentOptionName(setting) {
            const idx = setting.default_index || 1;
            if (setting.options && setting.options[idx - 1]) {
                return setting.options[idx - 1].name;
            }
            return `Option ${idx}`;
        },
        fieldOptionName(field) {
            const idx = field.default_index || 1;
            if (field.options && field.options[idx - 1]) {
                return field.options[idx - 1].name;
            }
            return `Option ${idx}`;
        },
    },
};
