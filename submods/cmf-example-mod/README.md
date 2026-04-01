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

## How to use

1. Enable both `community_mod_framework` and `community_mod_framework_example`.
2. Start a new game as any country.
