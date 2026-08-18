"""Global hotkeys on Windows: GetAsyncKeyState for truth, the low-level hook for consuming.

The hook path is not the Linux path: `suppress_event()` aborts pynput's own conversion, so a
consumed key never reaches `on_press`. See docs/armadilhas.md 2.12.
"""

from __future__ import annotations

import ctypes
import queue
import threading

from ..hotkeys_core import GRACE_S, POLL_S, Binding, GrabDenied, Mode
from ..hotkeys_core import HotkeyManager as _HotkeyManager

__all__ = [
    "GRACE_S", "POLL_S", "Binding", "GrabDenied", "Mode",
    "KeyState", "KeySuppressor", "HotkeyManager", "vk_for",
]

_WM_KEYDOWN = 0x0100
_WM_SYSKEYDOWN = 0x0104
_DOWN_MESSAGES = (_WM_KEYDOWN, _WM_SYSKEYDOWN)

_DOWN_BIT = 0x8000
_NO_MAPPING = -1

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
_user32.VkKeyScanW.restype = ctypes.c_short


def vk_for(key: str) -> int | None:
    """`"f9"` -> 120. pynput names the special keys; single characters go through the layout."""
    from pynput import keyboard

    special = getattr(keyboard.Key, key, None)
    vk = getattr(getattr(special, "value", None), "vk", None)
    if vk:
        return vk
    if len(key) != 1:
        return None
    # KeyCode.from_char() leaves vk None on Windows, so ask the active keyboard layout instead.
    scan = _user32.VkKeyScanW(key)
    return None if scan == _NO_MAPPING else scan & 0xFF


class KeyState:
    """Physical key state. The hook wins where it has looked; GetAsyncKeyState covers the rest."""

    def __init__(self) -> None:
        self._vks: dict[str, int | None] = {}
        self._seen: dict[int, bool] = {}
        self._lock = threading.Lock()

    def vk(self, key: str) -> int | None:
        if key not in self._vks:
            self._vks[key] = vk_for(key)
        return self._vks[key]

    def note(self, vk: int, down: bool) -> None:
        """What the hook saw. See docs/armadilhas.md 2.13: a key we swallow never reaches
        GetAsyncKeyState, so on a grabbed key that call answers False the whole time it is held."""
        with self._lock:
            self._seen[vk] = down

    def is_down(self, key: str) -> bool:
        vk = self.vk(key)
        if not vk:
            return False
        with self._lock:
            seen = self._seen.get(vk)
        if seen is not None:
            return seen
        # Never passed under the hook — held from before the listener started, or not ours.
        return bool(_user32.GetAsyncKeyState(vk) & _DOWN_BIT)

    def close(self) -> None:
        self._vks.clear()
        with self._lock:
            self._seen.clear()


class KeySuppressor:
    """Which keys the hook must swallow; the hook itself lives in the listener's event filter."""

    def __init__(self, state: KeyState) -> None:
        self._state = state
        self._by_vk: dict[int, str] = {}
        self._lock = threading.Lock()

    def grab(self, key: str) -> None:
        vk = self._state.vk(key)
        if not vk:
            raise GrabDenied(f"unknown key: {key}")
        with self._lock:
            self._by_vk[vk] = key

    def ungrab_all(self) -> None:
        with self._lock:
            self._by_vk.clear()

    def key_of(self, vk: int) -> str | None:
        with self._lock:
            return self._by_vk.get(vk)

    def close(self) -> None:
        self.ungrab_all()


class HotkeyManager(_HotkeyManager):
    """The shared machine, wired to Windows: the event filter both consumes and feeds the queue."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._events: queue.Queue[tuple[str, bool] | None] = queue.Queue()
        self._pump: threading.Thread | None = None

    def _make_state(self) -> KeyState:
        return KeyState()

    def _make_grabber(self, state: KeyState) -> KeySuppressor:
        return KeySuppressor(state)

    def _make_listener(self, on_press, on_release):
        from pynput import keyboard

        holder: dict[str, object] = {}

        # See docs/armadilhas.md 2.7: the hook blocks while this runs, so it only records.
        def event_filter(msg, data):
            down = msg in _DOWN_MESSAGES
            state = self._state
            if state is not None:
                state.note(data.vkCode, down)

            suppressor = self._grabber
            listener = holder.get("listener")
            if suppressor is None or listener is None:
                return True
            key = suppressor.key_of(data.vkCode)
            if key is None:
                return True
            if down:
                self._events.put((key, True))
            listener.suppress_event()
            return True

        listener = keyboard.Listener(
            on_press=on_press, on_release=on_release, win32_event_filter=event_filter
        )
        holder["listener"] = listener
        return listener

    def start(self) -> None:
        super().start()
        self._pump = threading.Thread(target=self._drain, daemon=True, name="dito-keys")
        self._pump.start()

    def _drain(self) -> None:
        while True:
            item = self._events.get()
            if item is None:
                return
            key, pressed = item
            self._on_key_name(key, pressed)

    def stop(self) -> None:
        super().stop()
        pump, self._pump = self._pump, None
        if pump is not None and pump.is_alive():
            self._events.put(None)
            pump.join(timeout=1.0)
