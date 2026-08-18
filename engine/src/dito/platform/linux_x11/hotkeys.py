"""Global hotkeys on X11 — the events lie, the keymap does not. See docs/armadilhas.md 2."""

from __future__ import annotations

import threading

from ..hotkeys_core import GRACE_S, POLL_S, Binding, GrabDenied, Mode
from ..hotkeys_core import HotkeyManager as _HotkeyManager

__all__ = [
    "GRACE_S", "POLL_S", "Binding", "GrabDenied", "Mode",
    "KeyState", "KeyGrabber", "HotkeyManager",
]


def _keysym_name(key: str) -> str:
    """"f9" -> "F9", "scroll_lock" -> "Scroll_Lock". X keysym names are Capitalised_Like_This."""
    return "_".join(part.capitalize() for part in key.split("_"))


class KeyState:
    """Physical key state, on our own X connection behind one lock (armadilhas 2.3)."""

    def __init__(self) -> None:
        from Xlib import display

        self._display = display.Display()
        self._lock = threading.Lock()
        self._codes: dict[str, int] = {}

    def keycode(self, key: str) -> int | None:
        if key in self._codes:
            return self._codes[key]
        from Xlib import XK

        keysym = XK.string_to_keysym(_keysym_name(key))
        if not keysym:
            return None
        with self._lock:
            code = self._display.keysym_to_keycode(keysym)
        if code:
            self._codes[key] = code
        return code or None

    def is_down(self, key: str) -> bool:
        code = self.keycode(key)
        if not code:
            return False
        with self._lock:
            bits = self._display.query_keymap()
        return bool(bits[code >> 3] & (1 << (code & 7)))

    def close(self) -> None:
        try:
            self._display.close()
        except Exception:
            pass


class KeyGrabber:
    """Consumes keys so they never reach the focused window (armadilhas 2.6)."""

    # See docs/armadilhas.md 2.8: NumLock (Mod2), CapsLock (Lock), ScrollLock (Mod5), all combos.
    _IGNORED = (0, 0x02, 0x10, 0x02 | 0x10, 0x40, 0x40 | 0x02, 0x40 | 0x10, 0x40 | 0x02 | 0x10)

    def __init__(self, state: KeyState) -> None:
        from Xlib import X, display

        self._X = X
        self._display = display.Display()
        self._root = self._display.screen().root
        self._state = state
        self._grabbed: list[int] = []
        self._lock = threading.Lock()

    def grab(self, key: str) -> None:
        code = self._state.keycode(key)
        if not code:
            raise GrabDenied(f"unknown key: {key}")
        from Xlib import error

        catcher = error.CatchError(error.BadAccess)
        with self._lock:
            for mods in self._IGNORED:
                self._root.grab_key(
                    code, mods, True,
                    self._X.GrabModeAsync, self._X.GrabModeAsync,
                    onerror=catcher,
                )
            self._display.sync()
            if catcher.get_error():
                for mods in self._IGNORED:
                    self._root.ungrab_key(code, mods)
                self._display.flush()
                raise GrabDenied(f"«{key.upper()}» already belongs to another program")
            self._grabbed.append(code)

    def ungrab_all(self) -> None:
        with self._lock:
            for code in self._grabbed:
                for mods in self._IGNORED:
                    try:
                        self._root.ungrab_key(code, mods)
                    except Exception:
                        pass
            self._grabbed.clear()
            try:
                self._display.flush()
            except Exception:
                pass

    def close(self) -> None:
        self.ungrab_all()
        try:
            self._display.close()
        except Exception:
            pass


class HotkeyManager(_HotkeyManager):
    """The shared machine, wired to X11: own connection for state, XGrabKey for consuming."""

    def _make_state(self) -> KeyState:
        return KeyState()

    def _make_grabber(self, state: KeyState) -> KeyGrabber:
        return KeyGrabber(state)

    def _make_listener(self, on_press, on_release):
        from pynput import keyboard

        return keyboard.Listener(on_press=on_press, on_release=on_release)
