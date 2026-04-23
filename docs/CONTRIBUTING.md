# Community Mod Framework
![banner.png](/assets/images/cmf/CMF_Banner.png)

As the Community Mod Framework aims to support compatibility between different mods - sometimes you have to add something to it so your mods can integrate successfully.

# Philosophy

This framework aims to preserve base game behavior by default.
So if no other mod is used, the framework aims to be invisible to players.

The goal is to provide mods that make use of it, new ways to show content or hook into base game functionality.

## Contents
* [Ground Rules](#ground-rules)
* [File Naming](#file-naming)
* [Variable Prefixing](#variable-prefixing)
* [Documentation](#documentation)
* [Community Engagement](#community-engagement)

## Ground Rules

As a *community* mod framework - we endeavor to make the bar to accessibility as low as we can make it without compromising functionality. However, please remember that we are all volunteers doing this for fun so please be respectful of our time.

## File Naming

All CMF files should use the `cmf_` prefix. This prevents conflicts with base game files and other mods, and makes it easy to identify which files belong to the framework.

**Exception:** The Community Mod Menu (CMM) uses a `cmm_` prefix due to its scale and standalone-like nature. If a similarly large, self-contained feature were added to the framework, it could warrant its own prefix as well.

# Variable Prefixing

If you add a variable, list, effect, trigger, etc. for use in CMF, please prefix it using `cmf_`. This is to prevent conflicts with both base game and other mods.

It should be noted that, for functions which effectively add new features, we prefer generalized solutions which can be used by many different mods for consistent outcomes.

## Documentation

Documentation is maintained in two places:

- **[GitHub wiki](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki)** — Full detailed documentation. The wiki is a separate git repo (`community-mod-framework.wiki.git`) and can be cloned and edited like any repo.
- **Paradox wiki pages** (`docs/wiki/`) — Overview and quick reference pages in MediaWiki format for the [EU5 Paradox wiki](https://eu5.paradoxwikis.com/). These are less detailed and link to the GitHub wiki for full docs.

When adding or changing features, update both:
1. The GitHub wiki (detailed docs).
2. The Paradox wiki pages in `docs/wiki/` (quick reference).

## Pull Request Reviews

In addition to maintainer reviews, pull requests will receive an automated review from [Qodo](https://www.qodo.ai/). Most of its suggestions will be incorrect or irrelevant and should be ignored — however, it does occasionally catch real issues (mostly spelling mistakes). Do not feel obligated to address its comments unless they point out a genuine problem. In addition to pointing out fake errors, it will also miss real ones and is not a substitute for a human review.

## Community Engagement

The absolute best place to connect with the project is via the Discord server: [EU5 Mod Coop](https://discord.gg/aqAAcCZsY7)
