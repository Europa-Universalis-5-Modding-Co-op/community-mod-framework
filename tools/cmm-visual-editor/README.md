# CMM Visual Editor

Visual editor for creating and managing EU5 Community Mod Menu (CMM) settings integrations.

## Development Setup

```bash
cd tools/cmm-visual-editor
pip install -e .
cmm-visual-editor
```

`pip install -e .` only needs to be run once. After that, `cmm-visual-editor` launches the tool. Changes to the source files take effect immediately without reinstalling.

Alternatively, you can run the module directly after install:

```bash
python -m cmm_visual_editor
```

## How It Works

### Generated Files

The tool generates 5 files into a mod directory, where `<prefix>` is the file prefix you choose (defaults to your mod ID):

| File | Path | Content |
|------|------|---------|
| On Action | `in_game/common/on_action/<prefix>_menu_on_action.txt` | CMM registration hook |
| Effects | `in_game/common/scripted_effects/<prefix>_menu_effects.txt` | Setting registrations + text callbacks |
| Scripted GUIs | `in_game/common/scripted_guis/<prefix>_menu_scripted_gui.txt` | Setting change callbacks |
| Localization | `main_menu/localization/english/<prefix>_menu_l_english.yml` | All display strings |
| Metadata | `.metadata/metadata.json` | Mod metadata with CMM dependency |

File names include `_menu` to avoid conflicts with a mod's own effect/GUI/localization files.

### Callback Preservation

When saving to a mod directory that already has generated files:
- **Scripted GUI callbacks** (`_on_changed` blocks): existing callbacks are preserved. Only newly added settings get template callbacks appended.
- **Text effect callbacks**: existing text `_on_changed` effects are preserved. The registration block is always regenerated.
- **On action, localization, metadata**: always fully regenerated (these contain no custom logic).

This means you can add custom logic to your callbacks and re-save from the tool without losing it.

### Architecture

- Python stdlib `http.server` (zero external dependencies)
- Vue 3 SPA served as static files
- All code generation runs server-side in Python, mirrored client-side in JS for live preview
- Parser reads existing mod files via regex-based extraction of `cmm_register_*` blocks
