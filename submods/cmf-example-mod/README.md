# Community Mod Framework Example Mod

This is a reference integration mod for `community_mod_framework`.

## What it demonstrates

### CMM (Community Mod Menu)
- Declaring dependency on Community Mod Framework in `.metadata/metadata.json`.
- Registering settings under mod id `cmm_example` with derived localization keys.
- Appending into CMM shared registration hook `cmm_on_mod_registration`.
- Defining immediate per-setting callbacks for country-scope bool, button, numeric, slider, dropdown, text, and list examples.
- Defining immediate per-setting callbacks for global bool, button, numeric, slider, and dropdown examples.
- Splitting country-scope and global-scope examples across separate `General` and `Global` tabs.
- Grouping the `General` tab into `Toggles`, `Values`, and `Lists` sections using tab-specific group ids.
- Demonstrating the full global setting surface; global text is intentionally omitted because CMM does not expose a global text-setting API.

### CMF (Framework Features)
- Creating and showing a custom alert with localization keys and a scripted GUI callback.
- Creating and showing a custom action bar button with localization keys and a scripted GUI callback.

## Files

### CMM
- `in_game/common/on_action/cmf_example_on_actions.txt`
- `in_game/common/scripted_effects/cmm_example_effects.txt`
- `in_game/common/scripted_guis/cmm_example_scripted_gui.txt`
- `main_menu/localization/english/cmm_example_mod_l_english.yml`

### CMF
- `in_game/common/scripted_guis/cmf_sgui_action_bar_example.txt`
- `in_game/common/scripted_guis/cmf_sgui_alert_example.txt`
- `main_menu/localization/english/cmf_action_bar_example_l_english.yml`
- `main_menu/localization/english/cmf_alert_example_l_english.yml`

## Test flow

1. Enable both `community_mod_framework` and `community_mod_framework_example`.
2. Start a new game as any country.
3. **CMM:** Open pause menu and click `Mod Menu`.
4. Confirm the `Registered mods:` counter is at least `2` (core + example).
5. Select `CMM Example Mod` and confirm the `General` tab shows one of each country-scope setting type across `Toggles`, `Values`, and `Lists`.
6. Switch to the `Global` tab and confirm it shows one of each global setting type across `Toggles` and `Values`.
7. **CMF:** Confirm the example custom alert appears in the alert bar.
8. Confirm the example action bar button appears in the action bar.

## Integration snippet for other modders

```txt
# in_game/common/scripted_effects/<your_mod>_cmm.txt
your_mod_register_in_cmm = {
    cmm_register_bool_setting = {
        mod_id = your_mod_id
        setting_id = your_setting_id
        tab_id = general
        group_id = general
        default_value = 1
    }
}
```
