const { createApp, reactive, computed, ref, watch, toRaw, nextTick, onMounted } = Vue;

// ── Undo / Redo history ─────────────────────────────────────────────
const History = {
    _past: [],
    _future: [],
    _current: null,        // snapshot of the current/latest state
    _maxSize: 200,
    _paused: false,

    snapshot(state) {
        return JSON.parse(JSON.stringify(toRaw(state)));
    },

    // Set the initial baseline (call once at startup or after import)
    init(state) {
        this._current = this.snapshot(state);
        this._past.length = 0;
        this._future.length = 0;
    },

    // Record a new state: previous _current goes onto _past
    push(state) {
        if (this._paused) return;
        if (this._current) {
            this._past.push(this._current);
            if (this._past.length > this._maxSize) this._past.shift();
        }
        this._current = this.snapshot(state);
        this._future.length = 0;
    },

    undo(state) {
        if (!this._past.length) return false;
        this._future.push(this._current);
        this._current = this._past.pop();
        this._apply(state, this._current);
        return true;
    },

    redo(state) {
        if (!this._future.length) return false;
        this._past.push(this._current);
        this._current = this._future.pop();
        this._apply(state, this._current);
        return true;
    },

    _apply(state, snap) {
        this._paused = true;
        // Deep-clone so _current isn't shared with reactive state
        const copy = JSON.parse(JSON.stringify(snap));
        Object.keys(copy).forEach(k => { state[k] = copy[k]; });
        this._paused = false;
    },

    clear() {
        this._past.length = 0;
        this._future.length = 0;
        this._current = null;
    },

    get canUndo() { return this._past.length > 0; },
    get canRedo() { return this._future.length > 0; },
};

// ── App ──────────────────────────────────────────────────────────────
const app = createApp({
    setup() {
        const state = reactive({
            mod_id: '',
            file_prefix: '',
            mod_name: '',
            mod_desc: '',
            metadata_name: '',
            metadata_id: '',
            metadata_version: '0.1',
            metadata_short_description: '',
            metadata_tags: ['Utilities'],
            metadata_game_version: '1.1.*',
            tabs: [],
        });

        const selectedTabIdx = ref(0);
        const selectedGroupIdx = ref(0);
        const rightTab = ref('preview');
        const showImport = ref(false);
        const importPath = ref('');
        const importWarnings = ref([]);

        // Direct-edit state
        const modDir = ref('');           // directory currently being edited
        const dirty = ref(false);         // unsaved changes exist
        const saveStatus = ref('');       // '', 'saving', 'saved', 'error'
        const saveError = ref('');

        // Undo/redo reactivity helpers (Vue can't observe getters on a plain object)
        const undoCount = ref(0);
        const redoCount = ref(0);
        function refreshHistoryCounts() {
            undoCount.value = History._past.length;
            redoCount.value = History._future.length;
        }

        // ── History: push a snapshot before every mutation ────────
        let historyTimer = null;
        // Debounced push – coalesces rapid keystrokes into one snapshot
        function schedulePush() {
            if (historyTimer) clearTimeout(historyTimer);
            historyTimer = setTimeout(() => {
                History.push(state);
                refreshHistoryCounts();
                historyTimer = null;
            }, 400);
        }

        // Deep watch the whole state tree
        watch(state, () => {
            dirty.value = true;
            if (saveStatus.value === 'saved') saveStatus.value = '';
            schedulePush();
        }, { deep: true });

        // Set the initial baseline so the very first edit can be undone
        History.init(state);

        function undo() {
            // flush any pending debounced push first
            if (historyTimer) { clearTimeout(historyTimer); historyTimer = null; History.push(state); }
            if (History.undo(state)) {
                clampSelection();
                refreshHistoryCounts();
            }
        }

        function redo() {
            if (historyTimer) { clearTimeout(historyTimer); historyTimer = null; History.push(state); }
            if (History.redo(state)) {
                clampSelection();
                refreshHistoryCounts();
            }
        }

        // ── Keyboard shortcuts ───────────────────────────────────
        window.addEventListener('keydown', (e) => {
            const mod = e.ctrlKey || e.metaKey;
            if (mod && e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
            if (mod && e.key === 'z' && e.shiftKey)  { e.preventDefault(); redo(); }
            if (mod && e.key === 'y')                 { e.preventDefault(); redo(); }
            if (mod && e.key === 's')                 { e.preventDefault(); saveToDir(); }
        });

        // ── Selection helpers ────────────────────────────────────
        const selectedTab = computed(() => state.tabs[selectedTabIdx.value] || null);
        const selectedGroup = computed(() => {
            const tab = selectedTab.value;
            if (!tab) return null;
            return tab.groups[selectedGroupIdx.value] || null;
        });

        function clampSelection() {
            if (selectedTabIdx.value >= state.tabs.length)
                selectedTabIdx.value = Math.max(0, state.tabs.length - 1);
            const tab = state.tabs[selectedTabIdx.value];
            if (tab && selectedGroupIdx.value >= tab.groups.length)
                selectedGroupIdx.value = Math.max(0, tab.groups.length - 1);
        }

        watch(() => state.tabs.length, clampSelection);
        watch(selectedTabIdx, () => { selectedGroupIdx.value = 0; });

        // ── Mutations (all go through history) ───────────────────
        function sanitizeId(obj, key) {
            obj[key] = obj[key].replace(/[^a-z0-9_]/gi, '').toLowerCase();
        }

        function addTab() {
            state.tabs.push({ tab_id: '', name: '', groups: [] });
            selectedTabIdx.value = state.tabs.length - 1;
            selectedGroupIdx.value = 0;
        }

        function removeTab(i) {
            state.tabs.splice(i, 1);
            clampSelection();
        }

        function addGroup() {
            const tab = selectedTab.value;
            if (!tab) return;
            tab.groups.push({ group_id: '', name: '', settings: [] });
            selectedGroupIdx.value = tab.groups.length - 1;
        }

        function removeGroup(i) {
            const tab = selectedTab.value;
            if (!tab) return;
            tab.groups.splice(i, 1);
            clampSelection();
        }

        function addSetting() {
            const group = selectedGroup.value;
            if (!group) return;
            group.settings.push({
                setting_id: '',
                setting_type: 'bool',
                is_global: false,
                name: '',
                desc: '',
                default_value: 0,
                button_text: 'Run',
                min_value: 0,
                max_value: 100,
                step_value: 1,
                default_index: 1,
                option_count: 3,
                options: [
                    { index: 1, name: 'Option 1' },
                    { index: 2, name: 'Option 2' },
                    { index: 3, name: 'Option 3' },
                ],
                character_limit: 42,
                quote_text: 0,
                item_count: 3,
                is_ordered: 1,
                item_column_name: 'Item',
                item_names: ['Item A', 'Item B', 'Item C'],
                fields: [],
                on_changed_effect: '',
                pass_value_param: '',
                no_pass_value: false,
            });
        }

        function removeSetting(i) {
            const group = selectedGroup.value;
            if (group) group.settings.splice(i, 1);
        }

        function moveSetting(i, dir) {
            const group = selectedGroup.value;
            if (!group) return;
            const j = i + dir;
            if (j < 0 || j >= group.settings.length) return;
            const temp = group.settings[i];
            group.settings[i] = group.settings[j];
            group.settings[j] = temp;
        }

        function onUpdate(data) {
            Object.assign(state, data);
        }

        // ── Import ───────────────────────────────────────────────
        async function importFromDir() {
            importWarnings.value = [];
            try {
                const resp = await fetch('/api/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ directory: importPath.value }),
                });
                const data = await resp.json();
                if (data.error) {
                    importWarnings.value = [data.error];
                    return;
                }
                if (data._warnings) importWarnings.value = data._warnings;

                const warnings = data._warnings;
                delete data._warnings;

                // Reset history and apply
                if (historyTimer) { clearTimeout(historyTimer); historyTimer = null; }
                History.clear();
                History.init(state);   // baseline = pre-import state
                Object.assign(state, data);
                selectedTabIdx.value = 0;
                selectedGroupIdx.value = 0;

                // Cancel watcher's debounced push and record import as new state
                if (historyTimer) { clearTimeout(historyTimer); historyTimer = null; }
                History.push(state);   // pre-import → _past, post-import → _current

                // Enter direct-edit mode
                modDir.value = importPath.value;
                dirty.value = false;
                saveStatus.value = '';
                refreshHistoryCounts();

                if (!importWarnings.value.length) showImport.value = false;
            } catch (e) {
                importWarnings.value = ['Import failed: ' + e.message];
            }
        }

        // ── Save directly to directory ───────────────────────────
        async function saveToDir() {
            const dir = modDir.value;
            if (!dir || !state.mod_id) return;
            saveStatus.value = 'saving';
            saveError.value = '';
            try {
                const resp = await fetch('/api/export', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ output_dir: dir, model: toRaw(state) }),
                });
                const data = await resp.json();
                if (data.error) {
                    saveStatus.value = 'error';
                    saveError.value = data.error;
                    return;
                }
                saveStatus.value = 'saved';
                dirty.value = false;
            } catch (e) {
                saveStatus.value = 'error';
                saveError.value = e.message;
            }
        }

        // ── Download ZIP ─────────────────────────────────────────
        async function generateAndDownload() {
            try {
                const resp = await fetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(state),
                });
                if (!resp.ok) {
                    const err = await resp.json();
                    alert('Error: ' + (err.error || 'Unknown error'));
                    return;
                }
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = (state.file_prefix || state.mod_id || 'cmm_mod') + '_cmm_integration.zip';
                a.click();
                URL.revokeObjectURL(url);
            } catch (e) {
                alert('Download failed: ' + e.message);
            }
        }

        // ── Open new (empty) directory ──────────────────────────
        function openNewDir() {
            if (!importPath.value) return;
            if (historyTimer) { clearTimeout(historyTimer); historyTimer = null; }
            History.clear();
            // Reset state to defaults
            const defaults = {
                mod_id: '', file_prefix: '', mod_name: '', mod_desc: '',
                metadata_name: '', metadata_id: '', metadata_version: '0.1',
                metadata_short_description: '', metadata_tags: ['Utilities'],
                metadata_game_version: '1.1.*', tabs: [],
            };
            Object.assign(state, defaults);
            selectedTabIdx.value = 0;
            selectedGroupIdx.value = 0;

            if (historyTimer) { clearTimeout(historyTimer); historyTimer = null; }
            modDir.value = importPath.value;
            dirty.value = false;
            saveStatus.value = '';
            History.init(state);
            refreshHistoryCounts();
            showImport.value = false;
        }

        // ── Browse for directory ──────────────────────────────────
        async function browseDir() {
            try {
                const resp = await fetch('/api/browse');
                const data = await resp.json();
                if (data.directory) {
                    importPath.value = data.directory;
                }
            } catch (e) {
                // silently ignore if browse fails
            }
        }

        // ── Close / disconnect from directory ────────────────────
        function closeModDir() {
            modDir.value = '';
            dirty.value = false;
            saveStatus.value = '';
        }

        // ── Close the editor (shutdown server) ───────────────────
        async function closeApp() {
            if (dirty.value && !confirm('You have unsaved changes. Close anyway?')) return;
            try {
                await fetch('/api/shutdown', { method: 'POST' });
            } catch (e) { /* connection will drop */ }
            document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#888"><p>CMM Visual Editor closed. You can close this tab.</p></div>';
        }

        // Auto-open mod directory if server detected one
        onMounted(async () => {
            try {
                const resp = await fetch('/api/auto-open');
                const data = await resp.json();
                if (!data.directory) return;

                const importResp = await fetch('/api/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ directory: data.directory }),
                });
                const importData = await importResp.json();
                if (importData.error) return;

                const warnings = importData._warnings || [];
                delete importData._warnings;

                if (historyTimer) { clearTimeout(historyTimer); historyTimer = null; }
                History.clear();
                Object.assign(state, importData);
                selectedTabIdx.value = 0;
                selectedGroupIdx.value = 0;
                modDir.value = data.directory;
                dirty.value = false;
                saveStatus.value = '';
                if (warnings.length) importWarnings.value = warnings;

                if (historyTimer) { clearTimeout(historyTimer); historyTimer = null; }
                History.init(state);
                refreshHistoryCounts();
            } catch (e) { console.error('Auto-open failed:', e); }
        });

        return {
            state, selectedTabIdx, selectedGroupIdx, rightTab,
            showImport, importPath, importWarnings,
            selectedTab, selectedGroup,
            modDir, dirty, saveStatus, saveError,
            undoCount, redoCount,
            sanitizeId, addTab, removeTab, addGroup, removeGroup,
            addSetting, removeSetting, moveSetting, onUpdate,
            generateAndDownload, importFromDir, saveToDir, closeModDir,
            openNewDir, browseDir, undo, redo, closeApp,
        };
    },
});

// Register components
app.component('mod-editor', ModEditorComponent);
app.component('setting-editor', SettingEditorComponent);
app.component('list-editor', ListEditorComponent);
app.component('dropdown-options', DropdownOptionsComponent);
app.component('preview-panel', PreviewPanelComponent);
app.component('code-panel', CodePanelComponent);
app.component('localization-panel', LocalizationPanelComponent);

app.mount('#app');
