# Community Mod Framework Example Mod

This is a reference integration mod for `community_mod_framework`.

## What it demonstrates

### CMM (Community Mod Menu)
- Declaring dependency on Community Mod Framework in `.metadata/metadata.json`.
- Registering settings under mod id `cmm_example` with derived localization keys.
- Appending into CMF shared registration hook `cmf_on_mod_registration`.
- Reacting to setting changes via the `cmf_on_callback` on_action and `_on_changed` callbacks (text and list settings).
- Grouping the `General` tab into `Toggles`, `Values`, `Lists`, and `Alerts` sections using tab-specific group ids.
- Global settings

### CMF (Framework Features)
- Registering custom alerts with localization keys, shown or removed based on a CMM toggle.
- Opening an event from an alert left-click through the `cmf_on_callback` on_action.
- Opening the Advances screen from an alert left-click through the `cmf_active_alert` GUI variable.
- Registering custom action bar buttons with localization keys.

## Files

### CMM
- `in_game/common/on_action/cmf_example_on_actions.txt`
- `in_game/common/scripted_effects/cmm_example_effects.txt`
- `in_game/common/scripted_guis/cmm_example_scripted_gui.txt`
- `main_menu/localization/english/cmm_example_mod_l_english.yml`

### CMF
- `in_game/common/scripted_effects/cmf_example_effects.txt`
- `in_game/events/cmf_example_events.txt`
- `in_game/gui/cmf_example/cmf_example_alert_watcher.gui`
- `in_game/gui/scripted_widgets/cmf_example_scripted_widgets.txt`
- `main_menu/localization/english/cmf_action_bar_example_l_english.yml`
- `main_menu/localization/english/cmf_alert_example_l_english.yml`
- `main_menu/localization/english/cmf_event_example_l_english.yml`

## How to use

1. Enable both `community_mod_framework` and `community_mod_framework_example`.
2. Start a new game as any country.
