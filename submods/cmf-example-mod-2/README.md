# Community Mod Menu Example Mod 2

Minimal test/integration mod for `community.mod.menu.dev`.

## What it does

- Registers settings under mod id `cmm_example2` into CMM.
- Uses derived localization keys (`<mod_id>_name` / `<mod_id>_desc`).
- Appends into CMM shared registration hook `cmm_on_mod_registration`.
- Applies setting changes immediately via scripted GUI callback `cmm_example2__<setting_id>_on_changed` (bool, slider, and dropdown).
