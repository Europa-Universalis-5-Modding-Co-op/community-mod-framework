# Community Mod Framework
![banner.png](/docs/banner.png)

The Community Mod Framework aims to support compatibility between different mods.

## Steam Page
TBD

## Contents
* [Philosophy](#philosophy)
* [Setting Dependency](#setting-dependency)
* [GUI Features](#gui-features)
  * [Custom Alerts](#custom-alerts)
* [Script Features](#script-features)
  * [Fixing Variable Errors](#fixing-variable-errors)
* [Contributors](#contributors)

# Philosophy

This framework aims to preserve base game behavior by default.
So if no other mod is used, the framework aims to be invisible to players.

The goal is to provide mods that make use of it, new ways to show content or hook into base game functionality.

# Setting Dependency

To set this mod as a dependency to your own mod, you will need to add this to your `metadata.json` file:
```
  "relationships" : [
    {
      "rel_type" : "dependency",
      "id" : "com.github.Europa-Universalis-5-Modding-Co-op.community-mod-framework",
      "display_name" : "Community Mod Framework",
      "resource_type" : "mod",
      "version" : "1.*"
    }
  ]
```
**Also remember to add the mod to your required items on your own mods steam page.**

# GUI Features

## Custom Alerts
You can create and show custom alerts. This is achieved through a combination of localization keys and a scripted gui.

### Setup
Custom alerts require a set of localization keys.

The First and most important is the so-called root localization key.
It is self-referential, as in both the key and the text are the **same**.
Here are all needed localization keys:
- `<root_loc_key>` - This is the internal alert name referenced by `cmf_show_alert`
- `<root_loc_key>_color` - This is the alert color (`blue`/`orange`/`red`/`red_war`/`black`/`yellow`/`green`/`purple`)
- `<root_loc_key>_icon` - This should be a text icon which is used as the icon for the alert
- `<root_loc_key>_name` - This is the name of the alert, which is shown in the tooltip header
- `<root_loc_key>_tooltip` - This is the tooltip text of the alert, which is shown in the tooltip body

Here is an example:
```yaml
l_english:
 cmf_alert_example: "cmf_alert_example"
 cmf_alert_example_color: "orange"
 cmf_alert_example_icon: "@advance!"
 cmf_alert_example_name: "Some Alert"
 cmf_alert_example_tooltip: "This is a dynamic custom alert."
```

Next, we need a scripted gui with the **same** name as the root localization key.
The scripted gui runs when the alert is clicked:
```
cmf_alert_example = {
    # The player country will be set as root
    scope = country

    effect = {
        # This effect will be run when the alert is clicked
    }
}
```

### Usage

> **NOTE** These commands need to run in the country scope

To show a custom alert, the `cmf_show_alert` effect is used:
```
cmf_show_alert = {
    alert = cmf_alert_example
}
```
The alert can be removed using the `cmf_remove_alert` effect:
```
cmf_remove_alert = {
    alert = cmf_alert_example
}
```
This will remove the alert from the alert bar.

Finally, to check whether an alert is shown the `cmf_is_alert_shown` can be used:
```
cmf_is_alert_shown = {
    alert = cmf_alert_example
}
```

### Notes
The user can remove alerts by themself if they right-click the alert.
If they do that, it works the same as if the `cmf_remove_alert` effect was run.

When an alert is clicked, the corresponding scripted gui is executed.

Also when an alert is clicked the gui variable `cmf_active_alert` is set to the root loc key.
This can be helpful if you want to open a custom window or otherwise react to clicking the alert in the gui.
You can check for this variable using the `VariableSystem`.
Here is an example which checks for the example alert defined above:
```
visible = "[GetVariableSystem.HasValue('cmf_active_alert', 'cmf_alert_example')]"
```

# Script Features

## Fixing Variable Errors
When you are using a variable only in the GUI or in localizations, the game creates errors and spams the error log.
To avoid this, there is a helper scripted effect in CMF that suppresses these types of errors.
```
fix_variable_error = {
	variable = variable_or_flag_name
}
```
Usage examples can be found [here](in_game/events/cmf_hidden.txt).

**NOTE**: This works for both **variables** and **flags**.

# Contributors
- [Bahmut](https://steamcommunity.com/id/Bahmut/)