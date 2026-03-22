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
        nextTick(() => { this._paused = false; });
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
            noinspection: false,
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
        const showSettings = ref(false);

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
            if (History._paused) return;
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
            obj[key] = obj[key].replace(/[^a-zA-Z0-9_]/g, '');
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
            tab.groups.push({ group_id: '', name: '', desc: '', settings: [] });
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
                    { index: 1, name: 'Option 1', desc: '', alias: '' },
                    { index: 2, name: 'Option 2', desc: '', alias: '' },
                    { index: 3, name: 'Option 3', desc: '', alias: '' },
                ],
                character_limit: 42,
                quote_text: 0,
                item_count: 3,
                is_ordered: 1,
                item_column_name: 'Item',
                item_names: ['Item A', 'Item B', 'Item C'],
                item_values: ['', '', ''],
                list_source: '',
                fields: [],
                on_changed_effect: '',
                pass_value_param: '',
                no_pass_value: false,
                alias: '',
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

        // ── Drag and drop ──────────────────────────────────────────
        // Drag state is NOT part of `state` so it doesn't trigger history/dirty.
        const drag = reactive({
            type: null,         // 'tab' | 'group' | 'setting' | null
            sourceTabIdx: -1,
            sourceGroupIdx: -1,
            sourceItemIdx: -1,
            overTabIdx: -1,
            overGroupIdx: -1,
            overItemIdx: -1,
            position: null,     // 'before' | 'after'
        });

        function resetDrag() {
            if (_scrollRAF) { cancelAnimationFrame(_scrollRAF); _scrollRAF = null; }
            drag.type = null;
            drag.sourceTabIdx = -1;
            drag.sourceGroupIdx = -1;
            drag.sourceItemIdx = -1;
            drag.overTabIdx = -1;
            drag.overGroupIdx = -1;
            drag.overItemIdx = -1;
            drag.position = null;
        }

        function moveItem(type, fromTabIdx, fromGroupIdx, fromIdx, toTabIdx, toGroupIdx, toIdx) {
            let srcArr, dstArr;
            if (type === 'tab') {
                srcArr = dstArr = state.tabs;
            } else if (type === 'group') {
                srcArr = state.tabs[fromTabIdx].groups;
                dstArr = state.tabs[toTabIdx].groups;
            } else {
                srcArr = state.tabs[fromTabIdx].groups[fromGroupIdx].settings;
                dstArr = state.tabs[toTabIdx].groups[toGroupIdx].settings;
            }

            if (srcArr === dstArr && fromIdx === toIdx) return;

            const [item] = srcArr.splice(fromIdx, 1);
            // Adjust target index if same array and source was before target
            if (srcArr === dstArr && fromIdx < toIdx) toIdx--;
            dstArr.splice(toIdx, 0, item);

            // Fix selection indices
            if (type === 'tab') {
                const sel = selectedTabIdx.value;
                if (fromIdx === sel) {
                    selectedTabIdx.value = toIdx;
                } else {
                    if (fromIdx < sel && toIdx >= sel) selectedTabIdx.value--;
                    else if (fromIdx > sel && toIdx <= sel) selectedTabIdx.value++;
                }
            } else if (type === 'group') {
                if (fromTabIdx === toTabIdx && fromTabIdx === selectedTabIdx.value) {
                    const sel = selectedGroupIdx.value;
                    if (fromIdx === sel) {
                        selectedGroupIdx.value = toIdx;
                    } else {
                        if (fromIdx < sel && toIdx >= sel) selectedGroupIdx.value--;
                        else if (fromIdx > sel && toIdx <= sel) selectedGroupIdx.value++;
                    }
                } else {
                    // Group left or entered the selected tab
                    if (fromTabIdx === selectedTabIdx.value) clampSelection();
                }
            }
        }

        // Horizontal position: left half = 'before', right half = 'after'
        function hPos(event) {
            const rect = event.currentTarget.getBoundingClientRect();
            return event.clientX < rect.left + rect.width / 2 ? 'before' : 'after';
        }
        // Vertical position: top half = 'before', bottom half = 'after'
        function vPos(event) {
            const rect = event.currentTarget.getBoundingClientRect();
            return event.clientY < rect.top + rect.height / 2 ? 'before' : 'after';
        }

        function insertIdx(overIdx, pos) {
            return pos === 'before' ? overIdx : overIdx + 1;
        }

        // Cancel drag if it started from an input/select/textarea
        function isInputEl(el) {
            const tag = el.tagName;
            return tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
        }

        // ── Drag start ─────────────────────────────────────────────
        function onDragStartTab(event, i) {
            drag.type = 'tab';
            drag.sourceTabIdx = i;
            drag.sourceItemIdx = i;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', '');
        }

        function onDragStartGroup(event, gi) {
            drag.type = 'group';
            drag.sourceTabIdx = selectedTabIdx.value;
            drag.sourceGroupIdx = gi;
            drag.sourceItemIdx = gi;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', '');
        }

        function onDragStartSetting(event, si) {
            if (!event.target.closest('.setting-card-header')) { event.preventDefault(); return; }
            if (isInputEl(event.target)) { event.preventDefault(); return; }
            drag.type = 'setting';
            drag.sourceTabIdx = selectedTabIdx.value;
            drag.sourceGroupIdx = selectedGroupIdx.value;
            drag.sourceItemIdx = si;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', '');
        }

        // ── Auto-scroll while dragging near edges ──────────────────
        let _scrollRAF = null;
        function dragAutoScroll(event) {
            const panel = event.target.closest('.editor-panel');
            if (!panel) return;
            const rect = panel.getBoundingClientRect();
            const edgeZone = 60;
            const maxSpeed = 18;
            let speed = 0;

            if (event.clientY < rect.top + edgeZone) {
                speed = -maxSpeed * (1 - (event.clientY - rect.top) / edgeZone);
            } else if (event.clientY > rect.bottom - edgeZone) {
                speed = maxSpeed * (1 - (rect.bottom - event.clientY) / edgeZone);
            }

            if (_scrollRAF) { cancelAnimationFrame(_scrollRAF); _scrollRAF = null; }
            if (speed !== 0) {
                (function scroll() {
                    panel.scrollTop += speed;
                    _scrollRAF = requestAnimationFrame(scroll);
                })();
            }
        }

        // ── Drag over (visual feedback) ────────────────────────────
        function onDragOverTab(event, i) {
            if (drag.type === 'tab' || drag.type === 'group' || drag.type === 'setting') {
                event.preventDefault();
                drag.overTabIdx = i;
                if (drag.type === 'tab') drag.position = hPos(event);
            }
        }

        function onDragOverGroup(event, gi) {
            if (drag.type === 'group' || drag.type === 'setting') {
                event.preventDefault();
                drag.overGroupIdx = gi;
                if (drag.type === 'group') drag.position = hPos(event);
            }
        }

        function onDragOverSetting(event, si) {
            if (drag.type === 'setting') {
                event.preventDefault();
                drag.overItemIdx = si;
                drag.position = vPos(event);
                dragAutoScroll(event);
            }
        }

        // ── Drag leave ─────────────────────────────────────────────
        function onDragLeaveTab(i) {
            if (drag.overTabIdx === i) drag.overTabIdx = -1;
        }
        function onDragLeaveGroup(gi) {
            if (drag.overGroupIdx === gi) drag.overGroupIdx = -1;
        }
        function onDragLeaveSetting(si) {
            if (drag.overItemIdx === si) { drag.overItemIdx = -1; drag.position = null; }
        }

        // ── Drop handlers ──────────────────────────────────────────
        function onDropTab(event, i) {
            event.preventDefault();
            if (drag.type === 'tab') {
                const to = insertIdx(i, drag.position);
                moveItem('tab', 0, 0, drag.sourceItemIdx, 0, 0, to);
            } else if (drag.type === 'group') {
                // Move group to end of target tab
                const targetGroups = state.tabs[i].groups;
                moveItem('group', drag.sourceTabIdx, 0, drag.sourceItemIdx, i, 0, targetGroups.length);
            } else if (drag.type === 'setting') {
                // Move setting to end of first group of target tab
                const targetTab = state.tabs[i];
                if (targetTab && targetTab.groups.length) {
                    const targetSettings = targetTab.groups[0].settings;
                    moveItem('setting', drag.sourceTabIdx, drag.sourceGroupIdx, drag.sourceItemIdx, i, 0, targetSettings.length);
                }
            }
            resetDrag();
        }

        function onDropGroup(event, gi) {
            event.preventDefault();
            event.stopPropagation();
            const currentTabIdx = selectedTabIdx.value;
            if (drag.type === 'group') {
                const to = insertIdx(gi, drag.position);
                moveItem('group', drag.sourceTabIdx, 0, drag.sourceItemIdx, currentTabIdx, 0, to);
            } else if (drag.type === 'setting') {
                // Move setting to end of target group
                const targetSettings = state.tabs[currentTabIdx].groups[gi].settings;
                moveItem('setting', drag.sourceTabIdx, drag.sourceGroupIdx, drag.sourceItemIdx, currentTabIdx, gi, targetSettings.length);
            }
            resetDrag();
        }

        function onDropSetting(event, si) {
            event.preventDefault();
            event.stopPropagation();
            if (drag.type !== 'setting') { resetDrag(); return; }
            const curTab = selectedTabIdx.value;
            const curGroup = selectedGroupIdx.value;
            const to = insertIdx(si, drag.position);
            moveItem('setting', drag.sourceTabIdx, drag.sourceGroupIdx, drag.sourceItemIdx, curTab, curGroup, to);
            resetDrag();
        }

        function onDropEmptyGroup(event) {
            event.preventDefault();
            if (drag.type !== 'setting') { resetDrag(); return; }
            const curTab = selectedTabIdx.value;
            const curGroup = selectedGroupIdx.value;
            moveItem('setting', drag.sourceTabIdx, drag.sourceGroupIdx, drag.sourceItemIdx, curTab, curGroup, 0);
            resetDrag();
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
                metadata_game_version: '1.1.*', noinspection: false, tabs: [],
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
            modDir, dirty, saveStatus, saveError, showSettings,
            undoCount, redoCount,
            drag, resetDrag,
            sanitizeId, addTab, removeTab, addGroup, removeGroup,
            addSetting, removeSetting, moveSetting, onUpdate,
            onDragStartTab, onDragStartGroup, onDragStartSetting,
            onDragOverTab, onDragOverGroup, onDragOverSetting,
            onDragLeaveTab, onDragLeaveGroup, onDragLeaveSetting,
            onDropTab, onDropGroup, onDropSetting, onDropEmptyGroup,
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
