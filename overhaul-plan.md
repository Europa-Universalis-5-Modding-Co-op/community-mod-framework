# Pre-Release Refactor: Implementation Plan

## Context

This is the final opportunity for breaking changes before the Community Mod Framework (CMF/CMM) release. The goals are:

1. **Eliminate mandatory callbacks** — Mod authors currently MUST define a `_on_changed` scripted GUI for every setting. Auto-apply via variable maps + `AddScope` removes this requirement.
2. **Modernize storage** — Move metadata and values to EU5 1.1 variable maps for cleaner internals and new features.
3. **Clean up API** — Consistent naming, add missing features (global/local registration stays separate).

**Critical dependency**: The auto-apply system relies on engine behaviors that have been validated in Phase 0. See the "EU5 Engine Bugs" section below for confirmed issues that **must** be worked around in every phase.

---

## Implementation Rules

These rules apply to every phase. Violating them produces hard-to-diagnose bugs.

### Complete Each Phase Fully Before Moving On

Do not start Phase N+1 until Phase N is finished, tested, and has zero warnings/errors. Lessons learned in one phase inform the next — skipping ahead means missing those lessons and introducing bugs that compound across phases.

### Replace Completely — No Compatibility Shims

When moving storage from plain variables to maps, **remove the old variables entirely**. Do not keep both "for compatibility" — this creates two sources of truth and orphaned variable references that trigger warnings. If a later phase reads an old variable, update that read NOW, not later.

### Every Variable Map Needs Warning Suppression

The EU5 validator cannot trace reads through `"variable_map(...)"` quoted scope links. Every variable map name written via `add_to_variable_map` will produce a "set but never used" warning. Suppress with `has_variable_map = <name>` inside an `always = no` dead branch in a **used** effect (the `cmm_init_variable_maps` effect is ideal). Similarly, `flag:cmm_init` needs `exists = flag:cmm_init`.

For "used but never set" warnings (variables set at runtime via conditional paths the validator can't trace), add a dead-branch `set_variable`:
```
if = {
    limit = { always = no }
    set_variable = { name = X value = 0 }
}
```

### Every New GUI Element Needs Localization

Any new `text = "KEY"` in a `.gui` file requires a corresponding entry in `main_menu/localization/english/cmm_l_english.yml` (and ideally all language files). Missing localization produces unlocalized text warnings and renders as the raw key string.

### GUI Widgets Need Explicit Sizing or Known-Working Types

`button_wax` requires `blockoverride "button_texture"`, `using = FrontEndMiddleSectionButton`, and explicit `size` — it is a pause-menu-specific type. For buttons inside the CMM settings panel, use `button_regular` with `minimumsize = { 168 32 }` instead — this is the same type used by button settings and is confirmed working.

### Avoiding Code Duplication for Global/Local Scope

Paradox `$macro$` parameters expand at compile time before parsing. Macros CAN compose **command names** — but ONLY when the expanded value is non-empty. `every_in_$s$list` with `$s$ = global_` correctly becomes `every_in_global_list`. However, there is **no way to pass an empty string** as a macro parameter — `$s$ = ""` expands to literal quote characters (`every_in_""list`), and `$s$ = ` (nothing) causes parse errors.

**Consequence**: You cannot use empty-vs-prefix (`$s$ = ""` vs `$s$ = global_`) because `""` inserts literal quote characters into the command name.

**Working approach — non-empty macro values that compose valid command names**: Pass macro parameters whose values are always non-empty fragments of the target command name:

| Parameter | Country value | Global value | Example composition |
|-----------|--------------|-------------|---------------------|
| `$vt$` | `variable` | `global_variable` | `add_to_$vt$_list` → `add_to_variable_list` / `add_to_global_variable_list` |
| `$lt$` | `in` | `in_global` | `every_$lt$_list` → `every_in_list` / `every_in_global_list` |

This works for ALL variable, list, and map commands:
```
# Registration — zero branching, zero duplication:
cmm_add_list_item_identity = {
    add_to_$vt$_list = {
        name = cmm_list_items_$mod_id$__$setting_id$
        target = flag:$mod_id$__$setting_id$_item_$item$
    }
}
```

Confirmed working: `add_to_$vt$_list`, `clear_$vt$_list`, `add_to_$vt$_map`, `remove_from_$vt$_map`, `is_key_in_$vt$_map`, `every_$lt$_list`.

**For runtime scope detection** (when the scope is determined by data, not by which API was called), use a country-scoped temporary variable set once at the top of the call chain:
```
# Top-level entry point
cmm_apply_list_change = {
    set_local_variable = { name = cmm_tmp_flag value = flag:$setting$ }
    set_variable = { name = cmm_tmp_is_global_list value = "variable_map(cmm_is_global|local_var:cmm_tmp_flag)" }
    # ... dispatch to sub-effects which check var:cmm_tmp_is_global_list ...
    remove_variable = cmm_tmp_is_global_list
}

# Leaf function
cmm_list_apply_field_slot_at_item = {
    if = {
        limit = { var:cmm_tmp_is_global_list >= 1 }
        remove_from_global_variable_map = { ... }
        add_to_global_variable_map = { ... }
    }
    else = {
        remove_from_variable_map = { ... }
        add_to_variable_map = { ... }
    }
}
```

This avoids threading a `$scope$` parameter through every function in the dispatch chain.

**Quoted scope links** (`"variable_map(...)"` / `"global_variable_map(...)"`) cannot be parameterized at all — macros don't expand inside quotes (Bug 2). For reads from variable maps, always branch with if/else and read into a local variable:
```
if = {
    limit = { var:cmm_tmp_is_global_list >= 1 }
    set_local_variable = { name = cmm_field_val value = "global_variable_map(cmm|local_var:cmm_tmp_fk)" }
}
else = {
    set_local_variable = { name = cmm_field_val value = "variable_map(cmm|local_var:cmm_tmp_fk)" }
}
# Then use local_var:cmm_field_val for logic
```

### EU5 Scope Facts

- `every_player` does **NOT** exist. Use `every_country` (with `limit = { is_ai = no }` if you only want human players).
- `on_game_start` fires with **no scope** — you cannot use `set_variable` (country-scoped) there. Use global maps or defer to first scripted GUI call.

---

## EU5 Engine Bugs (Confirmed via `submods/cmf-engine-test/`)

These are confirmed engine behaviors discovered during testing. Every phase that writes to variable maps MUST account for these.

### Bug 1: `add_to_variable_map` Never Updates — It Is Strictly "Add Only"

**Symptom**: `add_to_variable_map` / `add_to_global_variable_map` **never updates** an existing entry. If the key already exists in the map, the call is a silent no-op regardless of key type. This applies to ALL key types — `flag:`, `scope:`, `var:`, `local_var:` — the command simply does not have update semantics.

**Engine test results**:
- Tests 1-3 PASS: `scope:setting` works as a key for fresh writes and reads
- Tests 4-11 PASS: Cross-context reads work (flag:-written entries readable via scope:setting)
- **Tests 12-13**: FAIL when country tests run first (entry exists → no-op), PASS when country tests not run (no entry → fresh add). This confirms the "add only" behavior.
- **Test 14**: Same pattern — FAIL with existing entry, PASS without
- **Test 15**: Same pattern — reads back what test 12 wrote (or didn't write)
- Test 16 PASS: `scope:setting == flag:engine_test_key_a` — the keys ARE equal for comparisons
- Test 17 PASS: `remove_from_variable_map` with scope:setting DOES remove a flag:-created entry
- Tests 18-19 PASS: Remove-then-add workaround works for both global and country maps
- **Test 22 FAIL**: flag:→flag: same-key update on country map — confirms add_to NEVER updates
- **Test 23 FAIL**: flag:→flag: same-key update on global map — confirms add_to NEVER updates

**Root cause**: `add_to_variable_map` is literally "add to" — it inserts a new entry only if the key doesn't exist. It has no update/overwrite semantics. The "add_to" in the name is accurate. This is NOT about key type mismatches (as previously theorized) — it's fundamental to the command.

**Mandatory workaround**: Every `add_to_variable_map` / `add_to_global_variable_map` that updates a value (not just initial creation) MUST be preceded by a `remove_from_variable_map` / `remove_from_global_variable_map`:
```
# WRONG — silently fails if entry was created with flag:
add_to_variable_map = { name = cmm key = scope:setting value = 42 }

# CORRECT — remove first, then add
remove_from_variable_map = { name = cmm key = scope:setting }
add_to_variable_map = { name = cmm key = scope:setting value = 42 }
```

**Critical ordering rule**: If you need to READ the current value before writing, do the read BEFORE the remove:
```
# Read FIRST (entry still exists), THEN remove, THEN add
if = {
    limit = { "variable_map(cmm|scope:setting)" >= 1 }
    remove_from_variable_map = { name = cmm key = scope:setting }
    add_to_variable_map = { name = cmm key = scope:setting value = 0 }
}
else = {
    remove_from_variable_map = { name = cmm key = scope:setting }
    add_to_variable_map = { name = cmm key = scope:setting value = 1 }
}
```

**Where this applies**:
- **ALL runtime value changes** — since `add_to_variable_map` never updates (tests 22-23 FAIL), every write to an existing map entry must use remove-before-add. This includes:
  - Auto-apply scripted GUIs (Phase 3) using `scope:setting` keys
  - Runtime effects using `flag:` keys (Phase 2 toggle/dropdown/numeric/slider)
  - List field runtime effects (Phase 5) using `flag:` keys
  - `cmm_quantize_slider_setting` and any other effects that change existing values
- **Registration is safe without remove-before-add** — initial writes use `add_to_variable_map` to a key that doesn't exist yet, which is the one case where the command works correctly. Idempotent re-registration is also safe because the no-op behavior means the original value is preserved.

### Bug 2: `$macro$` Parameters Do Not Expand Inside Quoted Strings

Paradox script macros (`$param$`) are expanded at compile time, but the `"variable_map(...)"` quoted scope link syntax is parsed as a raw string. Macros inside quotes are NOT expanded — they become literal characters.

```
# WRONG — $setting$ is NOT expanded, the engine sees literal "$setting$":
"variable_map(cmm|flag:$setting$)"

# CORRECT — save to a local variable first, reference inside quotes with local_var:
set_local_variable = { name = cmm_tmp value = flag:$setting$ }
"variable_map(cmm|local_var:cmm_tmp)"
```

This applies to BOTH the map name and key positions in the quoted scope link. Since the map name position only accepts literal strings (not `var:` or `scope:`), you **cannot** use macros in map names at all. This means per-field variable maps with names like `$setting$_field_$slot$` are impossible to read via quoted scope links. Store field values in the unified `cmm` map with compound flag keys instead: `flag:$setting$_item_$item$_f$slot$`.

**However**, macros DO expand in command names and unquoted positions. This is why the scope parameterization trick (`$s$variable_map` → `global_variable_map`) works for commands but not inside quoted scope link strings.

### Bug 3: `var:` vs `local_var:` — Different Namespaces

`set_local_variable` creates a **local** variable. `set_variable` creates a **scope** variable. These are separate namespaces with separate accessors:

| Set with | Read with (unquoted) | Read with (inside quotes) |
|----------|---------------------|--------------------------|
| `set_local_variable` | `local_var:X` | `local_var:X` |
| `set_variable` | `var:X` | `var:X` |

Using `var:X` to read a local variable silently returns nothing/empty scope. This causes cascading failures where variable map lookups appear to fail but the real problem is the key resolution.

**Confirmed**: Using `set_local_variable` + `var:X` inside quoted strings caused all "Failed to fetch key for 'cmm' map due to not being set" runtime errors. The fix is to use matching accessors: `set_local_variable` + `local_var:X`, or `set_variable` + `var:X`.

**`local_var:` works inside quoted scope link strings** — confirmed via engine tests 20-21 (both PASS). Example:
```
set_local_variable = { name = cmm_tmp_flag value = flag:$setting$ }
"variable_map(cmm|local_var:cmm_tmp_flag)" >= 1
```

**Recommendation**: Prefer `set_local_variable` + `local_var:` for temporary variables used inside quoted scope links. Local variables don't pollute the country scope, don't persist after the effect completes, and don't need cleanup with `remove_variable`. Use `set_variable` + `var:` only when the value needs to persist beyond the current effect execution.

### Bug 5: UTF-8 BOM Required for Script Files

EU5 requires UTF-8 BOM encoding for `.yml` localization files (won't load without it) AND `.txt` script files (logs warning "should be in utf8-bom encoding" and may cause subtle issues). All files the framework creates or modifies should have UTF-8 BOM. When creating files programmatically, use `utf-8-sig` encoding (Python) or prepend the BOM bytes `EF BB BF` manually.

### Bug 6: `is_key_in_variable_map` Uses `target =`, Not `key =`

The trigger syntax for checking map membership is:
```
is_key_in_variable_map = { name = map_name target = flag:key_name }
```
NOT `key = flag:key_name`. The parameter is called `target`, not `key`. Similarly for `is_key_in_global_variable_map`. Getting this wrong causes a parse error. Note also that `has_variable_map_value` is NOT a valid trigger — the correct name is `is_value_in_variable_map`.

### Bug 7: Map Name Position Is Strictly Literal

In `"variable_map(MAP_NAME|KEY)"`, the MAP_NAME position:
- Does NOT expand `$macro$` parameters — confirmed by startup parse errors showing literal `$` characters
- Does NOT accept `local_var:` references — confirmed by engine test 24 (FAIL)
- Does NOT accept `var:` references — confirmed by engine test 25 (FAIL)

The map name must be a literal string. There is no way to dynamically reference a map by name in quoted scope links.

**Confirmed consequence**: Per-field variable maps with macro-containing names like `$setting$_field_$slot$` cannot be read via quoted scope links. All field values must go into the single `cmm` map with compound flag keys instead (e.g., `flag:$setting$_item_$item$_f$slot$`).

### Bug 8: `on_game_start` Has Empty Scope

`on_game_start` fires with no scope. `set_variable` (country-scoped) cannot be used in `on_game_start` effects. Use `add_to_global_variable_map` for global state, or defer country-scoped initialization to the first scripted GUI call.

### Scripted GUI Constraints (Confirmed via debugging)

These are hard-won lessons about what works and doesn't work inside scripted GUI `effect = {}` blocks.

1. **`scope = country` and `saved_scopes = { setting }` are BOTH required** for scripted GUIs that receive scopes via `AddScope`. Without `saved_scopes`, `scope:setting` cannot be resolved in the effect block. Without `scope = country`, the effect runs without a proper country scope for `add_to_variable_map`.

2. **`add_to_variable_map` (country scope) works** from scripted GUI effect blocks with the above declarations. Confirmed via engine test.

3. **`add_to_global_variable_map` from scripted GUIs**: During initial implementation, global map writes appeared to silently fail. This was later diagnosed as Bug 1 (missing remove-before-add workaround). The subsequent version confirmed that once remove-before-add is applied, both country-scope AND global-scope variable map writes work from scripted GUIs. **Always apply remove-before-add for writes that update existing entries.**

4. **`set_variable`, `set_global_variable` always work** from scripted GUI context — use these for debug markers when investigating issues.

5. **The `CMMExecuteAutoApply` GUI macro must pass scope correctly**:
   ```
   GetScriptedGui(GuiName).Execute(GuiScope.SetRoot(GetPlayer.MakeScope).AddScope('setting', MakeScopeFlag(SettingKey)).End)
   ```
   `MakeScopeFlag(SettingKey)` creates a flag scope from a string. `AddScope('setting', ...)` makes it available as `scope:setting` in the effect.

### `GetMapKeys` / `Scope.GetMapKeys()` Order Is Engine-Internal

`Scope.GetMapKeys('map_name')` returns keys as a GUI datamodel, but the iteration order is determined by an internal engine ordering (hash or flag-ID based). It is NOT insertion order, and remove+re-add does NOT change the position.

**Consequence**: `GetMapKeys` cannot be used for user-controlled ordering (e.g. list reorder). Variable lists remain the only way to maintain arbitrary ordering in GUI datamodels.

### Map Pre-Initialization Timing

`cmm_init_variable_maps` must run before ANY `"variable_map(...)"` quoted scope link access. The quoted scope link errors hard on nonexistent maps (unlike `is_key_in_variable_map` which returns false gracefully). This means:

- Call init at the start of EVERY public registration function, not just in a central on_action
- The example mod's on_action may fire independently and before the framework's on_action
- The scripted GUI re-registration path (menu open) also needs maps to exist
- The init is idempotent — `add_to_variable_map` with an existing key is a silent no-op (confirmed by engine tests 22-23)

### Warning Suppression Patterns

To suppress "variable X is set but never used" warnings for local variables used inside quoted strings (which the validator can't trace):
```
if = {
    limit = {
        always = no
        exists = local_var:cmm_tmp_flag
        exists = local_var:cmm_tmp_fk
    }
}
```

Place this in a scripted effect that IS called (not in an unused effect). The validator message "Setting it in an unused scripted trigger or effect does not count" is misleading — the `always = no` + `exists` pattern DOES work from dead code blocks within used effects.

For "variable X is used but never set" warnings (variables set at runtime via conditional paths or `add_to_variable_list`), use a dead-branch `set_variable` in the same function that `exists`-references them:
```
if = {
    limit = { always = no }
    set_variable = { name = X value = 0 }
}
```

For variable map names "set but never used", use `has_variable_map` / `has_global_variable_map` in a dead branch:
```
if = {
    limit = {
        always = no
        has_variable_map = cmm_type
        has_global_variable_map = cmm
    }
}
```

### GUI Widget Reference

- **Button types**: `button_standard` is NOT a valid widget type in EU5. Use `button_regular` (works in the settings panel, confirmed with `minimumsize = { 168 32 }`), `button_main_tab_alt` (used for tab headers), or `card_header_button_01` (used for mod list). `button_wax` is only for the pause menu — it requires `blockoverride "button_texture"` and `using = FrontEndMiddleSectionButton` to render at all. **Do not use `button_wax` outside the pause menu.**
- **`GetScriptedGui(name)` returns nullptr** when the named GUI doesn't exist. This produces `Promote 'GetScriptedGui' returned nullptr` in the error log. The `CMMSettingRowVisible` visibility macro must ensure onclick handlers never call nonexistent GUIs — make settings visible based on registration (`cmm_type` map has value > 0), not on `_on_changed` GUI existence.
- **`GetVariableFromVariableMap(...).GetValue` returns `CFixedPoint`**. You cannot chain `.GetString` on it — this produces `Could not find promote for 'GetValue'` errors. For numeric comparisons use `EqualTo_CFixedPoint` / `GreaterThan_CFixedPoint`. For text display use `ToString_CFixedPoint(...)`.
- **`text` vs `raw_text`**: Use `text` for localized/data-bound strings (supports `[DataBinding]` syntax). Use `raw_text` only for literal strings that should bypass localization.

---

## Phase 0: Engine Validation Test Mod — COMPLETE

**Status**: All 25 tests complete. The test mod exists at `submods/cmf-engine-test/` and is standalone with no CMF dependency.

**IMPORTANT**: Run Country Tests FIRST, then Global Tests. Tests 11-15 and 20 depend on data seeded by the country suite. Running global tests alone produces false positives for tests 12-15.

**Full results** (country first, then global):
| Tests | Result | What it proves |
|-------|--------|---------------|
| 1-3 | PASS | scope:setting works as map key for fresh writes, reads, and arithmetic |
| 4-9 | PASS | Global map writes/reads work from scripted GUI context |
| 10 | FAIL | Global writes don't leak to country scope (expected FAIL) |
| 11 | PASS | Cross-context reads work (flag:-written, scope:-read) |
| 12-13 | FAIL | Updating existing entry with scope:setting is a no-op |
| 14 | FAIL | var: intermediary also can't update |
| 15 | FAIL | Failed update didn't create a second entry — complete no-op |
| 16 | PASS | scope:setting == flag:engine_test_key_a in comparisons |
| 17 | PASS | remove_from_map with scope:setting removes flag:-created entry |
| 18-19 | PASS | Remove-then-add workaround works (global + country) |
| 20-21 | PASS | local_var: works as key in quoted scope links (country + global) |
| 22-23 | FAIL | flag:→flag: same-key update fails — add_to NEVER updates |
| 24-25 | FAIL | Map name position doesn't accept local_var: or var: — must be literal |

---

## Phase 1: Metadata Variable Maps + Explicit Type

**Files:**
- `in_game/common/scripted_effects/cmm_core_effects.txt` (add `cmm_init_variable_maps`)
- `in_game/common/scripted_effects/cmm_core_bool_setting_effects.txt`
- `in_game/common/scripted_effects/cmm_core_dropdown_setting_effects.txt`
- `in_game/common/scripted_effects/cmm_core_numeric_setting_effects.txt`
- `in_game/common/scripted_effects/cmm_core_slider_setting_effects.txt`
- `in_game/common/scripted_effects/cmm_core_text_setting_effects.txt`
- `in_game/common/scripted_effects/cmm_core_button_setting_effects.txt`
- `in_game/common/scripted_effects/cmm_core_list_setting_effects.txt`
- `in_game/common/scripted_effects/cmm_core_list_setting_init_effects.txt` (update suppression blocks)
- `in_game/common/scripted_effects/cmm_core_alias_effects.txt`
- `loading_screen/data_binding/cmm_macros_settings.txt`
- `loading_screen/data_binding/cmm_macros.txt`
- `loading_screen/data_binding/cmm_macros_list.txt`
- `in_game/gui/cmm/cmm_components/cmm_slider_setting.gui` (scrollbar min/max/step + hardcode visual step count to 101)
- `in_game/gui/cmm/cmm_components/cmm_numeric_setting.gui` (tooltip min/max range display)
- `in_game/gui/cmm/cmm_components/cmm_list_setting.gui` (list last index)

**New country-scoped variable maps** (set during registration):

| Map | Key | Value |
|-----|-----|-------|
| `cmm_type` | `flag:mod__setting` | 1=bool, 2=dropdown, 3=numeric, 4=slider, 5=text, 6=button, 7=list |
| `cmm_is_global` | `flag:mod__setting` | 0 or 1 |
| `cmm_default` | `flag:mod__setting` | default value |
| `cmm_min` | `flag:mod__setting` | min bound |
| `cmm_max` | `flag:mod__setting` | max bound |
| `cmm_step` | `flag:mod__setting` | step size |
| `cmm_dropdown_count` | `flag:mod__setting` | option count |
| `cmm_dropdown_last_index` | `flag:mod__setting` | max valid index |
| `cmm_slider_actual_step_count` | `flag:mod__setting` | computed step count |
| `cmm_slider_actual_last_index` | `flag:mod__setting` | step_count - 1 |
| `cmm_text_char_limit` | `flag:mod__setting` | character limit |
| `cmm_text_quote` | `flag:mod__setting` | 0 or 1 |
| `cmm_list_count` | `flag:mod__setting` | item count |
| `cmm_list_is_ordered` | `flag:mod__setting` | 0 or 1 |

**Registration effect changes** (each type file): Replace ALL individual `set_variable` calls for metadata with `add_to_variable_map` calls. Remove the old variables completely — do NOT keep both. Example for bool:
```
# OLD (remove entirely):
set_variable = { name = cmm_setting_is_global_$mod_id$__$setting_id$ value = 0 }
set_variable = { name = cmm_setting_is_slider_$mod_id$__$setting_id$ value = 0 }
set_variable = { name = cmm_setting_is_button_$mod_id$__$setting_id$ value = 0 }

# NEW:
add_to_variable_map = { name = cmm_type key = flag:$mod_id$__$setting_id$ value = 1 }
add_to_variable_map = { name = cmm_is_global key = flag:$mod_id$__$setting_id$ value = 0 }
add_to_variable_map = { name = cmm_default key = flag:$mod_id$__$setting_id$ value = $default_value$ }
```

**Also update suppression blocks**: Remove `exists = var:cmm_setting_is_global_*` etc. from all suppression functions — those variables no longer exist.

**Map pre-initialization**: Variable maps must exist before `is_key_in_variable_map` or `variable_map()` is used. Create a `cmm_init_variable_maps` effect that writes a dummy entry to each map. Include warning suppression for all map names and the `cmm_init` flag inside this effect:
```
cmm_init_variable_maps = {
    add_to_variable_map = { name = cmm key = flag:cmm_init value = 0 }
    add_to_variable_map = { name = cmm_type key = flag:cmm_init value = 0 }
    # ... etc for each map
    add_to_global_variable_map = { name = cmm key = flag:cmm_init value = 0 }

    # Suppress "set but never used" warnings for map names and init flag
    if = {
        limit = {
            always = no
            exists = flag:cmm_init
            has_variable_map = cmm
            has_variable_map = cmm_type
            # ... etc for each map
            has_global_variable_map = cmm
        }
    }
}
```
Call this at the start of every registration effect.

**Runtime effect changes** (toggle, apply_dropdown, step_numeric, etc.): Replace ALL metadata reads. Since macros don't expand inside quotes (Bug 2), save to a local variable first:
```
# OLD:
var:cmm_setting_is_global_$setting$ = 1

# NEW:
set_local_variable = { name = cmm_tmp_flag value = flag:$setting$ }
"variable_map(cmm_is_global|local_var:cmm_tmp_flag)" >= 1
```

**GUI macro changes** (`cmm_macros_settings.txt`):

New macro needed: `CMMMapValue(MapName, SettingKey)` — reads a value from a country-scoped variable map:
```
CMMMapValue(MapName, SettingKey) =
    Player.MakeScope.GetVariableFromVariableMap(MapName, MakeScopeFlag(SettingKey)).GetValue
```

Also `CMMMapInt(MapName, SettingKey) = FixedPointToInt(CMMMapValue(MapName, SettingKey))`.

Replace all type-check macros with direct map reads:
- `CMMSettingIsBool(SettingKey)` → `EqualTo_CFixedPoint(CMMMapValue('cmm_type', SettingKey), '(CFixedPoint)1')`
- `CMMSettingIsDropdown` (type=2), `CMMSettingIsNumeric` (type=3), `CMMSettingIsSlider` (type=4), `CMMSettingIsText` (type=5), `CMMSettingIsButton` (type=6), `CMMSettingIsList` (type=7) — same pattern.
- `CMMSettingIsGlobal` → `CMMValueEqualsOne(CMMMapValue('cmm_is_global', SettingKey))`
- `CMMDropdownOptionCount` → `CMMMapInt('cmm_dropdown_count', SettingKey)`
- `CMMTextSettingCharacterLimit` → `CMMMapInt('cmm_text_char_limit', SettingKey)`
- `CMMTextSettingQuoteText` → `CMMValueEqualsOne(CMMMapValue('cmm_text_quote', SettingKey))`
- `CMMListSettingIsOrdered` → `CMMValueEqualsOne(CMMMapValue('cmm_list_is_ordered', SettingKey))`

Add `CMMSettingIsRegistered(SettingKey)` → `GreaterThan_CFixedPoint(CMMMapValue('cmm_type', SettingKey), '(CFixedPoint)0')` (used in Phase 3 visibility).

**⚠️ SLIDER GUI — MUST update in this phase**: The scrollbar widget in `cmm_slider_setting.gui` has `min`, `max`, and `step` properties. These MUST be updated from `CMMMetadataValue('cmm_setting_min_', ...)` to `CMMMapValue('cmm_min', ...)`. If you forget this, the scrollbar gets min=0, max=0 and the handle is permanently stuck at position 0. The text value display will still work (it reads from the `cmm` value map via `CMMSettingValue`), making this a confusing bug where "the value changes but the slider doesn't move."

---

## Phase 2: Setting Values in Variable Maps

**Files:**
- All registration effect files (same as Phase 1)
- All runtime effect files (toggle, apply_dropdown, step_numeric, quantize_slider, etc.)
- `loading_screen/data_binding/cmm_macros_settings.txt`
- `in_game/common/scripted_effects/cmm_core_alias_effects.txt`

**Value maps:**
- Country-scoped map named `cmm`: key = `flag:mod__setting`, value = setting value
- Global-scoped map named `cmm`: key = `flag:mod__setting`, value = setting value (via `add_to_global_variable_map`)

**Registration changes**: Replace `set_variable`/`set_global_variable` for initial value with map writes:
```
# OLD:
if = {
    limit = { NOT = { has_variable = $mod_id$__$setting_id$ } }
    set_variable = { name = $mod_id$__$setting_id$ value = $default_value$ }
}

# NEW:
if = {
    limit = { NOT = { is_key_in_variable_map = { name = cmm target = flag:$mod_id$__$setting_id$ } } }
    add_to_variable_map = { name = cmm key = flag:$mod_id$__$setting_id$ value = $default_value$ }
}
```

For clamping existing values (dropdown range, numeric bounds), read from the map, then use remove-before-add if the value needs correction.

**Runtime effect changes**: All value reads/writes change to map operations. Since `add_to_variable_map` never updates (Bug 1, tests 22-23), every value change MUST use remove-before-add:
```
# OLD (cmm_toggle_bool_setting):
if = { limit = { var:$setting$ = 1 }
    set_variable = { name = $setting$ value = 0 }
}

# NEW — must use remove-before-add since add_to never updates:
set_local_variable = { name = cmm_tmp_flag value = flag:$setting$ }
if = { limit = { "variable_map(cmm|local_var:cmm_tmp_flag)" >= 1 }
    remove_from_variable_map = { name = cmm key = flag:$setting$ }
    add_to_variable_map = { name = cmm key = flag:$setting$ value = 0 }
}
else = {
    remove_from_variable_map = { name = cmm key = flag:$setting$ }
    add_to_variable_map = { name = cmm key = flag:$setting$ value = 1 }
}
```

For global settings, use `global_variable_map`/`remove_from_global_variable_map`/`add_to_global_variable_map`.

**GUI macro `CMMSettingValue`**: Change to read from map:
```
Select_CFixedPoint(CMMSettingIsGlobal(SettingKey),
    GetVariableFromGlobalVariableMap('cmm', MakeScopeFlag(SettingKey)).GetValue,
    Player.MakeScope.GetVariableFromVariableMap('cmm', MakeScopeFlag(SettingKey)).GetValue)
```

**`CMMCanEditSetting`**: Update `GetGlobalVariable('cmm_core__enable_host_only_tools')` to `GetVariableFromGlobalVariableMap('cmm', MakeScopeFlag('cmm_core__enable_host_only_tools')).GetValue`.

**Alias effects** (`cmm_core_alias_effects.txt`): `cmm_sync_setting_alias` and `cmm_sync_dropdown_option_alias` read values from maps.

---

## Phase 3: Auto-Apply Scripted GUIs

**New file:** `in_game/common/scripted_guis/cmm_core_auto_apply_scripted_gui.txt`

**New scripted GUIs** (all receive `scope:setting` via AddScope):

- `cmm_auto_toggle_bool`: Read value from `cmm` map via `scope:setting` key, flip 0↔1, write back. Branch global/local via `cmm_is_global` map.
- `cmm_auto_apply_dropdown`: Read `cmm_dropdown_index_to_apply` marker, clamp to `cmm_dropdown_last_index` map, write to `cmm` value map. Clear marker.
- `cmm_auto_apply_numeric`: Delegates to `cmm_auto_apply_numeric_from_scope` scripted effect.
- `cmm_auto_apply_slider`: Read `cmm_slider_index_to_apply`, compute value from visual index using `cmm_slider_actual_last_index`/`cmm_min`/`cmm_step` maps, write to `cmm` value map. Clear markers. Falls through to `cmm_auto_apply_numeric_from_scope` for +/- button clicks.

**Shared numeric effect**: `cmm_auto_apply_numeric_from_scope` — a scripted EFFECT (not GUI) that both numeric and slider auto-apply GUIs call via `cmm_auto_apply_numeric_from_scope = yes`. Uses `scope:setting` directly in map reads/writes. Handles both `cmm_numeric_step_delta_to_apply` (delta) and `cmm_numeric_change_to_apply` (step/jump) markers.

**Every auto-apply GUI fires `cmm_on_setting_changed`**: ALL six auto-apply GUIs (bool, dropdown, numeric, slider, button, and the numeric-from-scope shared effect) must include the on_action fire at the end of their effect block. This is not optional — it's how mod authors receive callbacks.

**⚠️ CRITICAL: Apply Bug 1 workaround to EVERY map write in auto-apply**. Registration writes entries with `flag:` keys. Auto-apply updates them with `scope:setting` keys. Without the remove-before-add pattern, all updates silently fail and settings appear frozen.

**Slider visual index**: The visual slider always has 101 steps (indices 0-100). The visual last index is always `100`. In the auto-apply slider, hardcode `100` as the divisor instead of reading a per-setting variable — this avoids needing to construct a variable name from `scope:setting`.

**Pattern for auto-apply bool toggle**:
```
cmm_auto_toggle_bool = {
    scope = country
    saved_scopes = { setting }
    effect = {
        if = {
            limit = { "variable_map(cmm_is_global|scope:setting)" >= 1 }
            if = {
                limit = { "global_variable_map(cmm|scope:setting)" >= 1 }
                remove_from_global_variable_map = { name = cmm key = scope:setting }
                add_to_global_variable_map = { name = cmm key = scope:setting value = 0 }
            }
            else = {
                remove_from_global_variable_map = { name = cmm key = scope:setting }
                add_to_global_variable_map = { name = cmm key = scope:setting value = 1 }
            }
        }
        else = {
            if = {
                limit = { "variable_map(cmm|scope:setting)" >= 1 }
                remove_from_variable_map = { name = cmm key = scope:setting }
                add_to_variable_map = { name = cmm key = scope:setting value = 0 }
            }
            else = {
                remove_from_variable_map = { name = cmm key = scope:setting }
                add_to_variable_map = { name = cmm key = scope:setting value = 1 }
            }
        }
    }
}
```

**Post-change callback via on_action** (confirmed working via testing):

Every auto-apply scripted GUI fires `cmm_on_setting_changed` after changing the value. This is the mechanism for optional mod-author callbacks — same pattern as `cmm_on_mod_registration`.

```
# At the end of each auto-apply effect block:
set_variable = { name = cmm_changed_setting value = scope:setting }
trigger_event_silently = {
    on_action = cmm_on_setting_changed
}
remove_variable = cmm_changed_setting
```

Add `cmm_on_setting_changed` to `cmm_on_action.txt`:
```
cmm_on_setting_changed = {
    on_actions = { }
}
```

Mod authors hook in exactly like registration:
```
# In the mod's on_action file:
cmm_on_setting_changed = {
    on_actions = { my_mod_on_setting_changed }
}

my_mod_on_setting_changed = {
    effect = {
        if = {
            limit = { var:cmm_changed_setting = flag:my_mod__my_setting }
            # custom side effects here
        }
    }
}
```

This works for global settings too — the on_action fires on the country that clicked (the host for global settings), which is correct.

**Buttons also use auto-apply + on_action**: Create `cmm_auto_apply_button` which only fires the on_action (no value change — buttons have no stored value). This unifies ALL setting types under one callback mechanism. The old `CMMExecuteSettingChanged` / `_on_changed` pattern is eliminated entirely.

```
cmm_auto_apply_button = {
    scope = country
    saved_scopes = { setting }
    effect = {
        set_variable = { name = cmm_changed_setting value = scope:setting }
        trigger_event_silently = {
            on_action = cmm_on_setting_changed
        }
        remove_variable = cmm_changed_setting
    }
}
```

Button onclick becomes:
```
onclick = "[CMMExecuteAutoApply('cmm_auto_apply_button', Scope.GetFlagName)]"
```

**New macros** (`cmm_macros.txt`):
```
CMMExecuteAutoApply(GuiName, SettingKey) =
    "GetScriptedGui(GuiName).Execute(GuiScope
        .SetRoot(GetPlayer.MakeScope)
        .AddScope('setting', MakeScopeFlag(SettingKey))
        .End)"
```

**GUI file changes** — Update onclick handlers in each component:

`cmm_setting_row.gui` (checkbox):
```
onclick = "[CMMExecuteAutoApply('cmm_auto_toggle_bool', Scope.GetFlagName)]"
```

`cmm_setting_row.gui` (button):
```
onclick = "[CMMExecuteAutoApply('cmm_auto_apply_button', Scope.GetFlagName)]"
```

`cmm_dropdown_setting.gui` (onselectionchanged):
```
onselectionchanged = "[CMMExecuteAutoApply('cmm_auto_apply_dropdown', Scope.GetFlagName)]"
```

`cmm_numeric_setting.gui` (all `CMMExecuteSettingChanged` occurrences):
```
# Replace CMMExecuteSettingChanged with CMMExecuteAutoApply('cmm_auto_apply_numeric', ...)
```

`cmm_slider_setting.gui` (all `CMMExecuteSettingChanged` occurrences):
```
# Replace CMMExecuteSettingChanged with CMMExecuteAutoApply('cmm_auto_apply_slider', ...)
```

Text settings stay unchanged — they use console commands.

**List settings keep `_on_changed`** (confirmed via testing — see "Known Pitfalls" for full analysis):

List field clicks go through `CMMExecuteListItemSettingChanged` → `CMMExecuteSettingChanged` → `_on_changed` scripted GUI → `cmm_apply_list_change`. This chain cannot move to auto-apply because the GUI datamodel requires a per-setting variable list (`cmm_list_items_$setting$`) for user-controlled ordering, and variable list operations require the list name as a compile-time literal.

The list `_on_changed` is minimal boilerplate — one line calling `cmm_apply_list_change = { setting = ... }`. Keep `CMMExecuteSettingChanged` and `CMMExecuteListItemSettingChanged` macros for lists.

**Summary of callback mechanism by type:**
| Type | GUI onclick | Callback mechanism |
|------|-----------|-------------------|
| Bool | `CMMExecuteAutoApply('cmm_auto_toggle_bool', ...)` | `cmm_on_setting_changed` on_action |
| Dropdown | `CMMExecuteAutoApply('cmm_auto_apply_dropdown', ...)` | `cmm_on_setting_changed` on_action |
| Numeric | `CMMExecuteAutoApply('cmm_auto_apply_numeric', ...)` | `cmm_on_setting_changed` on_action |
| Slider | `CMMExecuteAutoApply('cmm_auto_apply_slider', ...)` | `cmm_on_setting_changed` on_action |
| Button | `CMMExecuteAutoApply('cmm_auto_apply_button', ...)` | `cmm_on_setting_changed` on_action |
| Text | Console commands (unchanged) | Console commands |
| List | `CMMExecuteListItemSettingChanged(...)` | `_on_changed` scripted GUI (required) |

**Visibility change** (`CMMSettingRowVisible` in `cmm_macros_settings.txt`):

Since buttons now use auto-apply too, ALL registered settings are visible by default. `_on_changed` is only needed for conditional visibility (`is_shown`) and list callbacks:
```
And(
    CMMMatchesSelectedModAndTab(OwnerMod, OwnerTab),
    Or(
        CMMSettingIsRegistered(SettingKey),
        CMMGuiIsShown(Concatenate(SettingKey, '_on_changed'))
    )
)
```

---

## Phase 4: Global List Settings

**Files:**
- `in_game/common/scripted_effects/cmm_core_list_setting_effects.txt` (registration)
- `in_game/common/scripted_effects/cmm_core_list_setting_init_effects.txt` (item init)
- `in_game/common/scripted_effects/cmm_core_list_setting_runtime_effects.txt` (runtime)

This phase has TWO distinct parts: registration (compile-time scope) and runtime (data-driven scope). They use different techniques.

### Part A: Registration — `$vt$` macro composition (compile-time)

Add `cmm_register_global_settings_list` alongside the existing `cmm_register_settings_list`. Also add global variants of `cmm_begin_settings_list` / `cmm_finish_settings_list` / `cmm_register_settings_list_from_list`.

Use macro command-name composition with `$vt$` (see "Implementation Rules" above). The registration wrappers pass `vt = variable` or `vt = global_variable`, and internal functions compose commands like `add_to_$vt$_list`, `clear_$vt$_list`:

```
cmm_register_settings_list = {
    cmm_register_list_setting_internal = { ... is_global = 0 vt = variable }
}
cmm_register_global_settings_list = {
    cmm_register_list_setting_internal = { ... is_global = 1 vt = global_variable }
}

# Internal — zero branching, zero duplication:
cmm_add_list_item_identity = {
    add_to_$vt$_list = {
        name = cmm_list_items_$mod_id$__$setting_id$
        target = flag:$mod_id$__$setting_id$_item_$item$
    }
}
cmm_initialize_list_setting_item_list = {
    clear_$vt$_list = cmm_list_items_$mod_id$__$setting_id$
    # ... 20-case switch calling cmm_add_list_item_identity with vt = $vt$ ...
}
```

The `cmm_begin_global_settings_list` / `cmm_finish_global_settings_list` are separate public API functions (not parameterized) that hardcode `clear_global_variable_list` etc. for the dynamic list path.

### Part B: Runtime — `var:cmm_tmp_is_global_list` branching (data-driven)

`cmm_apply_list_change` determines scope from the `cmm_is_global` map at entry and stores it in a country-scoped temp variable. All sub-effects check this variable to branch.

```
cmm_apply_list_change = {
    set_local_variable = { name = cmm_tmp_flag value = flag:$setting$ }
    set_variable = { name = cmm_tmp_is_global_list value = "variable_map(cmm_is_global|local_var:cmm_tmp_flag)" }
    # ... existing dispatch logic (unchanged) ...
    remove_variable = cmm_tmp_is_global_list
}
```

This avoids threading a macro parameter through every function in the dispatch chain. Sub-effects just check `var:cmm_tmp_is_global_list`.

**Functions that need scope branching:**

1. **List iteration** (`cmm_reorder_list_setting`, `cmm_list_apply_dispatch_to_marked_position`, `cmm_list_apply_dispatch_to_all_items`, `cmm_for_each_list_item`): Branch `every_in_list` / `every_in_global_list` on the temp variable. Note: `cmm_for_each_list_item` is called outside of `cmm_apply_list_change`, so it reads `cmm_is_global` from the map directly instead of using the temp variable.

2. **List modification** (`cmm_reorder_list_setting`): Branch `clear_variable_list` / `clear_global_variable_list` and `add_to_variable_list` / `add_to_global_variable_list` for the actual item list. The scratch temp list (`cmm_list_rebuild_temp`) always uses country scope.

3. **Field value reads** (leaf functions): Cannot be parameterized because `"variable_map(...)"` / `"global_variable_map(...)"` are quoted scope links (Bug 2). Read into a local variable via if/else:
```
set_local_variable = { name = cmm_tmp_fk value = flag:$setting$_item_$item$_f$slot$ }
if = {
    limit = { var:cmm_tmp_is_global_list >= 1 }
    set_local_variable = { name = cmm_field_val value = "global_variable_map(cmm|local_var:cmm_tmp_fk)" }
}
else = {
    set_local_variable = { name = cmm_field_val value = "variable_map(cmm|local_var:cmm_tmp_fk)" }
}
# Then use local_var:cmm_field_val for logic
```

4. **Field value writes** (leaf functions): Branch `remove_from_variable_map` / `remove_from_global_variable_map` and `add_to_variable_map` / `add_to_global_variable_map`.

**Leaf functions requiring read/write branching:**
- `cmm_list_prepare_bool_field_value_from_slot_item` — 1 read
- `cmm_list_prepare_numeric_field_value_from_slot_item` — 1 read
- `cmm_list_apply_numeric_field_slot` — 1 read + 3 write points
- `cmm_list_apply_field_slot_at_item` — 4 reads + 6 writes (bool toggle, dropdown forward/backward/select, bulk apply)

**Functions that do NOT need changes** (pure dispatch, no list/map ops):
- `cmm_list_dispatch_saved_item_action`, `cmm_list_dispatch_item_action`
- `cmm_list_prepare_*_from_item`, `cmm_list_apply_*_at_item` (slot dispatch wrappers)
- `cmm_list_apply_field_value_to_all_items`

**What stays country-scoped regardless:**
- Item identity metadata (`cmm_list_item_owner_setting_*`, `*_name`) — identical for all players, set during registration
- Item value scopes (`*_item_*_value` variable lists) — set during registration, same for all players
- Field type/bounds metadata (`cmm_list_field_*_type_*`, `*_min_*`, `*_max_*`) — per-slot constants

---

## Phase 5: Variable Maps for List Field Storage

**Files:**
- `in_game/common/scripted_effects/cmm_core_list_setting_effects.txt` (field init)
- `in_game/common/scripted_effects/cmm_core_list_setting_init_effects.txt` (per-item init)
- `in_game/common/scripted_effects/cmm_core_list_setting_runtime_effects.txt` (field read/write)
- `loading_screen/data_binding/cmm_macros_list.txt` (field value GUI macros)
- `in_game/gui/cmm/cmm_components/cmm_list_setting_fields.gui`

Replace per-item field variables with maps:
```
# OLD: var:mod__setting_item_1_field_1
# NEW: variable_map(cmm|flag:mod__setting_item_1_f1)
```

Note the key format: `_field_` in variable names becomes `_f` in map keys.

**Field init** (per-item init functions): Replace `set_variable`/`has_variable` with map operations. Use `$vt$` from Phase 4 to compose the correct map commands (`is_key_in_$vt$_map`, `add_to_$vt$_map`, `remove_from_$vt$_map`):
```
# OLD:
if = { limit = { NOT = { has_variable = $mod_id$__$setting_id$_item_$item$_field_$slot$ } }
    set_variable = { name = $mod_id$__$setting_id$_item_$item$_field_$slot$ value = $default_value$ }
}

# NEW:
if = { limit = { NOT = { is_key_in_$vt$_map = { name = cmm target = flag:$mod_id$__$setting_id$_item_$item$_f$slot$ } } }
    add_to_$vt$_map = { name = cmm key = flag:$mod_id$__$setting_id$_item_$item$_f$slot$ value = $default_value$ }
}
```

For clamping, use `set_local_variable = { name = cmm_tmp_fk value = flag:$mod_id$__$setting_id$_item_$item$_f$slot$ }` then read via `"variable_map(cmm|local_var:cmm_tmp_fk)"` (country) or `"global_variable_map(cmm|local_var:cmm_tmp_fk)"` (global — branch on `$is_global$`), and update with remove-before-add using `$vt$` commands.

**Field metadata** (type, min, max, step, dropdown_last_index per slot): These stay as country-scoped variables since they're the same for all players and don't change at runtime.

**⚠️ CRITICAL: Apply Bug 1 workaround to ALL runtime list field writes**.

**Ordering rule for bool toggle**: Read BEFORE remove:
```
set_local_variable = { name = cmm_tmp_fk value = flag:$setting$_item_$item$_f$slot$ }
if = {
    limit = { "variable_map(cmm|local_var:cmm_tmp_fk)" >= 1 }
    remove_from_variable_map = { name = cmm key = flag:$setting$_item_$item$_f$slot$ }
    add_to_variable_map = { name = cmm key = flag:$setting$_item_$item$_f$slot$ value = 0 }
}
else = {
    remove_from_variable_map = { name = cmm key = flag:$setting$_item_$item$_f$slot$ }
    add_to_variable_map = { name = cmm key = flag:$setting$_item_$item$_f$slot$ value = 1 }
}
```

**GUI macros** (`cmm_macros_list.txt`):
- `CMMListItemFieldVar(ItemKey, SlotKey)` → `Player.MakeScope.GetVariableFromVariableMap('cmm', MakeScopeFlag(Concatenate(ItemKey, Concatenate('_f', SlotKey))))` (returns map entry, NOT `.GetValue`)
- `CMMListItemFieldValue(ItemKey, SlotKey)` → `CMMListItemFieldVar(ItemKey, SlotKey).GetValue` (chains `.GetValue`)

**⚠️ CRITICAL GUI BUG: List field 0-based vs 1-based index mismatch**

`DataModelRepeatedItem` produces 0-based widget indices but field slots are 1-based. Every GUI lookup that uses the widget index as a slot key must convert with `CMMWidgetIndexToOrdinal(PdxGuiWidget.GetIndexInDataModel)`.

Places that need the conversion in `cmm_list_setting_fields.gui`:
1. **Header field name**: `CMMListFieldMetadataFlag(Key, ToString_int32(CMMWidgetIndexToOrdinal(PdxGuiWidget.GetIndexInDataModel)), '_name_')`
2. **Cell type visibility** (bool/numeric/dropdown): `CMMListFieldIsBool(Key, ToString_int32(CMMWidgetIndexToOrdinal(...)))`
3. **Bool checked state**: `CMMListItemFieldValue(Key, ToString_int32(CMMWidgetIndexToOrdinal(...)))`
4. **Numeric display value**: `CMMListItemFieldValue(Key, ToString_int32(CMMWidgetIndexToOrdinal(...)))`

Places that are ALREADY correct and should NOT be changed:
- **Hover slot ordinal**: `onmousehierarchyenter` already uses `CMMWidgetIndexToOrdinal`
- **Hardcoded dropdown variants**: The 0→1 mapping is intentional
- **Dropdown option indices inside `item` blocks**: These are dropdown OPTION indices (0-based), not field slot indices
- **Shift-click apply-all button**: Already uses `CMMWidgetIndexToOrdinal`

---

## Phase 6: Reset to Defaults

**New file:** `in_game/common/scripted_effects/cmm_core_reset_effects.txt`

```
cmm_reset_to_defaults = {
    every_key_in_variable_map = {
        variable = cmm_default
        # 'this' is the setting flag key
        # Read default from cmm_default map
        # Check cmm_is_global map
        # Write default to cmm value map (global or local)
        # MUST use remove-before-add workaround
    }
}
```

**New scripted GUI:** `CMM_ResetToDefaults` in `cmm_settings_scripted_gui.txt`

**GUI change:** Add "Reset to Defaults" button in `cmm_settings_pane.gui`. Use `button_regular` with `minimumsize = { 168 32 }` — NOT `button_wax` (see GUI Widget Reference).

**Localization:** Add to `main_menu/localization/english/cmm_l_english.yml`:
```
 CMM_RESET_TO_DEFAULTS: "Reset to Defaults"
 CMM_RESET_TO_DEFAULTS_TOOLTIP: "Reset all settings for all mods to their registered default values."
```

---

## Phase 7: Dropdown Option Tooltips

**Files:**
- `in_game/gui/cmm/cmm_components/cmm_dropdown_setting.gui`
- `loading_screen/data_binding/cmm_macros.txt`

Add tooltip to each dropdown `item` widget's `button_dropdown`:
```
tooltip = "[CMMOptionDesc(Scope.GetFlagName, CMMWidgetIndexToOrdinal(PdxGuiWidget.GetIndexInDataModel))]"
tooltip_enabled = "[CMMHasOptionDesc(Scope.GetFlagName, CMMWidgetIndexToOrdinal(PdxGuiWidget.GetIndexInDataModel))]"
tooltipwidget = { BasicFunctionalTooltip = {} }
```

New macros in `cmm_macros.txt`:
- `CMMOptionDesc(OptionRoot, Index)` — resolves `<root>_option_<N>_desc` localization
- `CMMHasOptionDesc(OptionRoot, Index)` — checks if desc localization key exists (same `Not(EqualTo_string(...))` pattern as `CMMHasLocalizedSuffixText`)

Localization key pattern: `<mod_id>__<setting_id>_option_<N>_desc`

---

## Phase 8: Consistent Naming

**Files:**
- `in_game/common/scripted_effects/cmf_alert_effects.txt`
- `in_game/common/scripted_triggers/cmf_alert_triggers.txt`
- `submods/cmf-example-mod/` (all references)
- `in_game/common/scripted_guis/cmf_sgui_alerts.txt`

Renames:
| Old | New |
|-----|-----|
| `cmf_show_alert` | `cmf_add_alert` |
| `cmf_remove_alert` | (unchanged) |
| `cmf_is_alert_shown` | `cmf_is_alert_active` |

Search the entire `in_game/` and `submods/` directories for references to the old names and update them all.

**Note on `cmf_action_bar_effects.txt`**: The `every_country` loop syncs global action bar elements to per-country lists. `every_player` does NOT exist in EU5. Keep `every_country` as-is — it's needed because the per-country list `cmf_action_bar_active_elements` is read by the GUI and scripted GUIs.

---

## Phase 9: Example Mod + Documentation

You may change EU5 wiki pages in `docs\wiki`, but do not change the GitHub wiki pages at `cmf-wiki/`, or the `assets\local\CLAUDE.md` file until the user tests and verifies all changes then instructs you to do so.

**Example mod updates:**
- Remove all `_on_changed` scripted GUIs for bool, dropdown, numeric, slider, AND button (both local and global variants) — all use auto-apply + `cmm_on_setting_changed` on_action now
- Keep `_on_changed` for list (still uses `cmm_apply_list_change` with `$setting$` — the one setting type that requires it)
- Keep `_on_changed` for text (console commands)
- Update alert calls to new names (`cmf_add_alert`)
- Add a `cmm_on_setting_changed` on_action hook demonstrating the optional callback pattern:
```
cmm_on_setting_changed = {
    on_actions = { my_mod_on_setting_changed }
}
my_mod_on_setting_changed = {
    effect = {
        if = {
            limit = { var:cmm_changed_setting = flag:my_mod__my_setting }
            # custom side effects
        }
    }
}
```

**Paradox wiki** (`docs/wiki/cmm.wiki`): Update quick-reference snippets.

---

## Dependency Order

```
Phase 0 (Engine Test) ← COMPLETE
    ↓
Phase 1 (Metadata Maps) ← includes slider GUI fix
    ↓
Phase 2 (Value Maps)
    ↓
Phase 3 (Auto-Apply GUIs) ← MOST BUG-PRONE PHASE, see workarounds
    ↓
Phase 4 (Global Lists) ← use macro parameterization
    ↓
Phase 5 (List Field Maps) ← second most bug-prone, see workarounds
    ↓
Phase 6 (Reset to Defaults) ← requires Phase 1 + 2; needs localization
    ↓
Phase 7 (Dropdown Tooltips) ← independent
    ↓
Phase 8 (Consistent Naming) ← independent
    ↓
Phase 9 (Docs + Examples) ← after all others
```

Phases 7 and 8 are independent and can be done at any point, but must still be completed before moving to Phase 9.

## Known Pitfalls (Confirmed via Implementation)

These are issues discovered during actual implementation. They are NOT hypothetical — each one caused real bugs or wasted time.

### Every GUI accessor that reads metadata MUST be updated

When metadata moves from plain variables to maps, **every** GUI expression that reads it must be updated. Search for ALL occurrences of `CMMMetadataValue`, `CMMMetadataInt`, `CMMMetadataIsSet`, `CMMMetadataEqualsOne` in `.gui` files. Any reference to a migrated variable prefix (like `cmm_setting_min_`, `cmm_setting_max_`, `cmm_setting_slider_visual_step_count_`) is a bug — the data no longer exists as a plain variable.

Known locations that need updating (easy to miss):
- `cmm_slider_setting.gui` scrollbar `min`/`max`/`step` properties → `CMMMapValue('cmm_min', ...)`
- `cmm_numeric_setting.gui` tooltip range display → `CMMMapValue('cmm_min', ...)` / `CMMMapValue('cmm_max', ...)`
- `cmm_slider_setting.gui` datamodel count `CMMMetadataInt('cmm_setting_slider_visual_step_count_', ...)` → hardcode `101` (the value never varies per-setting; the auto-apply slider already hardcodes `100` for the divisor)
- `cmm_list_setting.gui` last index `CMMMetadataInt('cmm_setting_list_last_index_', ...)` → `CMMMapInt('cmm_list_last_index', ...)`

References to ownership metadata (`cmm_mod_default_tab_`, `cmm_tab_owner_mod_id_`, `cmm_group_owner_*`, `cmm_setting_owner_*`, `cmm_list_item_column_name_`) are fine — these remain as plain country variables.

### Optional callbacks use `cmm_on_setting_changed` on_action — NOT `_on_changed` scripted GUIs

**Solved**: The old `_on_changed` scripted GUI pattern is replaced by a shared `cmm_on_setting_changed` on_action that fires after every auto-apply. Mod authors hook into it exactly like `cmm_on_mod_registration`. The changed setting's flag key is in `var:cmm_changed_setting`.

This approach was confirmed working via testing. It avoids the `GetScriptedGui` nullptr problem entirely — on_actions with empty `on_actions = { }` are safe no-ops. It unifies ALL setting types (bool, dropdown, numeric, slider, button) under one callback mechanism.

**Consequence**: For bool/dropdown/numeric/slider/button, the `_on_changed` scripted GUI is ONLY used for `is_shown` conditional visibility — NOT for callbacks. Remove `cmm_core__enable_host_only_tools_on_changed` — it's dead code.

**Exception — lists**: List settings still require `_on_changed` scripted GUIs with `cmm_apply_list_change`. This was extensively tested — two alternative approaches were explored and ruled out:

1. **Field key lookup maps** (`cmm_fk1..5` mapping item flag → compound field value key): Confirmed working for single-item field toggles and bulk apply via `every_key_in_variable_map` with owner filtering. The two-step chain (`scope:item` → lookup map → compound key → value map) successfully reads and writes field values without `$setting$`. However, this only solves field VALUE access — not list iteration or ordering.

2. **`GetMapKeys` for GUI datamodel**: Tested whether `Scope.GetMapKeys()` iteration order could be controlled via remove+re-add. Result: **order is engine-internal (hash/flag-ID based), NOT insertion order**. Remove+re-add does not change the position. This means `GetMapKeys` cannot replace variable lists for user-controlled ordering (reorder).

**The irreducible blocker**: The GUI `datamodel` needs a per-setting variable list (`cmm_list_items_$setting$`) for ordered rendering. Variable list operations (`clear_variable_list`, `add_to_variable_list`, `every_in_list`) require the list name as a compile-time literal string. Since the list name contains the setting key, and auto-apply only has `scope:setting` (runtime), lists cannot use auto-apply for reorder operations. The `_on_changed` boilerplate is one line and irreducible.

### Slider visual step count is a constant — don't store it per-setting

The visual slider track is always divided into 101 clickable button slots (indices 0-100). This is the **visual track resolution**, NOT the logical step count. The mapping from visual position to actual value uses the per-setting `cmm_slider_actual_step_count` (which IS variable — e.g. 10 for a 1-10 slider with step 1). The formula is: `actual_value = min + step * round(visual_index * actual_last_index / 100)`.

Since the visual resolution is always 101, the per-setting variables `cmm_setting_slider_visual_step_count_*` (`= 101`) and `cmm_setting_slider_visual_last_index_*` (`= 100`) are redundant. The auto-apply slider already hardcodes `100` as the divisor. Hardcode `101` in the GUI datamodel and remove these per-setting variables.

### Helper extraction reduces code dramatically

The list code has many 20-case switch blocks that repeat identical logic with different item numbers. Extracting a parameterized helper (accepting `$item$` and a `$min_count$` for the guard condition) turns 80+ lines into 20 one-line calls. Apply this pattern to ALL 20-case blocks, not just some:
- `cmm_reinitialize_dynamic_list_item_metadata` ← already done
- `cmm_initialize_list_setting_item_metadata`
- `cmm_initialize_list_setting_item_list`
- `cmm_add_settings_list_item` (20-case switch with per-item init)
- `cmm_add_staged_settings_list_item` (20-case switch)
- `cmm_initialize_list_bool_field_slot` (20-case switch per item)
- `cmm_initialize_list_dropdown_field_slot` (20-case switch per item)
- `cmm_initialize_list_numeric_field_slot` (20-case switch per item)

### Don't implement features halfway

Every phase must be fully complete before moving on. "I'll add the API surface now and implement the runtime later" creates code that compiles but silently does nothing — global lists that appear to work but store everything in country scope. The plan says to do something → do ALL of it, including the runtime, the init, and the GUI.

## Self-Checks (Implementer)

After completing all code phases (1-8), before handing off to the user for testing:

1. Grep `.gui` files for `CMMMetadataValue`, `CMMMetadataInt`, `CMMMetadataIsSet`, `CMMMetadataEqualsOne` — any reference to a migrated variable prefix (like `cmm_setting_min_`, `cmm_setting_max_`, `cmm_setting_slider_visual_step_count_`) is a bug
2. Grep for `CMMExecuteSettingChanged` in GUI files — should only appear in list-related GUI files (`cmm_list_setting.gui`, `cmm_list_setting_fields.gui`), nowhere else
3. Grep for old variable names (`cmm_setting_is_global_`, `cmm_setting_is_slider_`, `cmm_setting_is_button_`) — should not be set or read anywhere
4. Confirm all new variable map names have suppression entries in `cmm_init_variable_maps`
5. Confirm all new GUI text keys have localization entries in `cmm_l_english.yml`

**Phase 3 deliverables** (for user testing):
- Example mod's `_on_changed` GUIs removed for bool/dropdown/numeric/slider/button
- Example mod includes a `cmm_on_setting_changed` on_action hook with a visible side effect (e.g. removing an alert when a toggle is clicked)
- Built-in `cmm_core__enable_host_only_tools_on_changed` removed
- An `_on_changed` with `is_shown = { always = no }` added to one example setting to demonstrate conditional visibility

**Phase 5 deliverables** (for user testing):
- List setting columns display correct headers
- All three field types (bool, numeric, dropdown) render correctly
- List reorder works for ordered lists

## Reference

**Deploy workflow for example mod**: After modifying `submods/cmf-example-mod/`, delete `%USERPROFILE%/Documents/Paradox Interactive/Europa Universalis V/mod/cmf-example-mod/` and replace it with a fresh copy from `submods/cmf-example-mod/`. The framework itself lives at `%USERPROFILE%/Documents/Paradox Interactive/Europa Universalis V/mod/community-mod-framework/` and is edited in-place.

**Error log location**: `%USERPROFILE%/Documents/Paradox Interactive/Europa Universalis V/logs/error.log`.

**Two classes of errors**:
- **Startup errors** (file parse time): `[pdx_persistent_reader.cpp]` "Unknown trigger type", `[jomini_eventtarget.cpp]` "Failed to find valid event target link" — these indicate syntax/reference problems in script files
- **Runtime errors** (during gameplay): `[jomini_script_system.cpp]` "Script system error" — these indicate logic failures like accessing nonexistent maps/keys

Both must be zero for a successful implementation.
