"""The "press a key" field.

The tricky part is not reading a key press — it is reading one while a global listener is holding
that same key. The sequence matters:

  1. suspend the global backend (it keeps its thread and simply discards; destroying a pynput
     Listener and rebuilding it is what leaves a key stuck down);
  2. grab the keyboard at the *application* level, so the next press belongs to this widget;
  3. resolve the key to the canonical name the backend uses, not to the character Qt reports —
     the backend matches on the X keysym, and Qt's text() is empty for the keys worth binding;
  4. validate: no bare modifier, no key already bound to another Dito action, and then an actual
     test grab, because X has no API for "who owns this key" and attempting it IS the test;
  5. release and resume.

Only keys that do not type a character are offered. Binding a letter globally would swallow it
everywhere, which is a trap rather than a feature.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPushButton

from .theme import Palette, Radius, Size, Space, Type

# Qt key -> the canonical name shared by the config file, pynput and the X keysym lookup.
BINDABLE: dict[Qt.Key, str] = {
    **{getattr(Qt.Key, f"Key_F{n}"): f"f{n}" for n in range(1, 13)},
    Qt.Key.Key_ScrollLock: "scroll_lock",
    Qt.Key.Key_Pause: "pause",
    Qt.Key.Key_Insert: "insert",
    Qt.Key.Key_Print: "print_screen",
    Qt.Key.Key_Menu: "menu",
    Qt.Key.Key_Home: "home",
    Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "page_up",
    Qt.Key.Key_PageDown: "page_down",
    Qt.Key.Key_Space: "space",
}

MODIFIERS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt,
    Qt.Key.Key_Meta, Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock,
}


def pretty(key: str) -> str:
    return {
        "scroll_lock": "Scroll Lock",
        "print_screen": "Print Screen",
        "page_up": "Page Up",
        "page_down": "Page Down",
        "space": "Espaço",
        "menu": "Menu",
        "insert": "Insert",
        "home": "Home",
        "end": "End",
        "pause": "Pause",
    }.get(key, key.upper())


class KeyCapture(QPushButton):
    """A button that becomes a key recorder when clicked."""

    captured = Signal(str)
    rejected = Signal(str)

    def __init__(
        self,
        key: str,
        palette: Palette,
        validate: Callable[[str], str | None] | None = None,
        on_capture_start: Callable[[], None] | None = None,
        on_capture_end: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette
        self._key = key
        self._validate = validate or (lambda _k: None)
        self._on_start = on_capture_start or (lambda: None)
        self._on_end = on_capture_end or (lambda: None)
        self._capturing = False

        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(Size.CONTROL_H)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._restyle()
        self.clicked.connect(self.begin_capture)
        self._refresh()

    # ---- state -----------------------------------------------------------------------

    @property
    def key(self) -> str:
        return self._key

    def set_key(self, key: str) -> None:
        self._key = key
        self._refresh()

    def _refresh(self) -> None:
        self.setText("pressione uma tecla…" if self._capturing else pretty(self._key))
        self._restyle()

    def _restyle(self) -> None:
        p = self._palette
        border = p.primary if self._capturing else p.border_strong
        weight = Type.SEMIBOLD if self._capturing else Type.MEDIUM
        self.setStyleSheet(
            f"QPushButton {{ min-height: {Size.CONTROL_H}px; padding: 0 {Space.LG}px;"
            f" border: {2 if self._capturing else 1}px solid {border};"
            f" border-radius: {Radius.CONTROL}px; background: {p.surface};"
            f" color: {p.text_primary}; font-weight: {weight};"
            f" font-family: {Type.MONO}; }}"
            f"QPushButton:hover {{ background: {p.surface_alt}; }}"
        )

    # ---- capture ---------------------------------------------------------------------

    def begin_capture(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self._on_start()
        self.grabKeyboard()
        self._refresh()

    def _end_capture(self) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self.releaseKeyboard()
        self._on_end()
        self._refresh()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        if not self._capturing:
            super().keyPressEvent(event)
            return

        qt_key = Qt.Key(event.key())

        if qt_key == Qt.Key.Key_Escape:
            self._end_capture()
            return
        if qt_key in MODIFIERS:
            # Waiting rather than rejecting: reaching for Ctrl+F9 presses Ctrl first, and
            # complaining about it would be nagging the user for typing correctly.
            return

        name = BINDABLE.get(qt_key)
        if name is None:
            self.rejected.emit(
                "essa tecla não serve como atalho global — use F1–F12, Scroll Lock, Pause, "
                "Insert ou Espaço"
            )
            return

        problem = self._validate(name)
        if problem:
            self.rejected.emit(problem)
            return

        self._key = name
        self._end_capture()
        self.captured.emit(name)

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Clicking away cancels. A widget left holding the keyboard grab would eat every
        keystroke in the app."""
        self._end_capture()
        super().focusOutEvent(event)
