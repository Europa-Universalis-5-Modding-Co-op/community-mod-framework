# Community Mod Framework
![banner.png](/assets/images/cmf/banner.png)

As the Community Mod Framework aims to support compatibility between different mods - sometimes you have to add something to it so your mods can integrate successfully.

# Philosophy

This framework aims to preserve base game behavior by default.
So if no other mod is used, the framework aims to be invisible to players.

The goal is to provide mods that make use of it, new ways to show content or hook into base game functionality.

## Contents
* [Ground Rules](#ground-rules)
* [File Naming](#file-naming)
* [Variable Prefixing](#variable-prefixing)
* [Community Engagement](#community-engagement)

## Ground Rules

As a *community* mod framework - we endeavor to make the bar to accessibility as low as we can make it without compromising functionality. However, please remember that we are all volunteers doing this for fun so please be respectful of our time.

## File Naming

All CMF files should use the `cmf_` prefix. This prevents conflicts with base game files and other mods, and makes it easy to identify which files belong to the framework.

**Exception:** The Community Mod Menu (CMM) uses a `cmm_` prefix due to its scale and standalone-like nature. If a similarly large, self-contained feature were added to the framework, it could warrant its own prefix as well.

# Variable Prefixing

If you add a variable, list, effect, trigger, etc. for use in CMF, please prefix it using `cmf_`. This is to prevent conflicts with both base game and other mods.

It should be noted that, for functions which effectively add new features, we prefer generalized solutions which can be used by many different mods for consistent outcomes.

## Community Engagement

The absolute best place to connect with the project is via the Discord server: [Europa Universalis V](https://discord.gg/aUV49QbqYm)
