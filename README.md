# Community Mod Framework (CMF)
![banner](assets/images/cmf/banner.png)

A shared mod framework and menu for **Europa Universalis 5**. Includes the Community Mod Menu (CMM), custom alerts, action bar elements, and more.

## Contents
* [Features](#features)
* [Documentation](#documentation)
* [Setting Dependency](#setting-dependency)
* [Philosophy](#philosophy)
* [Contributors](#contributors)

## Steam Page
https://steamcommunity.com/sharedfiles/filedetails/?id=3605358788

## Features

- **Community Mod Menu (CMM)** — Shared in-game settings UI for mods (toggles, sliders, dropdowns, buttons, text inputs, settings lists).
- **Custom Alerts** — Dynamic, dismissable notifications in the in-game alert bar.
- **Action Bar Elements** — Custom buttons in the game's action bar.
- **is_host Trigger** — Check if the current country is controlled by the host player.
- **[Community Mod Toolkit (CMT)](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit)** — A companion set of development tools, such as a Workshop uploader and mod translator.

## Documentation

- **[GitHub Wiki](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki)** — Full documentation.
- **[EU5 Paradox Wiki](https://eu5.paradoxwikis.com/Community_Mod_Framework)** — Overview and quick reference.

## Setting Dependency

To set this mod as a dependency to your own mod, you will need to add this to your `metadata.json` file:
```json
  "relationships" : [
    {
      "rel_type" : "dependency",
      "id" : "community.mod.framework",
      "display_name" : "Community Mod Framework",
      "resource_type" : "mod",
      "version" : "2.*"
    }
  ]
```
**Also remember to add the mod to your required items on your own mods steam page.**

# Philosophy

This framework aims to preserve base game behavior by default.
So if no other mod is used, the framework aims to be invisible to players.

The goal is to provide mods that make use of it, new ways to show content or hook into base game functionality.

## Links

- [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3605358788)
- [Example Mod](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/tree/main/submods/cmf-example-mod)
- [Community Mod Toolkit](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit) — Development tools (visual editor, upload, translation)
- [Contributing](docs/CONTRIBUTING.md)
- [Discord](https://discord.gg/aUV49QbqYm)

## Contributors
- [Bahmut](https://steamcommunity.com/id/Bahmut/)
- [Conner](https://steamcommunity.com/id/ARealConner/)
- [Pickle](https://steamcommunity.com/id/pickled-dev)

## License

ISC. See [LICENSE](LICENSE).
