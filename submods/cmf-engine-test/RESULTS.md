# Engine Test Results

Date: 2026-06-14

## Country Tests (engine_test_run)

| # | Test | Result |
|---|------|--------|
| 1 | scope:setting as variable map key | PASS |
| 2 | variable_map(x \| scope:setting) read-back | PASS |
| 3 | Map value to local variable arithmetic | PASS |

**3/3 passed**

## Global Tests (engine_test_run_global)

| # | Test | Result |
|---|------|--------|
| 4 | set_global_variable (baseline) | PASS |
| 5 | Global write + read (hardcoded flag) | PASS |
| 6 | Global write + read (scope:setting) | PASS |
| 7 | scope:setting == flag:engine_test_key_a ? | PASS |
| 8 | Global write(scope:setting) read(hardcoded) | PASS |
| 9 | Read on_action global map (hardcoded) | PASS |
| 10 | Read on_action global map (scope:setting) | PASS |
| 11 | Cross-context country map read (flag to scope:setting) | PASS |
| 12 | Global write stays in global scope | PASS |
| 13 | flag:->flag: same-key update (country map) | PASS |
| 14 | flag:->flag: same-key update (global map) | PASS |
| 15 | scope:setting->scope:setting direct overwrite (global) | PASS |
| 16 | Update global map entry (flag: then scope:setting) | PASS |
| 17 | Update country map entry (flag: then scope:setting) | PASS |
| 18 | Read back update with scope:setting (two entries?) | PASS |
| 19 | remove_from_map with scope:setting on flag: entry | PASS |
| 20 | Workaround: remove + re-add global map | PASS |
| 21 | Workaround: remove + re-add country map | PASS |
| 22 | scope:setting remove + re-add (global) | PASS |
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

## Macro Param Tests (engine_test_run_global)

Run 2026-06-19.

| # | Test | Result |
|---|------|--------|
| 36 | macro param as key in variable_map() quoted string | FAIL |
| 37 | macro param in map name position of quoted string | PASS |
| 38 | macro param as both map name and key | PASS |

Anomalous and unexplained. Each test reads the same dedicated map seeded with
flag:engine_test_key_a = 55, passing the slot via a $PARAM$ macro arg:

- 36 (macro in key slot, literal map name) FAILS: $KEY$ did not substitute.
- 37 (macro in map-name slot, literal key) PASSES: $MAP$ did substitute.
- 38 (macro in both slots) PASSES: both substituted, including the same key-slot
  macro that failed in 36.

So the key-slot macro substitutes when a map-name macro is also present in the
string (38) but not when the map name is literal (36). This contradicts the
documented rule that $PARAM$ never substitutes inside quoted accessors. The rule
should be revisited once the behavior is understood; do not rely on either outcome
until then.

## Summary

**Total: 32/35 passed (3 failed)**

Tests 36-38 (macro params in quoted accessors) ran 2026-06-19 with an anomalous,
unexplained result (36 FAIL, 37 PASS, 38 PASS); see the Macro Param Tests section.

### Key Findings

**add_to_variable_map NOW updates existing entries (tests 13-18, 23):**
- Writing to the same key twice overwrites: `add_to` acts as "add or update", replacing the prior value.
- Applies to both country and global maps, and regardless of key type (flag:, scope:setting).
- Behavior change: on the 2026-03-28 run these tests FAILED (add was "add only", a silent no-op on an existing key), and the var: intermediary update (test 23) also failed. A game patch between 2026-03-28 and 2026-06-14 reversed this. Re-run this suite after any patch before relying on either behavior.
- remove + re-add (tests 19-22) still works, so cmf_change_variable_map remains correct; it is just no longer required to update a value.

**Variable references cannot be used in map name position (tests 26-27):**
- "variable_map(local_var:X|...)" and "variable_map(var:X|...)" do not resolve - the map name must be a literal.
- Variable references DO work in the key position (tests 24-25, and test 35 for a var: numeric key).

**ordered_key_in_variable_map defaults to 1 without max (tests 31-32, 34):**
- Without max, the iterator picks exactly one element (test 34 passes with count = 1).
- Test 31 fails because it expects all 3 entries, but only 1 is visited.
- With max = 3, all entries are visited (test 32).
- every_key_in_variable_map iterates all entries without needing max (test 28).

### GUI Map Read Tests (var: numeric keys) - removed 2026-06-19

A bottom section of the test window probed GUI-side reads of var: numeric-keyed global maps via `GetVariableFromGlobalVariableMap` with `Scope` and `Scope.Self`. The reads never resolved (the window showed `default` / `ERROR_FLAG_INDEX`), and the `Scope.Self` form logged a `FetchData` nullptr error every frame, spamming the console. The probes were display-only and unscored, so they were removed along with the `engine_test_gui_action` map and the second `engine_test_gui_map` entry that fed only them. Finding: GUI-side reads of var: numeric-keyed global-map entries do not resolve; CMF's mod action log keys entries with flag scopes via `MakeScopeFlag`, which does resolve in GUI.
