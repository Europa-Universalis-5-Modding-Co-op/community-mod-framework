# Community Mod Framework (CMF)
![banner](assets/images/cmf/banner.png)

A shared mod framework and menu for **Europa Universalis 5**. Includes the Community Mod Menu (CMM), custom alerts, action bar elements, and more.

## Contents
* [Features](#features)
* [Getting Started](#getting-started)
* [Philosophy](#philosophy)
* [Contributors](#contributors)

## Steam Page
https://steamcommunity.com/sharedfiles/filedetails/?id=3605358788

## Features

- **[Community Mod Menu (CMM)](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki/Community-Mod-Menu)** — Shared in-game settings UI for mods (toggles, sliders, dropdowns, buttons, text inputs, settings lists). Includes a visual editor tool.
- **[Custom Alerts](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki/Custom-Alerts)** — Dynamic, dismissable notifications in the in-game alert bar.
- **[Action Bar](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki/Action-Bar)** — Custom action bar with configurable buttons.
- **[is_host Trigger](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki/is_host-Trigger)** — Check if the current country is controlled by the host player.
- **[cmf_suppress Effect](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki/Warning-Suppression)** — Suppress "used but never set" and "set but never used" engine warnings.
- **[Community Mod Toolkit (CMT)](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit)** — A companion set of development tools, such as a mod template, workshop uploader and mod translator.

## Getting Started

To set this mod as a dependency to your own mod, you will need to add this to your `metadata.json` file:
```json
  "relationships" : [
    {
      "rel_type" : "dependency",
      "id" : "community_mod_framework",
      "display_name" : "Community Mod Framework",
      "resource_type" : "mod",
      "version" : "2.*"
    }
  ]
```
**Also remember to add the mod to your required items on your own mods steam page.**

See the [GitHub wiki](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki) for full documentation on setting up and using each feature, or the [EU5 Paradox wiki](https://eu5.paradoxwikis.com/Community_Mod_Framework) which serves as quick reference.

# Philosophy

This framework aims to preserve base game behavior by default.
So if no other mod is used, the framework aims to be invisible to players.

The goal is to provide mods that make use of it, new ways to show content or hook into base game functionality.

## Links

- [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3605358788)
- [Example Mod](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/tree/main/submods/cmf-example-mod)
- [Community Mod Toolkit](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit)
- [Contributing](docs/CONTRIBUTING.md)
- [Discord](https://discord.gg/aqAAcCZsY7)

## Contributors
- [Bahmut](https://steamcommunity.com/id/Bahmut/)
- [Conner](https://steamcommunity.com/id/ARealConner/)
- [Pickle](https://steamcommunity.com/id/pickled-dev)

## License

ISC. See [LICENSE](LICENSE).
