"""Changing the theme or the language of windows that are ALREADY on screen, without a restart.

Two walks over the same tree. A widget that owns colours implements `set_palette(palette)`; a
widget that owns text implements `retranslate()`. Anything that implements neither is repainted by
swapping the marked stylesheet it carries, so a window nobody taught about themes still follows.
"""

from __future__ import annotations

from weakref import WeakSet

from PySide6.QtWidgets import QApplication, QWidget

from ..i18n import AUTO, setup
from . import theme
from .theme import Palette

# The tray icon has no parent window, so the widget walk cannot reach it. It signs up instead.
_extras: WeakSet = WeakSet()

_setting = "auto"
_palette: Palette = theme.LIGHT
_watching = False

_SHEETS = {
    theme.APP_MARKER: theme.stylesheet,
    theme.HUD_MARKER: theme.hud_stylesheet,
}


def register(participant: object) -> None:
    _extras.add(participant)


def palette() -> Palette:
    return _palette


def setting() -> str:
    return _setting


def _reachable() -> list[object]:
    """Materialised, not lazy: `set_palette` may add or drop children as it runs."""
    found: list[object] = []
    seen: set[int] = set()
    for top in QApplication.topLevelWidgets():
        for widget in (top, *top.findChildren(QWidget)):
            if id(widget) not in seen:
                seen.add(id(widget))
                found.append(widget)
    found.extend(_extras)
    return found


def apply_theme(mode_setting: str | None = None) -> Palette:
    """Resolve `auto | light | dark` and repaint every live window in the result."""
    global _setting, _palette
    if mode_setting is not None:
        _setting = mode_setting
    _palette = theme.palette(theme.resolve_mode(_setting))

    app = QApplication.instance()
    if app is None:
        return _palette
    app.setStyleSheet(theme.stylesheet(_palette))

    for obj in _reachable():
        setter = getattr(obj, "set_palette", None)
        if setter is not None:
            setter(_palette)
        elif isinstance(obj, QWidget):
            _reskin(obj)
    for top in QApplication.topLevelWidgets():
        top.update()

    _watch_system()
    return _palette


def _reskin(widget: QWidget) -> None:
    sheet = widget.styleSheet()
    for marker, build in _SHEETS.items():
        if sheet.startswith(marker):
            widget.setStyleSheet(build(_palette))
            return


def _watch_system() -> None:
    """`auto` has to keep meaning auto: follow the desktop when it flips after we started."""
    global _watching
    if _watching:
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        app.styleHints().colorSchemeChanged.connect(
            lambda _scheme: apply_theme() if _setting == "auto" else None
        )
        _watching = True
    except (AttributeError, RuntimeError):
        _watching = False


def apply_language(language: str) -> int:
    """Install the catalogue and retranslate whatever knows how; returns how many widgets did."""
    setup(language or AUTO)
    done = 0
    for obj in _reachable():
        retranslate = getattr(obj, "retranslate", None)
        if retranslate is not None:
            retranslate()
            done += 1
    return done


def retranslates(widget: QWidget) -> bool:
    """Whether the window this widget lives in updates its own text, or needs to be reopened."""
    window = widget.window()
    return window is not None and hasattr(window, "retranslate")
