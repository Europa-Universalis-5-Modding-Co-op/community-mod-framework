# Engine Test Results

Date: 2026-06-14

## Country Tests (et_run)

| # | Test | Result |
|---|------|--------|
| 1 | scope:et_setting as variable map key | PASS |
| 2 | variable_map(x \| scope:et_setting) read-back | PASS |
| 3 | Map value to local variable arithmetic | PASS |

**3/3 passed**

## Global Tests (et_run_global)

| # | Test | Result |
|---|------|--------|
| 4 | set_global_variable (baseline) | PASS |
| 5 | Global write + read (hardcoded flag) | PASS |
| 6 | Global write + read (scope:et_setting) | PASS |
| 7 | scope:et_setting == flag:et_key_a ? | PASS |
| 8 | Global write(scope:et_setting) read(hardcoded) | PASS |
| 9 | Read on_action global map (hardcoded) | PASS |
| 10 | Read on_action global map (scope:et_setting) | PASS |
| 11 | Cross-context country map read (flag to scope:et_setting) | PASS |
| 12 | Global write stays in global scope | PASS |
| 13 | flag:->flag: same-key update (country map) | PASS |
| 14 | flag:->flag: same-key update (global map) | PASS |
| 15 | scope:et_setting->scope:et_setting direct overwrite (global) | PASS |
| 16 | Update global map entry (flag: then scope:et_setting) | PASS |
| 17 | Update country map entry (flag: then scope:et_setting) | PASS |
| 18 | Read back update with scope:et_setting (two entries?) | PASS |
| 19 | remove_from_map with scope:et_setting on flag: entry | PASS |
| 20 | Workaround: remove + re-add global map | PASS |
| 21 | Workaround: remove + re-add country map | PASS |
| 22 | scope:et_setting remove + re-add (global) | PASS |
| 23 | Workaround: var: intermediary for update | PASS |
| 24 | local_var: as key in variable_map() quoted string | PASS |
| 25 | local_var: as key in global_variable_map() quoted string | PASS |
| 26 | local_var: in map name position of quoted string | FAIL |
| 27 | var: in map name position of quoted string | FAIL |
| 28 | every_key_in_variable_map iteration count | PASS |
| 29 | random_key_in_variable_map picks an entry | PASS |
| 30 | ordered_key_in_variable_map picks an entry | PASS |
| 31 | ordered_key_in_variable_map full iteration | FAIL |
| 32 | ordered_key_in_variable_map with max | PASS |
| 33 | every_key_in_global_variable_map (variable only) | PASS |
| 34 | ordered_key without max defaults to 1? | PASS |
| 35 | Global map write/read with var: numeric key | PASS |

**29/32 passed**

## Macro Param Tests (et_run_global)

Redesigned 2026-06-30 to fail closed, and confirmed in-game: all three now report
FAIL. The original 2026-06-19 run showed a false-positive PASS on 37/38 (explained
below), which prompted the redesign.

| # | Test | Result |
|---|------|--------|
| 36 | macro param as key in variable_map() quoted string | FAIL |
| 37 | macro param in map name position of quoted string | FAIL |
| 38 | macro param as both map name and key | FAIL |

Engine finding (unchanged): a $PARAM$ macro arg IS substituted inside the quoted
string, but it corrupts the variable_map(...) syntax. The 2026-06-19 load log showed
the mangled triggers:

- 37 "variable_map($MAP$|flag:et_key_a)" became
  "variable_mapet_macro_map$|flag:et_key_a)" (Unknown trigger type): the substituted
  value is there, but the "(" is gone and a stray "$" is left.
- 38 "variable_map($MAP$|flag:$KEY$)" became
  "variable_mapet_macro_map$|flaget_key_a$)" (same load error).

A $PARAM$ in the map-name slot destroys the "(" so the trigger fails to parse.
Originally the read sat directly in the if's limit, so an unparseable trigger left
the limit with no valid condition, read as vacuously true, and set _passed = 1: a
false-positive PASS. The redesign captures the read into a local var (et_macro_result,
init 0) and compares that separately, so only a genuine read of 55 passes. The mangled
set leaves et_macro_result unset rather than 0, so the score check is guarded with
has_local_variable to skip the read when the sentinel is unset (confirm on next run).

Conclusion: $PARAM$ cannot be used inside a quoted variable_map accessor. Use the
set_local_variable round-trip with local_var:/scope: keys instead. Note: it does not
fail silently. The mangled accessor logs a load-time parse error (jomini_eventtarget.cpp);
the "not being set" runtime errors came from the score check reading the cleared sentinel
(now guarded), not from the accessor itself. Reconcile this load-time error with the
global note's "fails silently" wording.

## Summary

**Total: 32/35 passed (3 failed)**

Tests 36-38 (macro params in quoted accessors): $PARAM$ cannot be used inside a quoted
variable_map accessor (all three broken). Redesigned 2026-06-30 to fail closed so they
report FAIL instead of the earlier false-positive PASS; see the Macro Param Tests section.

### Key Findings

**add_to_variable_map NOW updates existing entries (tests 13-18, 23):**
- Writing to the same key twice overwrites: `add_to` acts as "add or update", replacing the prior value.
- Applies to both country and global maps, and regardless of key type (flag:, scope:et_setting).
- Behavior change: on the 2026-03-28 run these tests FAILED (add was "add only", a silent no-op on an existing key), and the var: intermediary update (test 23) also failed. A game patch between 2026-03-28 and 2026-06-14 reversed this. Re-run this suite after any patch before relying on either behavior.
- remove + re-add (tests 19-22) still works, so cmf_change_variable_map remains correct; it is just no longer required to update a value.

**Variable references cannot be used in map name position (tests 26-27):**
- "variable_map(local_var:X|...)" and "variable_map(var:X|...)" do not resolve - the map name must be a literal.
- Variable references DO work in the key position (tests 24-25, and test 35 for a var: numeric key).
- These two also log an unsuppressable "used but never set" for the map-name-slot variable (a dead-branch set, a reached on_action set, and a full cmf_suppress replication all fail); it is left unsuppressed. The set side is a separate, normal "set but never used" because the map-name-slot use does not count as a use: et_map_name (test 26) is read-suppressed in et_suppress_warnings, while et_map_name_v (test 27) avoids it via its remove_variable. Key-slot references (tests 24-25) do not warn.

**ordered_key_in_variable_map defaults to 1 without max (tests 31-32, 34):**
- Without max, the iterator picks exactly one element (test 34 passes with count = 1).
- Test 31 fails because it expects all 3 entries, but only 1 is visited.
- With max = 3, all entries are visited (test 32).
- every_key_in_variable_map iterates all entries without needing max (test 28).

### GUI Map Read Tests (var: numeric keys) - removed 2026-06-19

A bottom section of the test window probed GUI-side reads of var: numeric-keyed global maps via `GetVariableFromGlobalVariableMap` with `Scope` and `Scope.Self`. The reads never resolved (the window showed `default` / `ERROR_FLAG_INDEX`), and the `Scope.Self` form logged a `FetchData` nullptr error every frame, spamming the console. The probes were display-only and unscored, so they were removed along with the `et_gui_action` map and the second `et_gui_map` entry that fed only them. Finding: GUI-side reads of var: numeric-keyed global-map entries do not resolve; CMF's mod action log keys entries with flag scopes via `MakeScopeFlag`, which does resolve in GUI.

## Size Limit Tests (et_run_map_size / et_run_list_size)

Run 2026-06-30. Probes the maximum entry count of a country variable map and a country variable list. Each test clears its structure, builds numeric-keyed entries with a counter, and checks `variable_map_size` / `variable_list_size` against the target. The builder nests whiles: an outer `limit` while re-enters an inner `count = 1000` batch until idx reaches TARGET. EU5 `while` hard-caps at 1000 iterations per invocation with no override keyword, so nesting is required to build past 1000.

Three engine findings from getting the builder loop clean:

- **EU5 `while` has no `max` field.** An attempt to flatten the loop with `max = 1100000` was rejected by the engine as `Unknown effect max`, so the loop silently defaulted to 1000 and built only 1000 entries (1k passed, all larger tiers failed). Unlike CK3/Vic3, EU5 `while` cannot raise its 1000 cap; nesting is the only way past it.
- **The inner batch uses `count = 1000`, not a limit.** A limit-based inner aborts at the 1000 cap and logs `while loop with no specified max aborted after executing 1000 times` on every batch; a counted loop completes instead. Switching the inner to `count` cleared the per-batch spam.
- **A limit-while warns the moment it reaches 1000 iterations, even at exactly 1000.** Tiers up to 100k are clean (outer does at most 100 batches), but a 1,000,000 build makes the outer do exactly 1000 batches and warns once. The 1M probes split the build into two 500,000 passes (500 batches each) so every loop stays under 1000 iterations.

| Test | Structure | Target | Result |
|------|-----------|--------|--------|
| Map 1k | variable map | 1,000 | PASS |
| Map 10k | variable map | 10,000 | PASS |
| Map 100k | variable map | 100,000 | PASS |
| Map 1M | variable map | 1,000,000 | PASS |
| List 1k | variable list | 1,000 | PASS |
| List 10k | variable list | 10,000 | PASS |
| List 100k | variable list | 100,000 | PASS |
| List 1M | variable list | 1,000,000 | PASS |

**8/8 passed.** Both structures reached 1,000,000 entries; no hard capacity cap was hit at 1M. The practical constraint is performance, not capacity.

### Findings

- **No capacity limit found at 1,000,000 for either structure.** The variable map and the variable list both reached 1M entries and passed their size checks.
- **Numeric `var:` counter values work as distinct variable map keys.** The map reaching 1M distinct entries confirms `key = var:et_size_idx` keys on the counter's value; had the keys collapsed, the map size would stay 1 and every map tier would FAIL.
- **Variable maps are dramatically faster than variable lists at scale (about 200x at 1M).** Building 1,000,000 entries took under 1 second for a map versus 3 minutes 20 seconds for a list. Building the 1k/10k/100k tiers was instant for a map and about 3 seconds for a list. Map insertion is near constant-time (hash map); list insertion cost grows with the list's current length (roughly quadratic total). For large per-country data, prefer a variable map over a variable list.

## Re-run of Tests 1-75 (2026-07-27)

Every prior test re-run alongside the new suites on 1.3.x. All results match the
last recorded run exactly: 26, 27, 31, 36-38, 43, 47, 48, 50, 53, 61 and 72-75 FAIL,
everything else PASS, and all 8 size tiers PASS. No behaviour changed since
2026-07-05, so nothing in the earlier findings needs revisiting for this patch.

## Re-run of Tests 1-38 (2026-06-30)

Re-run alongside the size tests; every result matches the prior run (26, 27, 31 FAIL; 36 displayed FAIL; 37, 38 displayed PASS as parse-error false positives; all others PASS). No behavior changed. (Macro tests 36-38 were redesigned to fail closed after this re-run; see the Macro Param Tests section.)

## Hidden Window Tests (Tests 39-71)

Run 2026-07-02. Covers the registered hidden/driver-window patterns used by CMF, Construction Manager, Autonomous Diplomats, and SmartTaxes. The rig is four registered top-level widgets in `et_hw_windows.gui` (an always-visible dynamic core, a static `visible = yes` twin, a gated `window`, and a remote TriggerAllAnimations target). One button (Run Hidden Window Tests) arms a boot driver whose state chain steps every timed test with settle delays; the chain takes about 12 seconds and the rows fill in when it finishes. Re-clicking the button re-runs the suite; a click while a run is mid-chain restarts scoring, so click once and wait.

Expected-FAIL rows assert a pattern previously recorded as broken, so FAIL is the result that CONFIRMS the lesson; probe rows had no expected value. Outcome: 23 results matched expectations, the 5 probes got answers (45, 60, 61, 65, 67), and 5 results overturned previously recorded lessons (41, 48, 50, 57, 70). Raw counts are not displayed in the UI, so where a count is cited below it is inferred from the pass/fail combinations.

| # | Test | Expected | Result |
|---|------|----------|--------|
| 39 | IsShown(scripted GUI) gate: _show fires when script sets the var | PASS | PASS |
| 40 | GetVariable('x').IsSet gate: _show fires | PASS | PASS |
| 41 | ScriptValue-compare gate: _show re-fires on later var changes | FAIL (sticky visible) | **PASS** |
| 42 | ScriptValue-compare gate evaluated at widget creation (pinned) | PASS | PASS |
| 43 | Static visible = yes top-level: descendant gate _show fires | FAIL (frozen subtree) | FAIL |
| 44 | Unpinned gate cycled off->on twice: _show fired both times | PASS | PASS |
| 45 | Pinned (visible_at_creation = no) gate cycled twice: _show re-fires | PROBE | PASS |
| 46 | Gated window, inner gate pre-set, pinned child: _show fires at creation | PASS | PASS |
| 47 | Same, unpinned child: _show fires | FAIL (created shown, no edge) | FAIL |
| 48 | Gated `window` re-creates children per show (trigger_on_create count = 2) | PASS | **FAIL** |
| 49 | Gated `widget` keeps children (trigger_on_create count = 1) | PASS | PASS |
| 50 | trigger_on_create defers while the parent is hidden | PASS | **FAIL** |
| 51 | trigger_on_create does not re-fire on gate cycles | PASS | PASS |
| 52 | Datamodel items seeded post-build instantiate and fire on create | PASS | PASS |
| 53 | Same-state on_finish: TriggerAllAnimations + immediate read sees items | FAIL (states play later) | FAIL |
| 54 | Chained-state read after a settle sees all items | PASS | PASS |
| 55 | Per-item scope passed from TriggerAllAnimations-fired states | PASS | PASS |
| 56 | Mid-cycle list append under statically-visible parent: items fire | PASS | PASS |
| 57 | Mid-cycle list append under dynamic-visible wrapper: items fire | FAIL (never instantiate) | **PASS** |
| 58 | TriggerAllAnimations reaches a state in another registered window | PASS | PASS |
| 59 | GetScriptedGui(Concatenate(...)) dynamic dispatch | PASS | PASS |
| 60 | Execute runs the effect despite is_shown = { always = no } | PROBE | PASS |
| 61 | Execute runs the effect despite is_valid = { always = no } | PROBE | FAIL |
| 62 | AddScope MakeScopeValue(3 * 4) + MakeScopeBool round-trip | PASS | PASS |
| 63 | save_temporary_scope_as inside an is_shown trigger | PASS | PASS |
| 64 | Self-loop poll state (trigger_on_create + self TriggerAnimation) keeps firing | PASS | PASS |
| 65 | Poll loop keeps advancing while its widget is hidden | PROBE | PASS |
| 66 | trigger_when fires when its condition flips true | PASS | PASS |
| 67 | trigger_when fires exactly once while the condition stays true | PROBE | PASS |
| 68 | Variable map value holding a flag target, read back and compared | PASS | PASS |
| 69 | Outermost every_* saved scope visible in a called sub-effect | PASS | PASS |
| 70 | Nested every_* saved scope visible in a called sub-effect | FAIL (reads as unset) | **PASS** |
| 71 | local_var captured in the nested loop reaches the sub-effect | PASS | PASS |

### Key Findings

**Confirmed lessons (the expected failures failed, the expected passes passed):**

- The static `visible = yes` freeze is real and reproduces in clean isolation (43): the identical IsShown-gated driver fired under the dynamic always-true top-level (39) and never fired under `visible = yes`.
- The loaded-save arming race reproduces synchronously (46/47): a child created with its gate already true never gets a hidden->shown edge, so `_show` never fires unless `visible_at_creation = no` forces the first-show transition. 46/47 set the inner gate while the parent window was hidden, then showed it, which is the same shape as a deserialized hidden window whose gate flag was armed before the GUI was built.
- The same-batch sequencing race is deterministic (53/54): a reader Executed in the same on_finish list as a PdxGuiTriggerAllAnimations call sees none of the item work (triggered states play on later frames); a chained state one settle later sees all of it. Per-item scopes pass through the triggered states intact (55).
- The rest of the driver toolkit behaves as documented: IsShown and IsSet gates are reactive (39/40), unpinned gates re-fire per cycle (44), trigger_on_create never re-fires on visibility cycles (49/51), datamodels instantiate items appended after window build (52) and mid-cycle under a statically-visible parent (56), TriggerAllAnimations crosses registered windows (58), GetScriptedGui(Concatenate(...)) dispatches by runtime name (59), computed MakeScopeValue / MakeScopeBool args arrive intact (62), save_temporary_scope_as works in trigger context (63), the self-TriggerAnimation poll loop runs (64), trigger_when fires on the flip (66), map values can hold flag targets (68), outermost-loop saved scopes and local_vars reach sub-effects (69/71).

**Probes answered:**

- **45: `visible_at_creation = no` does NOT freeze `_show`.** The pinned widget re-fired on each off->on gate flip, same as the unpinned one (44). The pin's only job is forcing the created-hidden state so a pre-true gate still produces a first-show edge; a one-shot driver is one-shot because its gate arms once per lobby, not because of the pin. A recurring driver may carry the pin safely.
- **60/61: `is_shown` does not gate Execute, `is_valid` DOES.** A scripted GUI with `is_shown = { always = no }` still ran its effect when Executed; one with `is_valid = { always = no }` did not. is_shown is display-only; is_valid is the real execution guard, so an is_valid gate protects against Executes fired from stale or force-triggered GUI paths.
- **65: state machines keep running while their widget is hidden.** The poll loop kept advancing after its gate closed, so hiding a poller does not stop it; the stop-guard belongs in the scripted GUI's effect.
- **67: trigger_when is edge-triggered.** One fire per false->true flip; no re-firing while the condition stays true for a full second.

**Overturned expectations:**

- **41: ScriptValue comparisons in `visible` re-evaluated on both value changes** within the ~2.5s window, so the "sticky visible" behavior seen in Autonomous Diplomats (a pull widget that fired a few times and then stuck) is a longer-horizon degradation, not a hard never-re-evaluates. Creation-time evaluation also works (42). Variable `.IsSet` gates or polling remain the safe choice for long-lived gates.
- **48 with 50: a gated `window` creates its children ONCE, at its first show, and never re-creates them; a gated `widget` creates its children immediately, even while hidden.** 50 failed because the trigger_on_create child under a hidden widget parent fired at instantiation (there is no deferral to first show), while the gated window's trigger_on_create child fired only once across two shows (48). Combined with 46 (pinned child fired at the window's first show) and 47 (unpinned child never fired), the consistent model is: `window` = lazy-create once on first show, `widget` = immediate create; nothing is torn down or re-created on later gate cycles, and trigger_on_create is strictly instantiation-time. Per-pulse re-work in a gated window must therefore come from `_show` re-fires or a running state loop (SmartTaxes' wait/apply loop), never from "re-created children".
- **57: mid-cycle items under a `visible = "[GetPlayer.Exists]"` wrapper instantiated and fired.** The eu5_auto_expand_forked failure (mid-cycle approved lists never instantiating under a dynamic-visible wrapper) did not reproduce in this minimal shape, so the wrapper alone is not sufficient to break instantiation. Statically-visible parents remain the safe default for two-pass windows, but the break must involve more of that window's structure than just the wrapper.
- **70: a scope saved in a nested every_country and read literally in a called sub-effect WAS set.** The known CMM failure (nested every_in_list with the scope name passed to the helper as a macro param) did not reproduce with plain nested every_country loops and a literal scope: read, so that failure is tied to the more complex shape, not to nested loops in general.

Tests 39-67 run inside the GUI rig; 68-71 are script-side and run inside et_hw_finish at the end of the chain. Test 50's finding means the after-lobby caller pattern's timing rests on when registered widgets are instantiated rather than on trigger_on_create deferring; the callers demonstrably work in production, but that instantiation timing is untested here.

## Variable List Duplicate Tests (et_run_dups + hidden-window test 75)

Run 2026-07-05. Probes whether a country variable list can hold the same target twice:
two unguarded add_to_variable_list calls with one flag, then size, iteration, and
removal checks (72-74, the Run List Duplicate Tests button), plus a GetList datamodel
seeded with the same flag twice in the hidden-window rig (75, runs with the HW chain).

| # | Test | Result |
|---|------|--------|
| 72 | add_to_variable_list appends a duplicate target (size 2) | FAIL |
| 73 | every_in_list visits the duplicated entry twice | FAIL |
| 74 | remove_list_variable removes one instance, not all | FAIL |
| 75 | GetList datamodel instantiates a duplicated entry twice | FAIL |

**0/4 passed.**

### Findings

- **A variable list holds each target at most once.** Adding an already-present target
  is a silent no-op: the size stays 1 (72), iteration visits one entry (73), and a GUI
  GetList datamodel instantiates one item widget (75). Lists behave as target sets.
  `is_target_in_variable_list` guards before adds therefore do not change the list
  contents; they only matter for skipping side effects paired with the add (counters,
  first-add setup).
- 74's failure is a consequence of 72, not a separate finding: only one entry ever
  existed, so the single remove_list_variable emptied the list and the size-1 assertion
  could not hold. Per-instance removal semantics are moot - duplicates cannot exist.
- Consequence for mods: multiplicity cannot be represented by repeated list entries
  (e.g. firing an engine GUI action N times per target via N datamodel items). Use
  distinct targets, per-rank lists, or a count stored elsewhere.

## on_game_start Save-Load Firing Test

Added 2026-07-12. Probes whether vanilla `on_game_start` fires when LOADING an
existing save, or only when starting a NEW game. CMF added its own `on_game_load`
hook because vanilla has no load hook; this test confirms that directly instead of
inferring it.

`et_on_game_start_load_probe` (in `et_on_actions.txt`, hooked under `on_game_start`)
runs `c:FRA = { change_culture = culture:greek_culture }`, flipping France's primary
culture to Greek. `on_game_start` fires in empty scope, so the probe navigates to
`c:FRA` explicitly behind a `country_exists` guard.

Protocol (both steps are required - step 1 is the control that proves the hook works
at all, so that a negative in step 2 means "did not fire on load" and not "hook broken"):

1. Enable the engine test. Start a NEW game, then select France and open its country
   panel. Its primary culture should read Greek. This confirms the on_action runs.
2. Take an existing save where France is still French (any normal save made without
   this probe). With the engine test enabled, load it and open France's country panel.
   - France shows Greek -> `on_game_start` DID fire on load.
   - France still French -> `on_game_start` did NOT fire on load.

Expected: France flips in step 1 and stays French in step 2, i.e. `on_game_start` is
a new-game-only hook and does not run on save load.

Result: CONFIRMED 2026-07-12. New game -> France Greek; loaded save -> France French.
Vanilla `on_game_start` does not fire on save load, only on a new game.

## Countryless Client Tests (76-89, 103, 107)

Added 2026-07-27. Probes what a client can still do with no country of its own.
Every claim in this area rested on one comparison across CMM's own feature surface,
in a single unspecified observer state, so the distinct client states were never
separated.

The rig is `et_nc_core` in `et_nc_windows.gui`. It self-starts once the map exists
and finishes about 4 seconds later, and it roots at `c:FRA` rather than the player.
Its rows in `et_window.gui` read only `GetCountry('FRA')` and `GetVariableSystem`;
nothing in section 8 touches `Player`, which comes back blank in three of the four
states. The one button, Re-run Countryless Suite, only sets a GUI variable, since a
scripted GUI Execute is the mechanism under test and would be dropped in exactly
the states that matter.

Test 76 exists to make the rest readable: without a marker proving the driver ran,
a blank row cannot be told apart from a dropped Execute.

Run 2026-07-27 on 1.3.x.

| # | Test | Lobby | Country | Generic obs | Specific obs |
|---|------|-------|---------|-------------|--------------|
| 76 | A pass has run this client session | TRUE | TRUE | TRUE | TRUE |
| 77 | GetPlayer.IsValid | FALSE | TRUE | FALSE | TRUE |
| 78 | IsPlayerValid | FALSE | TRUE | FALSE | TRUE |
| 79 | IsPlayerObserver | FALSE | FALSE | TRUE | TRUE |
| 80 | Scripted GUI Execute reached script | **PASS** | PASS | **FAIL** | **FAIL** |
| 81 | Scripted GUI IsShown evaluates | PASS | PASS | PASS | PASS |
| 82 | Scripted GUI IsValid evaluates | PASS | PASS | PASS | PASS |
| 83 | GetVariableSystem write + read | PASS | PASS | PASS | PASS |
| 84 | Data read off a named country | PASS | PASS | PASS | PASS |
| 85 | ExecuteConsoleCommand reached script | PASS | PASS | PASS | PASS |
| 86 | Commands landed from a 3-call burst | 1 of 3 | 1 of 3 | 1 of 3 | 1 of 3 |
| 87 | Commands landed from one `;` string | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| 88 | Location.GetKey on location:paris | 2191 | 2191 | 2191 | 2191 |
| 89 | Missing global map key reads silently | PASS | PASS | PASS | PASS |
| 103 | GetVariableSystem compares as a string | PASS | PASS | PASS | PASS |
| 107 | GUI variable carried from an earlier game | see below | see below | see below | see below |
| 108 | Execute ~1s after map load reached script | PASS | PASS | | |
| 109 | Console ~1s after map load reached script | FAIL | FAIL | | |

Rows 76-89 and 103 are settled-state readings, taken via Re-run.

**108/109 have no per-state columns and cannot have any.** They fire at map load, and
at map load every client is still at the country-selection lobby: observer mode and
taking a country are both reached through it. Two different questions were split out
of that instead, and together they close the coverage:

Run 2026-07-27, one full client relaunch per column so the map-load probes are armed.

| # | Test | Lobby | Country | Generic obs | Specific obs |
|---|------|-------|---------|-------------|--------------|
| 108 | Execute ~1s after map load | PASS | PASS | PASS | PASS |
| 109 | Console ~1s after map load | FAIL | FAIL | FAIL | FAIL |
| 110 | Console ~2s after map load | PASS | PASS | PASS | PASS |
| 111 | Console ~4s after map load | PASS | PASS | PASS | FAIL* |
| 112 | Console ~8s after map load | PASS | PASS | PASS | PASS |
| 113 | First Execute after taking a country | n/a | PASS | n/a | n/a |
| 114 | First console after taking a country | n/a | PASS | n/a | n/a |
| 115 | First Execute after entering observer | n/a | n/a | FAIL | FAIL |
| 116 | First console after entering observer | n/a | n/a | PASS | PASS |

n/a means that transition never happened in that column, so the probe never fired and
its row shows the seeded 0 as FAIL. Those cells are not results.

### Findings

**The console warm-up ends between 1 and 2 seconds after map load.** 109 failed in all
four sessions and 110 passed in all four, and 112 passed in all four. So the window is
real, short, and identical in every column - which it must be, since at map load every
client is still at the lobby.

\* **111's single FAIL is a collision artifact, not a warm-up result.** A warm-up
cannot fail at 4s while passing at 2s and 8s. In that column the observer transition
happened while the ladder was running, and 116 passed, so the transition probe's own
console command was in flight when the 4s rung fired and the rung was refused - which
is exactly test 86's one-command-at-a-time rule predicting its own interference. The
window conclusion does not rest on this rung.

**Execute needs no warm-up at all (108).** It reached script about a second after map
load in every session, while the console at the same instant did not. The two command
paths are not gated the same way.

**No state transition re-opens a warm-up (114, 116).** The very first console command
issued after taking a country, and after entering observer, both landed immediately.

**115 with 116 is the decisive form of the observer finding.** At the first frame of
observer mode the Execute was already dead and the console already worked. Every
timing explanation for test 80 is now excluded: it is not warm-up, not settling, and
not gating, because the same instant produced a working console command and a dead
Execute. Paired with 113/114 passing on the country transition, the split is purely
about observer status.

**107 reads FALSE in all four columns and that is correct.** Each column was a fresh
relaunch, so each was the first game of its session. 107 needs two games inside one
client run, which the previous run established (FALSE then TRUE).

**Test 107 CONFIRMED (re-run 2026-07-27 after the rebuild): GUI variables survive
from one game to the next inside a single client run.** First game of a fresh client
session read FALSE, second game of the same session read TRUE, which is the shape the
claim predicts and the shape the original broken version could not produce. The
rebuilt gate uses `et_nc_fresh`, a country variable `et_nc_seed` sets at
`on_game_start` and whichever branch fires clears; a GUI variable cannot be the
per-game marker when surviving the game boundary is the thing being measured. This
retires an assertion that had sat in two memories with no verification behind it.

### Findings

**The country-selection lobby is NOT a countryless client for Execute purposes.**
This is the result that overturns the recorded lesson. `.Execute()` reached script
at the lobby (80 PASS) with `GetPlayer.IsValid`, `IsPlayerValid` and
`IsPlayerObserver` all reading FALSE, and failed in both observer states. The prior
claim grouped "country-selection lobby, observer mode, between releasing one country
and taking another" as one dead state; only the observer half holds. Selecting a
country in the lobby without pressing Play changes nothing: all four rows read the
same as the unselected lobby, so that is not a distinct state.

**The console has a warm-up of between 1 and 2 seconds after map load; scripted GUI
Executes have none (108-112).** Across six sessions the Execute at ~1s always reached
script and the console at ~1s never did, while the console at ~2s and ~8s always did.
Both probes are armed once per game by `et_nc_seed` and disarmed only by the reset, so
a settled re-run cannot overwrite their answer. See the four-state table below.

**RETRACTED: an earlier reading suggested "an early window where NO command lands,
Execute and console alike". That was a rig artifact, not engine behaviour.** The
driver's gate is `Not(GetVariableSystem.Exists('et_nc_done'))`, and that GUI variable
survives the game boundary - which is exactly what test 107 confirms. So in any game
after the first of a client run the driver never auto-runs at all, and every row
reads the zeros `et_nc_seed` wrote. Step 2 of the 107 run reproduces it cleanly: 80
and 85 FAIL with 0 of 3 on both console rows, then one press of Re-run in the SAME
game turns all of them green. Nothing about elapsed time was involved. 108/109
supersede that reading entirely.

**Consequence for anyone running this suite: press Re-run Countryless Suite in every
state, including the first.** The auto-run only happens in the first game of a client
session. Row 76 reads the same persisting GUI variable, so it reports TRUE in a later
game even when no pass ran there; treat it as "a pass has run at some point this
session", not as "this state was measured".

This does not touch the observer result, which tests 115/116 have since put beyond
timing entirely: at the first frame of observer mode the console command landed and
the Execute did not.

Mechanism for the lobby accepting Executes at all is still unverified.

**Observing a specific country is indistinguishable from playing on every accessor
except `IsPlayerObserver`.** 77, 78 and 79 all read TRUE there, and 79 is the only
one that differs from a normal game. So `GetPlayer.IsValid` alone is worthless as a
"this client controls a country" test, and `And(GetPlayer.IsValid,
Not(IsPlayerObserver))` is exactly right. `CMFHasPlayerCountry` is confirmed correct.

**Generic observer and observing a country behave identically for Execute.** Both
FAIL, despite generic observer having no valid player at all and specific observer
reporting a valid one. So the discriminator for a dropped Execute is observer
status, not player validity.

**Everything that was claimed to still work, does.** IsShown, IsValid,
GetVariableSystem, arbitrary-country data reads and ExecuteConsoleCommand pass in
all four states, including generic observer.

**The console really does take one command at a time (86).** Three
`ExecuteConsoleCommand` calls in one state landed exactly 1, in every state, and the
log carries exactly two `console.cpp:1268` "You can't add new commands while the
console is still running commands" lines per pass. `ExecuteConsoleCommands` with
`;` separators landed all 3 (87), so it is the only way to batch.

**`Location.GetKey` returns the numeric runtime id (88).** `location:paris` reported
`2191`, not `paris`. Confirmed.

**A missing key in a global variable map reads silently in GUI (89).** No error, no
break. This is the opposite of the script side, where a quoted `variable_map()` on a
trigger's left side logs two errors per evaluation.

**Test 107 is VOID - the test was broken, not the claim.** Its gate was a live
expression on `et_nc_persist`, so the driver's own end-of-pass write to that key
flipped the gate and fired it mid-game. It read TRUE everywhere including the first
game of the session, which is impossible if it were measuring what it claimed. The
rig now gates both branches on a per-game country variable (`et_nc_fresh`, set by
`et_nc_seed` at `on_game_start` and cleared by whichever branch fires), because a GUI
variable cannot be the per-game marker when surviving the game boundary is the thing
being measured. Re-run needed; no conclusion either way yet.

### Protocol

**Press Re-run Countryless Suite in every state, including the first.** The automatic
pass fires only in the first game of a client session, because its gate reads a GUI
variable that survives the game boundary (test 107). In any later game the rows
otherwise show `et_nc_seed`'s zeros, which is indistinguishable from the engine
dropping every command. Rows 108/109 are the exception: they fire once per game at
map load and keep that answer.

The normal-country run is the control and is not optional. Without a run where
every row can pass, a wall of FAILs in observer mode is indistinguishable from a
broken rig.

1. Enable only the engine test. Start a new grand campaign. At the country-
   selection lobby, wait 5 seconds and record the section 8 and 9 rows: that is
   the lobby state. If the window does not render there, record that instead; the
   other states still stand on their own.
2. Take France and enter the game. Press Re-run Countryless Suite, wait 5 seconds,
   and record the same rows. This is the control.
3. Start a new grand campaign, swap to generic observer at the lobby, taking no
   country. Once in game, press Re-run Countryless Suite, wait 5 seconds, record.
4. Start a new grand campaign, swap to observing France specifically. Once in
   game, press Re-run Countryless Suite, wait 5 seconds, record.

Test 107 is answered by the second game of a client run, so it reads FALSE in step
1 and TRUE from step 3 onward as long as the game was never closed in between.

## Pure-Script Semantics (90-97, 106)

Added 2026-07-27. Run button: Run Script Tests. No GUI rig and no timing.

Run 2026-07-27 on 1.3.x.

| # | Test | Expected | Result |
|---|------|----------|--------|
| 90 | change_variable max = 9 raises 3 to 9 | PASS | PASS |
| 91 | change_variable min = 3 lowers 9 to 3 | PASS | PASS |
| 92 | change_variable max = 3 leaves 9 alone | PASS | PASS |
| 93 | List-iterator limit sees the body's own counter | FAIL (limit is blind to it) | FAIL |
| 94 | local_var set in one scope block reads in another | PASS | PASS |
| 95 | Same-named locals at two nesting levels share a slot | PASS | PASS |
| 96 | Variable written on a province_definition reads back there | PROBE | **FAIL** |
| 97 | Same variable read through a location's province_definition link | PROBE | **FAIL** |
| 106 | Nested every_in_list scope reaches a helper called by macro-param name | FAIL (the CMM shape) | **PASS** |

### Findings

**`change_variable` `min`/`max` are the min/max FUNCTIONS on the current value
(90-92).** `max = 9` raised 3 to 9, `min = 3` lowered 9 to 3, and `max = 3` left 9
alone. The ceiling-clamp reading, which a code review once "fixed" a running
maximum into and shipped as a regression, is wrong: `max` never lowers a value.
This is now settled by a test rather than by an incident report.

**A list-iterator `limit` cannot see the body's own counter increments (93).** The
limit was `local_var:i < 2` on a 5-entry list with the body incrementing `i`, and
all 5 entries were visited. Confirmed, and now isolated rather than resting on an
observation where the batch size changed in the same edit.

**`local_var:` is execution-wide (94, 95).** A local set inside `c:FRA = { }` read
back inside `c:ENG = { }` in the same execution, and a same-named local written by
an inner loop was visible to the outer scope afterwards. Both halves of the claim
confirmed, including the positive direction that had only ever been inferred from
the engine's error text.

**The province_definition round-trip is dead on the WRITE side (96, 97).** This is
the isolation the memory asked for. 96 wrote a variable on a `province_definition`
and read it back **in the same block**, and still failed, so the value never lands
at all. 97's failure is a consequence, not a second finding. Never store variables
on a province_definition; the working pattern remains writing to every province
slice via `every_province_in_province_definition`.

**106 OVERTURNS the narrowed nested-scope claim.** A scope saved in a nested
`every_in_list` over a temp list, handed to a helper as a macro-param NAME, WAS set
inside the helper. Test 70 had already disproved the general form; this was the
shape the memory narrowed the claim to, "until re-isolated". Both are now
disproved, so the CMM list-reset bug was caused by something else and the
nested-loop saved-scope rule should not be carried forward as an engine fact.

90-92 are the three-way split of the `change_variable` min/max question. The
recorded claim is that they are the min/max FUNCTIONS on the current value, not the
floor/ceiling clamps that `min`/`max` mean inside a `value = { }` block. 92 is the
half a code review once inverted, shipping a regression: a clamp reading would drop
9 to 3 there.

96 and 97 are the isolation the province_definition memory says was never done. The
claim is that definition-scope variables do not round-trip, without knowing whether
the write or the link read is the dead side. 96 PASS with 97 FAIL means the link
read; 96 FAIL means the write.

106 is the shape test 70 left open. Test 70 disproved the general form (a plain
nested `every_country` read as a literal `scope:X` in a called effect works), and
the memory then narrowed the claim to nested `every_in_list` with the scope name
passed as a macro param, "until re-isolated". This is that shape.

## State-Machine and Nesting (98-102)

Added 2026-07-27. Runs with the hidden-window chain (Run Hidden Window Tests); the
chain is about 4 seconds longer than before.

Run 2026-07-27 on 1.3.x.

| # | Test | Expected | Result |
|---|------|----------|--------|
| 98 | Chain reaches its tail past a bare name/duration/next state | FAIL (bare state stalls) | FAIL |
| 99 | Control: same chain, middle state has an on_start | PASS | PASS |
| 100 | GetGlobalList binds a global_variable_list to a datamodel | PASS | PASS |
| 101 | Outer Scope context survives an inner Location datamodel | PASS | PASS |
| 102 | datamodel_reuse_widgets keeps trigger_on_create from re-firing | PASS | PASS |

### Findings

**The bare-delay-state stall is real and now properly isolated (98 with 99).** Two
chains identical except for an `on_start` on the middle state: the bare one never
reached its tail, the control did, and both recorded that their `_show` fired first,
so the failure is "started and stalled" rather than "never armed". The recorded
lesson previously carried its own caveat that the state had been renamed in the same
change, making `on_finish` the mechanism by inference; that caveat can be dropped.

Possible mechanism, unconfirmed: the run logged one
`pdx_gui_animation_runtime_state.cpp:613 Animation triggered has no valid state
properties or sound effects` during the hidden-window suite. That is consistent with
the engine refusing to play a state carrying nothing, which would be why the chain
dies there. One occurrence, not attributed to a specific state, so it is a lead
rather than a result. It does mean the "nothing is logged" half of the recorded
lesson is doubtful.

**`GetGlobalList` binds a script-side global_variable_list into a datamodel (100).**
All 3 seeded targets instantiated.

**An outer `Scope` datamodel binding survives an inner `Location` datamodel in the
same tree (101).** Inside every inner row the outer `Scope.GetLocation` still
resolved to the seeded paris, while the inner `Location` was a different location.
Each type holds its own context slot; confirmed, and no longer resting only on a
working fix in another mod.

**`datamodel_reuse_widgets = yes` stops `trigger_on_create` firing per data item
(102).** Swapping the list for three different targets produced no further fires.
The CMM tab bar's deliberate exclusion from trigger_on_create caching rests on a
real behaviour.

98 and 99 are the controlled pair. The recorded claim came with its own caveat: the
state was renamed in the same change that added the `on_finish`, so `on_finish` was
"the mechanism by inference rather than by controlled test". These two chains are
identical apart from the middle state's `on_start`, and both require their `_show`
to have fired before scoring, so a FAIL means "started and stalled" rather than
"never armed". Nothing in the existing rig covered this: every non-`_show` state in
`et_hw_core` already carries an `on_start` or `on_finish`.

101's inner datamodel is a fixed literal (`london`'s province locations) rather than
one derived from the outer item, so the result does not depend on how many locations
any province holds. If the `Scope` slot survives the `Location` rebinding,
`Scope.GetLocation` is still paris inside every inner row; if it is shadowed, it is
never paris. The check also requires at least one inner row where the two differ, so
the two slots cannot pass by agreeing accidentally.

102 seeds three targets, lets them instantiate, then swaps the list for three
different targets. A PASS means no further `trigger_on_create` fires, i.e. the
widgets were reused. This is the premise the CMM tab bar's exclusion from caching
rests on; a FAIL means that exclusion is unnecessary.

## on_action Scope and Periodic Pulses (104-105)

Added 2026-07-27. Both count fires into a global, and the count is the result: a
no-scope hook fires once, a country-scope hook would fire once per country. The
seed is guarded so a per-country hook cannot re-zero its own counter.

Run 2026-07-27 on 1.3.x.

| # | Test | Expected | Result |
|---|------|----------|--------|
| 104 | on_game_start fires (1 = no scope, many = country scope) | 1 | 1 |
| 105 | weather_monthly_pulse fires (should track elapsed months) | 6 after 6 months | 6 |

### Findings

**`on_game_start` fires exactly once, in no scope (104).** A country-scoped hook
would have fired once per country and read in the hundreds. The project memory index
line claiming it "fires before country selection, not after" describes something
else and is not what this measures; the file it points at, "fires in no scope (not
country scope)", is the one this confirms.

**`weather_monthly_pulse` fires once per elapsed month in no scope (105).** Six fires
between 1 April and 1 October, 1337. Not per country and not per location, so it is
usable as the global monthly catch-up hook for a CMF-independent mod.

104 settles a flat contradiction in the memory set: the project memory index line
says `on_game_start` "fires before country selection, not after", while the file it
points at says it "fires in no scope (not country scope)". Those are different
claims and only the scope half is testable here.

For 105, run the step-1 save from 1 April, 1337 to 1 October, 1337 and read the
count. Six means once per elapsed month in no scope. A number in the hundreds or
thousands would mean the pulse is country- or location-scoped.

## Console Parse Cost (117-118)

Rig: `et_pc_effects.txt`, `et_pc_windows.gui`, seeded by `et_pc_seed`. Self-starting, so no
Execute of its own lands inside the measurement windows.

The claim under test: a console `effect` command is parsed when it runs, and that costs a large
FIXED number of `jomini_effect.cpp:158` / `jomini_trigger.cpp:103` lines per COMMAND, rather than a
cost set by the size of the effect the command names.

This came out of the Construction Manager observer bridge, where the recorded lesson was the
opposite - "cost tracks the size of the effect tree it names" - inferred from a single measurement
of 29 commands naming one mid-sized scoring effect at ~3,400 lines each. One data point cannot
separate "3,400 because that tree is that big" from "3,400 because every command costs that". The
pair below separates them.

| # | Test | Expected if fixed per command | Expected if proportional |
|---|------|-------------------------------|--------------------------|
| 117 | 20 calls as 20 commands | ~20x the floor | same as 118 |
| 118 | the same 20 calls in 1 command | ~1x the floor | same as 117 |

Both bursts call `et_pc_tiny`, a one-statement effect that names nothing, exactly 20 times. Equal
call counts, different command counts, so the difference in log volume is the per-command floor.
Burst 117 is submitted as one `;`-separated string rather than 20 `ExecuteConsoleCommand` calls,
because the console refuses any command issued while another is running (test 86) and 20 separate
calls would land one.

The counter row is the pass condition for both: `et_pc_n` must read 40. If either burst dropped
calls the volumes are not comparable and the measurement is void.

### Protocol

New game as France, not ironman. The rig self-starts at map load: burst 117 fires 5 seconds in
(clear of the 1-to-2 second console warm-up, test 109), burst 118 twelve seconds after that, and
the freshness marker is cleared 8 seconds later so its own command sits outside both windows. Wait
30 seconds on the map, then check the row reads 40 of 40 and read the volumes out of `debug.log`,
which carries a `[HH:MM:SS]` stamp on every line, so the two bursts separate by timestamp. The
`console.cpp:1175` lines mark each burst: 20 of them for 117, one for 118.

### Result

Run 2026-07-27, new game as France. The counter row read **40 of 40**, so both bursts landed every
call and the volumes are comparable.

| # | Test | Commands | Calls | `Adding effect` + `Adding trigger` lines |
|---|------|----------|-------|------------------------------------------|
| 117 | 20 calls as 20 commands | 20 | 20 | **67,535** |
| 118 | the same 20 calls in 1 command | 1 | 20 | **3,395** |

**CONFIRMED: the cost is fixed per command, not proportional to the effect named.** The same 20
calls cost 19.9x more spread across 20 commands than packed into one.

The rest of the run calibrates the floor exactly, because every other second in the log holds a
whole number of unrelated single commands and the volume tracks it precisely: 1 command = 3,376
lines at six separate timestamps, 2 commands = 6,752, 3 commands = 10,128. So **the floor is 3,376
lines per command**, and it is charged whatever the command names - `et_pc_tiny` is a single
`change_variable` statement.

The named effect's own size shows up as a small term on top: burst 118's one command came to 3,395,
which is the floor plus 19, against the 20 `et_pc_tiny` call sites it carries. About one line per
statement instantiated. That is why burst 117 reads 3,377 per command rather than 3,376.

This overturns the recorded lesson directly. The earlier reading of ~3,400 lines per command was
attributed to the size of the scoring effect being named; a one-statement effect costing 3,376 shows
the number was the floor all along. The design rule that follows is to minimise the COMMAND COUNT,
not the size of the effect each command names.

### Note on the proportional term

The live Construction Manager measurement also showed a term above the floor for very large named
trees: commands naming a 222,195-node tree cost on the order of a million lines each, far above the
floor. This pair does not test that half, since a tree that size cannot be built here without
generating a large amount of throwaway script. That half stays a live measurement.

