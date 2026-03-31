# Engine Test Results

Date: 2026-03-28

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
| 13 | flag:->flag: same-key update (country map) | FAIL |
| 14 | flag:->flag: same-key update (global map) | FAIL |
| 15 | scope:setting->scope:setting direct overwrite (global) | FAIL |
| 16 | Update global map entry (flag: then scope:setting) | FAIL |
| 17 | Update country map entry (flag: then scope:setting) | FAIL |
| 18 | Read back update with scope:setting (two entries?) | FAIL |
| 19 | remove_from_map with scope:setting on flag: entry | PASS |
| 20 | Workaround: remove + re-add global map | PASS |
| 21 | Workaround: remove + re-add country map | PASS |
| 22 | scope:setting remove + re-add (global) | PASS |
| 23 | Workaround: var: intermediary for update | FAIL |
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

**21/31 passed**

## Summary

**Total: 24/34 passed (10 failed)**

### Key Findings

**add_to_variable_map does NOT update existing entries (tests 13-18):**
- Writing to the same key twice does not overwrite — `add_to` is "add only", not "add or update".
- This applies to both country and global maps, and regardless of key type (flag:, scope:setting).
- The workaround is remove + re-add (tests 19-22 all pass).

**var: intermediary does not help with updates (test 23):**
- Storing scope:setting in a var: and using that as the key still doesn't update an existing flag: entry.

**Variable references cannot be used in map name position (tests 26-27):**
- `"variable_map(local_var:X|...)"` and `"variable_map(var:X|...)"` do not resolve — the map name must be a literal.
- Variable references DO work in the key position (tests 24-25 pass).

**ordered_key_in_variable_map defaults to 1 without max (tests 31-32, 34):**
- Without `max`, the iterator picks exactly one element (test 34 passes with count = 1).
- Test 31 fails because it expects all 3 entries, but only 1 is visited.
- With `max = 3`, all entries are visited (test 32).
- `every_key_in_variable_map` iterates all entries without needing max (test 28).

