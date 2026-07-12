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
