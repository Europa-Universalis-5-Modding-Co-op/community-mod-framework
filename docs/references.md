# Reference Index
This file catalogs useful reference files for CMM work.

## Vanilla EU5
- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\ingame_menu.gui`
  - Escape menu override target for menu button injection.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\common\scripted_guis\scripted_guis.info`
  - Scripted GUI schema.

- `C:\Steam\steamapps\common\Europa Universalis V\game\main_menu\gui\debug_menus.gui`
  - Valid `gui.createwidget` / `gui.ClearWidgets` usage.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\countries_list_view.gui`
  - Data-driven list rendering (`filtered_sorted_list`).

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\encyclopedia_lateralview.gui`
  - Search input wiring (`editbox_search_field`, `ontextedited`).

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\hud_bot.gui`
  - Searchbar/autocomplete patterns.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\outliner_settings.gui`
  - Stable checkbox row patterns.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\ui_library.gui`
  - Baseline tabs and control examples (`header_main_tabs`, `header_secondary_tabs`, `ranged_slider`).
  - Canonical dual-handle syntax example around lines `14492-14521` (`value_low`, `slider_low`, `dec_button_low`, `inc_button_low`, `mincap`, `maxcap`).

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\economy_lateralview.gui`
  - Real production slider usage (`economy_slider`, `onvaluechanged`, `onchangefinish`).

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\select_search_filter.gui`
  - Range-slider filtering pattern around lines `145-177` (`ranged_slider`, `value_low`, `onvaluechanged_low`, `onvaluechanged`).

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\setup_mercenary_requirements.gui`
  - Two production single-handle `ranged_slider` examples around lines `651-718` and `884-974`.
  - Useful for dynamic min/max/cap/step/value wiring and per-row +/- button enable/tooltip overrides.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\setup_condottieri.gui`
  - Two concise production `ranged_slider` examples around lines `420-487` and `525-592` (duration and cost modifier).
  - Good minimal pattern for dynamic bounds + `onvaluechanged` without extra custom logic.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\map_markers.gui`
  - Compact inline `ranged_slider` around lines `3932-4013`.
  - Shows custom +/- button skins inside slider for tight row layouts.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\import_export_lateralview.gui`
  - Narrow `ranged_slider` around lines `386-469` with tooltip and disabled slider +/- buttons (`dec_button = { button = {} }`, `inc_button = { button = {} }`).
  - Useful pattern when external +/- controls already exist in the row.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\diplomacy_lateralview.gui`
  - Multi-tab composition with `header_main_tabs` + secondary tab blocks.

- `C:\Steam\steamapps\common\Europa Universalis V\game\main_menu\gui\settings\setting_types.gui`
  - Native enum dropdown template and usage (`JominiSettingsEnumDropdown`, `dropDown`) around lines `3-100` and `618-635`.
  - Useful for dropdown active-item/item/list composition and selected index wiring.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\game_rules.gui`
  - In-game custom `dropDown` layout and behavior (`datamodel`, `onselectionchanged`, active-item/item composition) around lines `359-430`.

- `C:\Steam\steamapps\common\Europa Universalis V\game\in_game\gui\unit_viewer.gui`
  - Minimal functional `dropdown` binding with `selectedindex` + `onselectionchanged` around lines `382-393`.

## GlorpUI (Workshop 3612386197)

GlorpUI is useful for open/close flow and pause-menu injection examples.

- `C:\Steam\steamapps\workshop\content\3450310\3612386197\in_game\gui\glorp.gui`
  - Shared custom UI types in that mod.

- `C:\Steam\steamapps\workshop\content\3450310\3612386197\in_game\gui\glorpUI_window.gui`
  - GlorpUI-specific settings window implementation.

- `C:\Steam\steamapps\workshop\content\3450310\3612386197\in_game\gui\ingame_menu.gui`
  - GlorpUI pause-menu button injection.

- `C:\Steam\steamapps\workshop\content\3450310\3612386197\in_game\common\scripted_guis\glorpUI_custom_actions.txt`
  - GlorpUI scripted GUI toggle/action structure.

## Cheat Menu Pro (Workshop 3600272327)

- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\gui\sakuya_test.gui`
  - Main tab system (`header_main_tabs`, `button_main_tab_alt`, `GetVariableSystem.Set('sakuya_tabs', ...)`) around lines `143-177`.
  - Discrete numeric control via click modifiers (`left/right`, `ctrl`, `shift`) around lines `931-950`.
  - "Increase Monthly Income" amount selector ("Give me [number]" + slider-like control + confirm) around lines `4143-4475`.
  - This amount selector is a custom discrete slider implementation: state variable + step buttons + handle visuals.

- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\gui\sakuya_location.gui`
  - Secondary tab pattern via `sakuya_loc_tab` (`onclick` tab set + `visible` tab gating) around lines `75-140` and throughout content blocks.

- `C:\Steam\steamapps\workshop\content\3450310\3600272327\main_menu\common\scripted_guis\sakuya_cheat_sgui.txt`
  - Backend scripted GUI effects used by tab actions, numeric actions, and confirm actions.

- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\gui\sakuya_alpha.gui`
- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\gui\sakuya_beta.gui`
- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\gui\sakuya_beta_prov.gui`
  - Scope/domain-specific window variants and layout patterns.

- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\gui\sakuya_change_name.gui`
- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\gui\sakuya_change_name_char.gui`
  - Proven `editbox_single` + `ontextchanged` + `GetVariableSystem.Set(...)` examples.

- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\gui\scripted_widgets\sakuya_scripted_windows.txt`
  - Scripted widget mapping and spawn organization.

- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\gui\shared\sakuya_types.gui`
  - Shared reusable UI types/templates.

- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\common\on_actions\sakuya_mark_country_on_actions.txt`
- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\events\sakuya_mark_country_events.txt`
- `C:\Steam\steamapps\workshop\content\3450310\3600272327\in_game\events\sakuya_mark_character_events.txt`
  - Example of event/on_action orchestration that can complement scripted GUI operations.

## Skiar's Cheats Menu (Workshop 3600283823)

- `C:\Steam\steamapps\workshop\content\3450310\3600283823\in_game\gui\skiar_cheat_menu.gui`
  - Strong tab reference:
  - Main tabs via `header_main_tabs` + `GetVariableSystem.Set('cheat_tabs', ...)` around lines `205-472`.
  - Secondary tabs via `header_secondary_tabs` + `GetVariableSystem.Set('<section>_subtabs', ...)` around lines `490-560` (pattern repeats).
  - Numeric controls via paired +/- button rows and discrete value steps with scripted GUI datacontext (examples around lines `37566-37612` and `37871-37917`).
  - Consistent `ScriptedGui.IsShown/IsValid/Execute` row contract.

- `C:\Steam\steamapps\workshop\content\3450310\3600283823\in_game\gui\skiar_cheat_button_types.gui`
- `C:\Steam\steamapps\workshop\content\3450310\3600283823\in_game\gui\skiar_cheat_widget_button.gui`
- `C:\Steam\steamapps\workshop\content\3450310\3600283823\in_game\gui\skiar_cheat_button_placement.gui`
  - Reusable button styling and placement structure.

- `C:\Steam\steamapps\workshop\content\3450310\3600283823\in_game\gui\scripted_widgets\gui_mapping.txt`
  - Widget mapping pattern used by that mod's scripted GUI setup.

- `C:\Steam\steamapps\workshop\content\3450310\3600283823\in_game\common\scripted_guis\cheat_gold_button.txt`
  - Minimal clear scripted GUI contract example (`scope`, `is_shown`, `is_valid`, `effect`, `ai_is_valid`).

- `C:\Steam\steamapps\workshop\content\3450310\3600283823\in_game\common\scripted_guis\cheat_values_first_tab_button.txt`
  - Large scripted GUI backend for first-tab value actions (good for repetitive numeric effect wiring).

- `C:\Steam\steamapps\workshop\content\3450310\3600283823\in_game\common\scripted_guis\cheat_advances_research_button.txt`
  - Representative non-trivial stat/action button implementation.

- `C:\Steam\steamapps\workshop\content\3450310\3600283823\in_game\common\scripted_guis\cheat_remove_all_modifiers.txt`
  - Large batch-effect cleanup pattern.

## Notes on Sliders

- Cheat Menu Pro has a useful slider-like control in `sakuya_test.gui` (custom discrete implementation for monthly income amount).
- Skiar's menu uses discrete button matrices for numeric changes; it does not rely on native `ranged_slider` controls.
- Native `ranged_slider =` audit: 9 hits across 6 files.
- Native gameplay drag callbacks are only proven when `onvaluechanged` calls a native engine-backed data object method (`PossibleItem.OnChanged`, `CondottieriItem.OnDurationChanged`, `EconomyView.OnChangedCoinMinting`, etc.).
- No generic script-layer bridge for CMM-owned variables was found during testing:
  - `Player.MakeScope.GetVariable(...).SetValue`
  - `Player.MakeScope.GetVariable(...).SetValueArg`
  - `Player.MakeScope.GetVariable(...).SetValueFromWidget`
  - `PdxGuiWidget.GetValue`
  - `GetSliderValue(PdxGuiWidget.AccessSelf)`
  - all failed to parse in gameplay GUI/data binding.
- Hit-by-hit usefulness for CMM planning:
  - `ui_library.gui:14485` (`raw_text = "Ranged Slider:  ranged_slider = {}"`): not useful for implementation (label/example text only).
  - `ui_library.gui:14492-14521`: useful syntax reference for dual-handle sliders (`value_low`, `slider_low`, `dec_button_low`, `inc_button_low`), but this is UI-library demo content, not gameplay production wiring.
  - `select_search_filter.gui:145-177`: production dual-handle reference (`value_low` + `value`, `onvaluechanged_low` + `onvaluechanged`); also shows hiding built-in +/- buttons with empty button blocks. Useful for syntax/layout, but callbacks still target native objects.
  - `setup_mercenary_requirements.gui:651-718`: production single-handle baseline with dynamic `min/max/mincap/maxcap/step/wheelstep/value` and `onvaluechanged`. Useful for syntax/layout, but callbacks still target native objects.
  - `setup_mercenary_requirements.gui:884-974`: production single-handle pattern where `maxcap` is lower than `max` (`GetAvailableLimit` vs `GetMax`) plus per-button enable/tooltip gating (`CanDec`/`CanInc`). Useful for syntax/layout, but callbacks still target native objects.
  - `setup_condottieri.gui:420-487`: concise single-handle production pattern (duration slider) with minimal extra complexity. Useful for syntax/layout, but callbacks still target native objects.
  - `setup_condottieri.gui:525-592`: concise single-handle production pattern (cost modifier slider), same shape as duration. Useful for syntax/layout, but callbacks still target native objects.
  - `map_markers.gui:3932-4013`: compact inline slider pattern; demonstrates custom internal +/- skins (`minus_button.dds` / `plus_button.dds`) for tight rows. Useful for syntax/layout, but callbacks still target native objects.
  - `import_export_lateralview.gui:386-469`: hybrid pattern with external +/- step buttons and slider drag support; internal slider +/- intentionally disabled (`dec_button = { button = {} }`, `inc_button = { button = {} }`). Useful for syntax/layout, but callbacks still target native objects.
- Important non-hit reference for event contract:
  - `economy_lateralview.gui:71` defines `type economy_slider = ranged_slider`.
  - `economy_lateralview.gui:987-989`, `1144-1145`, `1779-1780`, `1988-1989` show `onvaluechanged` + `onchangefinish` usage in production wrappers.
  - These are useful to understand native callback shape, but not as proof that script-owned variables can read drag state.
- For CMM slider API planning, primary references should be:
  - Syntax/visual references: `setup_mercenary_requirements.gui:651-718`, `import_export_lateralview.gui:386-469`, `select_search_filter.gui:145-177`, `ui_library.gui:14492-14521`.
  - Native callback contract reference only: `economy_lateralview.gui` `economy_slider` usages.
  - Proven script-owned implementation direction: custom discrete controls like `sakuya_test.gui`, not native `ranged_slider`.
