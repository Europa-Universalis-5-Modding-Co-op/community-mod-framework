"""Data models for CMM Visual Editor."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DropdownOption:
    index: int
    name: str
    desc: str = ""
    alias: str = ""


@dataclass
class ListField:
    field_id: str
    field_type: str  # "bool" | "dropdown" | "numeric" | "slider"
    name: str
    # bool
    default_value: Optional[int] = None
    # dropdown
    default_index: Optional[int] = None
    option_count: Optional[int] = None
    options: Optional[list] = None
    # numeric
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step_value: Optional[float] = None
    # alias
    alias: str = ""
    item_aliases: Optional[list] = None  # per-item aliases (list of str, one per item)
    # per-item field visibility
    disabled_items: Optional[list] = None  # 1-based item indices where this field is hidden
    # format display
    postfix: str = ""  # text appended after the value (e.g. "%")
    prefix: str = ""  # text prepended before the value (e.g. a color code)


@dataclass
class Setting:
    setting_id: str
    setting_type: str  # bool|button|numeric|slider|dropdown|text|list
    is_global: bool = False
    name: str = ""
    desc: str = ""
    # bool
    default_value: Optional[float] = None
    # button
    button_text: Optional[str] = None
    # numeric / slider
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step_value: Optional[float] = None
    display_format: Optional[str] = None
    # dropdown
    default_index: Optional[int] = None
    option_count: Optional[int] = None
    options: Optional[list] = None
    # text
    character_limit: Optional[int] = None
    quote_text: Optional[int] = None
    # list
    item_count: Optional[int] = None
    is_ordered: Optional[int] = None
    item_column_name: Optional[str] = None
    item_names: Optional[list] = None
    item_values: Optional[list] = None  # per-item scope values (e.g. "building_type:fine_cloth_guild")
    list_source: Optional[str] = None  # variable list name for cmm_register_settings_list_from_list
    fields: Optional[list] = None
    # callback
    on_changed_effect: Optional[str] = None
    pass_value_param: Optional[str] = None
    no_pass_value: Optional[bool] = None
    # reset
    no_reset: Optional[bool] = None
    # alias
    alias: str = ""
    alias_inverted: bool = False
    # scripted gui (is_shown / is_valid conditions)
    scripted_gui: Optional[bool] = None
    visible: Optional[str] = None
    enabled: Optional[str] = None


@dataclass
class Group:
    group_id: str
    name: str = ""
    desc: str = ""
    settings: list = field(default_factory=list)


@dataclass
class Tab:
    tab_id: str
    name: str = ""
    groups: list = field(default_factory=list)


@dataclass
class ModModel:
    mod_id: str = ""
    file_prefix: str = ""
    mod_name: str = ""
    mod_desc: str = ""
    metadata_name: str = ""
    metadata_id: str = ""
    metadata_version: str = "0.1"
    metadata_short_description: str = ""
    metadata_tags: list = field(default_factory=lambda: ["Utilities"])
    metadata_game_version: str = "1.1.*"
    noinspection: bool = False
    tabs: list = field(default_factory=list)


def model_to_dict(model: ModModel) -> dict:
    """Convert ModModel to a JSON-serializable dict."""

    def _setting(s: Setting) -> dict:
        d = {
            "setting_id": s.setting_id,
            "setting_type": s.setting_type,
            "is_global": s.is_global,
            "name": s.name,
            "desc": s.desc,
        }
        if s.setting_type == "bool":
            d["default_value"] = s.default_value
        elif s.setting_type == "button":
            d["button_text"] = s.button_text or ""
        elif s.setting_type in ("numeric", "slider"):
            d["default_value"] = s.default_value
            d["min_value"] = s.min_value
            d["max_value"] = s.max_value
            d["step_value"] = s.step_value
            if s.display_format:
                d["display_format"] = s.display_format
        elif s.setting_type == "dropdown":
            d["default_index"] = s.default_index
            d["option_count"] = s.option_count
            d["options"] = [
                {"index": o.index, "name": o.name, **({"desc": o.desc} if o.desc else {}), **({"alias": o.alias} if o.alias else {})}
                for o in (s.options or [])
            ]
        elif s.setting_type == "text":
            d["character_limit"] = s.character_limit
            d["quote_text"] = s.quote_text
        elif s.setting_type == "list":
            d["item_count"] = s.item_count
            d["is_ordered"] = s.is_ordered
            d["item_column_name"] = s.item_column_name or ""
            d["item_names"] = s.item_names or []
            d["item_values"] = s.item_values or []
            d["list_source"] = s.list_source or ""
            d["fields"] = [_list_field(f) for f in (s.fields or [])]
        if s.on_changed_effect:
            d["on_changed_effect"] = s.on_changed_effect
        if s.pass_value_param:
            d["pass_value_param"] = s.pass_value_param
        if s.no_pass_value:
            d["no_pass_value"] = s.no_pass_value
        if s.no_reset:
            d["no_reset"] = s.no_reset
        if s.alias:
            d["alias"] = s.alias
        if s.alias_inverted:
            d["alias_inverted"] = s.alias_inverted
        if s.scripted_gui:
            d["scripted_gui"] = s.scripted_gui
        if s.visible:
            d["visible"] = s.visible
        if s.enabled:
            d["enabled"] = s.enabled
        return d

    def _list_field(f: ListField) -> dict:
        d = {
            "field_id": f.field_id,
            "field_type": f.field_type,
            "name": f.name,
        }
        if f.alias:
            d["alias"] = f.alias
        if f.item_aliases and any(a for a in f.item_aliases):
            d["item_aliases"] = f.item_aliases
        if f.disabled_items:
            d["disabled_items"] = f.disabled_items
        if f.field_type == "bool":
            d["default_value"] = f.default_value
        elif f.field_type == "dropdown":
            d["default_index"] = f.default_index
            d["option_count"] = f.option_count
            d["options"] = [
                {"index": o.index, "name": o.name, **({"desc": o.desc} if o.desc else {}), **({"alias": o.alias} if o.alias else {})}
                for o in (f.options or [])
            ]
        elif f.field_type in ("numeric", "slider"):
            d["default_value"] = f.default_value
            d["min_value"] = f.min_value
            d["max_value"] = f.max_value
            d["step_value"] = f.step_value
        if f.postfix:
            d["postfix"] = f.postfix
        if f.prefix:
            d["prefix"] = f.prefix
        return d

    return {
        "mod_id": model.mod_id,
        "file_prefix": model.file_prefix,
        "mod_name": model.mod_name,
        "mod_desc": model.mod_desc,
        "metadata_name": model.metadata_name,
        "metadata_id": model.metadata_id,
        "metadata_version": model.metadata_version,
        "metadata_short_description": model.metadata_short_description,
        "metadata_tags": model.metadata_tags,
        "metadata_game_version": model.metadata_game_version,
        "noinspection": model.noinspection,
        "tabs": [
            {
                "tab_id": t.tab_id,
                "name": t.name,
                "groups": [
                    {
                        "group_id": g.group_id,
                        "name": g.name,
                        "desc": g.desc,
                        "settings": [_setting(s) for s in g.settings],
                    }
                    for g in t.groups
                ],
            }
            for t in model.tabs
        ],
    }


def dict_to_model(data: dict) -> ModModel:
    """Convert a JSON dict back to a ModModel."""

    def _parse_option(o: Any) -> DropdownOption:
        return DropdownOption(index=o["index"], name=o.get("name", ""), desc=o.get("desc", ""), alias=o.get("alias", ""))

    def _parse_list_field(f: dict) -> ListField:
        return ListField(
            field_id=f["field_id"],
            field_type=f["field_type"],
            name=f.get("name", ""),
            default_value=f.get("default_value"),
            default_index=f.get("default_index"),
            option_count=f.get("option_count"),
            options=[_parse_option(o) for o in f.get("options", [])],
            min_value=f.get("min_value"),
            max_value=f.get("max_value"),
            step_value=f.get("step_value"),
            alias=f.get("alias", ""),
            item_aliases=f.get("item_aliases"),
            disabled_items=f.get("disabled_items"),
            postfix=f.get("postfix", ""),
            prefix=f.get("prefix", ""),
        )

    def _parse_setting(s: dict) -> Setting:
        return Setting(
            setting_id=s["setting_id"],
            setting_type=s["setting_type"],
            is_global=s.get("is_global", False),
            name=s.get("name", ""),
            desc=s.get("desc", ""),
            default_value=s.get("default_value"),
            button_text=s.get("button_text"),
            min_value=s.get("min_value"),
            max_value=s.get("max_value"),
            step_value=s.get("step_value"),
            display_format=s.get("display_format"),
            default_index=s.get("default_index"),
            option_count=s.get("option_count"),
            options=[_parse_option(o) for o in s.get("options", [])],
            character_limit=s.get("character_limit"),
            quote_text=s.get("quote_text"),
            item_count=s.get("item_count"),
            is_ordered=s.get("is_ordered"),
            item_column_name=s.get("item_column_name"),
            item_names=s.get("item_names"),
            item_values=s.get("item_values"),
            list_source=s.get("list_source"),
            fields=[_parse_list_field(f) for f in s.get("fields", [])],
            on_changed_effect=s.get("on_changed_effect"),
            pass_value_param=s.get("pass_value_param"),
            no_pass_value=s.get("no_pass_value"),
            no_reset=s.get("no_reset"),
            alias=s.get("alias", ""),
            alias_inverted=s.get("alias_inverted", False),
            scripted_gui=s.get("scripted_gui"),
            visible=s.get("visible"),
            enabled=s.get("enabled"),
        )

    return ModModel(
        mod_id=data.get("mod_id", ""),
        file_prefix=data.get("file_prefix", ""),
        mod_name=data.get("mod_name", ""),
        mod_desc=data.get("mod_desc", ""),
        metadata_name=data.get("metadata_name", ""),
        metadata_id=data.get("metadata_id", ""),
        metadata_version=data.get("metadata_version", "0.1"),
        metadata_short_description=data.get("metadata_short_description", ""),
        metadata_tags=data.get("metadata_tags", ["Utilities"]),
        metadata_game_version=data.get("metadata_game_version", "1.1.*"),
        noinspection=data.get("noinspection", False),
        tabs=[
            Tab(
                tab_id=t["tab_id"],
                name=t.get("name", ""),
                groups=[
                    Group(
                        group_id=g["group_id"],
                        name=g.get("name", ""),
                        desc=g.get("desc", ""),
                        settings=[_parse_setting(s) for s in g.get("settings", [])],
                    )
                    for g in t.get("groups", [])
                ],
            )
            for t in data.get("tabs", [])
        ],
    )
