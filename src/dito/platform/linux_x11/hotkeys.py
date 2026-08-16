"""Global hotkeys on X11 — the events lie, the keymap does not. See docs/armadilhas.md 2."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

GRACE_S = 0.30
POLL_S = 0.05


class Mode(StrEnum):
    HOLD = "hold"       # push-to-talk: down starts, sustained up ends
    TOGGLE = "toggle"   # meeting: one press starts, the next stops


@dataclass
class Binding:
    name: str
    key: str
    mode: Mode


class GrabDenied(RuntimeError):
    """Someone else owns this key — armadilhas 2.6: attempting the grab is the only test."""


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


class HotkeyManager:
    """Raw key events into start/stop, off the event thread — armadilhas 2.7 says why."""

    def __init__(
        self,
        on_start: Callable[[str], None],
        on_stop: Callable[[str], None],
        grab: bool = True,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self.on_start = on_start
        self.on_stop = on_stop
        self.want_grab = grab
        self._log = on_log or (lambda _m: None)

        self._bindings: dict[str, Binding] = {}
        self._by_key: dict[str, Binding] = {}
        self._active: str | None = None
        self._watching = False
        self._paused = False
        self._listener = None
        self._state: KeyState | None = None
        self._grabber: KeyGrabber | None = None
        self._lock = threading.Lock()
        self._watcher: threading.Thread | None = None
        self._shutting_down = False
        # Toggles waiting for the key to come physically up — see docs/armadilhas.md 2.11.
        self._held: set[str] = set()

    # ---- bindings -------------------------------------------------------------------

    def bind(self, name: str, key: str, mode: Mode) -> None:
        binding = Binding(name=name, key=key.lower(), mode=mode)
        self._bindings[name] = binding
        self._by_key[binding.key] = binding

    def conflicts(self, key: str, ignoring: str | None = None) -> str | None:
        """Which of our own actions owns this key — a clearer message than `BadAccess`."""
        key = key.lower()
        for name, binding in self._bindings.items():
            if name != ignoring and binding.key == key:
                return name
        return None

    # ---- lifecycle ------------------------------------------------------------------

    def start(self) -> None:
        from pynput import keyboard

        self._shutting_down = False
        self._state = KeyState()
        self._apply_grabs()

        def on_press(key):
            self._on_event(key, pressed=True)

        def on_release(key):
            self._on_event(key, pressed=False)

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        """Order matters: the watcher is drained first — see docs/armadilhas.md 2.9."""
        self._shutting_down = True
        watcher, self._watcher = self._watcher, None
        if watcher is not None and watcher.is_alive():
            watcher.join(timeout=GRACE_S + 1.0)

        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._grabber is not None:
            self._grabber.close()
            self._grabber = None
        if self._state is not None:
            self._state.close()
            self._state = None

    def pause(self) -> None:
        """The listener stays alive and discards — see docs/armadilhas.md 2.10."""
        self._paused = True
        if self._grabber is not None:
            self._grabber.ungrab_all()

    def resume(self) -> None:
        self._apply_grabs()
        self._paused = False

    def _apply_grabs(self) -> None:
        if not self.want_grab or self._state is None:
            return
        if self._grabber is None:
            self._grabber = KeyGrabber(self._state)
        else:
            self._grabber.ungrab_all()
        for binding in self._bindings.values():
            try:
                self._grabber.grab(binding.key)
            except GrabDenied as exc:
                # Not fatal: the key still works, it just also reaches the focused window.
                self._log(f"[shortcut] {exc} — continuing without consuming the key")

    # ---- events ---------------------------------------------------------------------

    def _key_name(self, key) -> str | None:
        name = getattr(key, "name", None)
        if name:
            return name.lower()
        char = getattr(key, "char", None)
        return char.lower() if char else None

    def _on_event(self, key, pressed: bool) -> None:
        if self._paused:
            return
        name = self._key_name(key)
        if name is None:
            return
        binding = self._by_key.get(name)
        if binding is None:
            return
        if pressed:
            self._pressed(binding)
        # Releases ignored here — armadilhas 2.1 and 2.2: only the physical keymap decides.

    def _pressed(self, binding: Binding) -> None:
        if binding.mode is Mode.TOGGLE:
            self._toggled(binding)
            return

        with self._lock:
            if self._active is not None:
                return              # already recording, this is auto-repeat
            self._active = binding.name
            self._watching = True

        self.on_start(binding.name)
        self._watcher = threading.Thread(
            target=self._watch_hold, args=(binding,), daemon=True, name="dito-hold"
        )
        self._watcher.start()

    def _toggled(self, binding: Binding) -> None:
        """One action per physical press — see docs/armadilhas.md 2.11: holding the key delivers
        Press over and over, and a toggle that trusts each one starts and stops while you hold."""
        with self._lock:
            if binding.name in self._held:
                return
            self._held.add(binding.name)
            if self._active == binding.name:
                self._active = None
                action = self.on_stop
            elif self._active is None:
                self._active = binding.name
                action = self.on_start
            else:
                action = None

        threading.Thread(
            target=self._await_release, args=(binding,), daemon=True, name="dito-toggle"
        ).start()
        if action is not None:
            action(binding.name)

    def _await_release(self, binding: Binding) -> None:
        """Frees the toggle once the key is physically up: the keymap decides, never the release
        event, which is a lie under auto-repeat and on wireless keyboards (2.1 and 2.2)."""
        state = self._state
        try:
            if state is None:
                return
            up_since: float | None = None
            while not self._shutting_down:
                if state.is_down(binding.key):
                    up_since = None
                elif up_since is None:
                    up_since = time.monotonic()
                elif time.monotonic() - up_since >= GRACE_S:
                    return
                time.sleep(POLL_S)
        finally:
            with self._lock:
                self._held.discard(binding.name)

    def _watch_hold(self, binding: Binding) -> None:
        """Ends only after GRACE_S physically up — armadilhas 2.1 and 2.2, nothing else works."""
        state = self._state
        if state is None:
            return
        up_since: float | None = None
        try:
            while True:
                if self._active != binding.name:
                    return
                if self._shutting_down:
                    # Quitting mid-hold: finish the recording rather than abandoning it.
                    break
                now = time.monotonic()
                if state.is_down(binding.key):
                    if up_since is not None and now - up_since > 0.05:
                        self._log("[shortcut] ghost release swallowed — the same recording goes on")
                    up_since = None
                elif up_since is None:
                    up_since = now
                elif now - up_since >= GRACE_S:
                    break
                time.sleep(POLL_S)
        finally:
            self._watching = False

        with self._lock:
            if self._active != binding.name:
                return
            self._active = None
        self.on_stop(binding.name)

    @property
    def active(self) -> str | None:
        return self._active
