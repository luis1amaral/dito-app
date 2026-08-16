"""Global hotkeys on X11 — the part of this program with the most scar tissue.

Reading the key events alone does not work, and the reasons are all empirical:

1. **Auto-repeat sends Release+Press pairs.** Hold a key down and X11 delivers a release
   immediately followed by a press, milliseconds apart. Treating the first release as "let go"
   ends the recording half a second after it started.

2. **So the events are not the truth; the keymap is.** `query_keymap` reports the PHYSICAL state
   of every key. A release is only real once the key has been continuously up for a grace window.
   Keys synthesised by XTest show up there too, so the method stays consistent.

3. **Wireless keyboards emit phantom releases** (power saving) that the keymap itself confirms.
   Those used to split one sentence into two recordings. The watcher bridges them: the same
   recording continues.

4. **Xlib is not thread-safe.** Every auto-repeat release used to spawn a timer landing in
   `query_keymap`; unserialised, two replies interleave on one connection and the process hangs.
   Every call here goes through a lock, on a connection this module owns.

5. **`suppress_event` is win32-only.** On X11 the cancel key leaks a character into whatever
   field has focus. `XGrabKey` is what actually consumes it — and since there is no API for "who
   owns this key", *attempting the grab is the test*: `BadAccess` means someone else has it.
"""

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
    """Another program already owns this key. There is no way to ask X who — the grab attempt is
    the only test available, and this is its failure."""


def _keysym_name(key: str) -> str:
    """"f9" -> "F9", "scroll_lock" -> "Scroll_Lock". X keysym names are Capitalised_Like_This."""
    return "_".join(part.capitalize() for part in key.split("_"))


class KeyState:
    """Physical key state, read from the X server and serialised behind one lock."""

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
    """Consumes keys so they never reach the focused window.

    Grabs are registered for every combination of the "don't care" modifiers. Without that, the
    grab silently stops working the moment NumLock or CapsLock is on — a classic X11 trap, and
    one that looks like "the hotkey randomly stopped".
    """

    # NumLock (Mod2), CapsLock (Lock), ScrollLock (Mod5) in every combination.
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
            raise GrabDenied(f"tecla desconhecida: {key}")
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
                raise GrabDenied(f"«{key.upper()}» já pertence a outro programa")
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
    """Turns raw key events into start/stop decisions.

    `on_start(name)` and `on_stop(name)` are called from a worker thread, never from the key
    event thread — the old version learned that transcribing inside the callback blocks the hook
    and, on Windows, gets the listener torn down entirely.
    """

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

    # ---- bindings -------------------------------------------------------------------

    def bind(self, name: str, key: str, mode: Mode) -> None:
        binding = Binding(name=name, key=key.lower(), mode=mode)
        self._bindings[name] = binding
        self._by_key[binding.key] = binding

    def conflicts(self, key: str, ignoring: str | None = None) -> str | None:
        """Which of our own actions already uses this key. Checked before the X grab, because a
        collision inside Dito deserves a clearer message than `BadAccess`."""
        key = key.lower()
        for name, binding in self._bindings.items():
            if name != ignoring and binding.key == key:
                return name
        return None

    # ---- lifecycle ------------------------------------------------------------------

    def start(self) -> None:
        from pynput import keyboard

        self._state = KeyState()
        self._apply_grabs()

        def on_press(key):
            self._on_event(key, pressed=True)

        def on_release(key):
            self._on_event(key, pressed=False)

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
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
        """Used while the settings window captures a new key. The listener thread stays alive and
        simply discards — tearing a pynput Listener down and rebuilding it is what leaves a key
        stuck down."""
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
                # Not fatal: without the grab the key still works, it just also reaches the
                # focused window. Silently falling back would be worse than saying so.
                self._log(f"[atalho] {exc} — seguindo sem consumir a tecla")

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
        # Releases are deliberately ignored here. On X11 they are not trustworthy (auto-repeat,
        # phantom releases); the watcher thread decides, from the physical keymap.

    def _pressed(self, binding: Binding) -> None:
        with self._lock:
            if binding.mode is Mode.TOGGLE:
                if self._active == binding.name:
                    self._active = None
                    self.on_stop(binding.name)
                elif self._active is None:
                    self._active = binding.name
                    self.on_start(binding.name)
                return

            if self._active is not None:
                return              # already recording, this is auto-repeat
            self._active = binding.name
            self._watching = True

        self.on_start(binding.name)
        threading.Thread(
            target=self._watch_hold, args=(binding,), daemon=True, name="dito-hold"
        ).start()

    def _watch_hold(self, binding: Binding) -> None:
        """Finish only when the key has been PHYSICALLY up for GRACE_S continuously.

        This is the fix for both auto-repeat and phantom releases. A wireless keyboard's spurious
        release is confirmed by the keymap too, so no amount of event filtering catches it — only
        requiring sustained absence does.
        """
        state = self._state
        if state is None:
            return
        up_since: float | None = None
        try:
            while True:
                if self._active != binding.name:
                    return
                now = time.monotonic()
                if state.is_down(binding.key):
                    if up_since is not None and now - up_since > 0.05:
                        self._log("[atalho] release fantasma atravessado — a mesma gravação segue")
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
