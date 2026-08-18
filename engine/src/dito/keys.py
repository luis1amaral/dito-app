"""The one table of bindable keys — see docs/armadilhas.md 2.7."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Key:
    name: str        # canonical, what the config file stores
    keysym: str      # X keysym name, verified against a live server by tests/test_keys.py
    qt_name: str     # attribute on Qt.Key, resolved by the UI so this module stays Qt-free
    label: str       # what the settings screen shows


def _function_keys() -> list[Key]:
    return [Key(f"f{n}", f"F{n}", f"Key_F{n}", f"F{n}") for n in range(1, 13)]


# Only keys that do not type a character: binding a letter globally swallows it everywhere.
BINDABLE: tuple[Key, ...] = (
    *_function_keys(),
    # The four below are why this table exists: capitalising the name gives Space, Print_Screen,
    # Page_Up and Page_Down, and none of those resolve to a keycode.
    Key("space", "space", "Key_Space", "Espaço"),
    Key("print_screen", "Print", "Key_Print", "Print Screen"),
    Key("page_up", "Prior", "Key_PageUp", "Page Up"),
    Key("page_down", "Next", "Key_PageDown", "Page Down"),
    Key("scroll_lock", "Scroll_Lock", "Key_ScrollLock", "Scroll Lock"),
    Key("pause", "Pause", "Key_Pause", "Pause"),
    Key("insert", "Insert", "Key_Insert", "Insert"),
    Key("menu", "Menu", "Key_Menu", "Menu"),
    Key("home", "Home", "Key_Home", "Home"),
    Key("end", "End", "Key_End", "End"),
)

BY_NAME: dict[str, Key] = {k.name: k for k in BINDABLE}
BY_QT: dict[str, Key] = {k.qt_name: k for k in BINDABLE}


def keysym(name: str) -> str | None:
    entry = BY_NAME.get((name or "").lower())
    return entry.keysym if entry else None


def label(name: str) -> str:
    entry = BY_NAME.get((name or "").lower())
    return entry.label if entry else (name or "").upper()


def is_bindable(name: str) -> bool:
    return (name or "").lower() in BY_NAME
