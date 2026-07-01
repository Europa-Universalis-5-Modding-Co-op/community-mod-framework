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
