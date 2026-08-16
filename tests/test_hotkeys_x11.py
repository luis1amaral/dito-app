"""Drives the real hotkey manager with synthetic X keystrokes and checks the timing.

This is an integration test on purpose. The whole point of `hotkeys.py` is behaviour that only
exists against a live X server — auto-repeat, physical keymap state, the grace window — and a
mock would test the mock.

F7/F8 are used because they are normally unbound, and because F9 belongs to the dictation daemon.
XTest injects at the server, so the keystrokes are global for the fraction of a second they last;
`pytest -m "not x11"` skips this file if that is not acceptable right now.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

pytestmark = pytest.mark.x11

x11 = pytest.importorskip("Xlib", reason="python-xlib não instalado")
pytest.importorskip("pynput", reason="pynput não instalado")

if not os.environ.get("DISPLAY"):
    pytest.skip("sem DISPLAY — testes de X11 não se aplicam", allow_module_level=True)

from Xlib import XK, X, display  # noqa: E402
from Xlib.ext import xtest  # noqa: E402

from dito.platform.linux_x11.hotkeys import GRACE_S, HotkeyManager, Mode  # noqa: E402


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, float]] = []
        self._lock = threading.Lock()
        self._t0 = time.monotonic()

    def start(self, name: str) -> None:
        self._add("START", name)

    def stop(self, name: str) -> None:
        self._add("STOP", name)

    def _add(self, kind: str, name: str) -> None:
        with self._lock:
            self.events.append((kind, name, time.monotonic() - self._t0))

    @property
    def sequence(self) -> list[tuple[str, str]]:
        with self._lock:
            return [(k, n) for k, n, _ in self.events]

    def gap(self, first: int, second: int) -> float:
        with self._lock:
            return self.events[second][2] - self.events[first][2]


def tap(dsp, key_name: str, hold_s: float) -> None:
    code = dsp.keysym_to_keycode(XK.string_to_keysym(key_name))
    xtest.fake_input(dsp, X.KeyPress, code)
    dsp.sync()
    time.sleep(hold_s)
    xtest.fake_input(dsp, X.KeyRelease, code)
    dsp.sync()


@pytest.fixture
def manager():
    rec = Recorder()
    mgr = HotkeyManager(on_start=rec.start, on_stop=rec.stop, grab=True)
    mgr.bind("dictation", "f7", Mode.HOLD)
    mgr.bind("meeting", "f8", Mode.TOGGLE)
    mgr.start()
    time.sleep(0.5)          # let the listener thread attach before injecting anything
    try:
        yield mgr, rec, display.Display()
    finally:
        mgr.stop()


def test_hold_lasts_as_long_as_the_key_is_physically_down(manager):
    """The regression that mattered most: a long hold used to be cut short by auto-repeat,
    because X11 delivers Release+Press pairs while the key is held."""
    mgr, rec, dsp = manager
    tap(dsp, "F7", 1.5)
    time.sleep(GRACE_S + 0.4)

    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]
    held = rec.gap(0, 1)
    assert 1.5 <= held <= 1.5 + GRACE_S + 0.4, (
        f"segurou {held:.2f}s, esperado ~{1.5 + GRACE_S:.2f}s"
    )


def test_short_tap_still_produces_one_start_and_one_stop(manager):
    mgr, rec, dsp = manager
    tap(dsp, "F7", 0.15)
    time.sleep(GRACE_S + 0.4)

    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]
    assert rec.gap(0, 1) <= 0.15 + GRACE_S + 0.4


def test_toggle_needs_a_second_press_not_a_release(manager):
    """A meeting has no time limit: releasing the key must not end the recording."""
    mgr, rec, dsp = manager
    tap(dsp, "F8", 0.1)
    time.sleep(0.8)
    assert rec.sequence == [("START", "meeting")], "soltar a tecla não pode parar a reunião"

    tap(dsp, "F8", 0.1)
    time.sleep(0.4)
    assert rec.sequence == [("START", "meeting"), ("STOP", "meeting")]


def test_conflicts_names_the_action_already_using_the_key(manager):
    mgr, _rec, _dsp = manager
    assert mgr.conflicts("f7") == "dictation"
    assert mgr.conflicts("f8") == "meeting"
    assert mgr.conflicts("f12") is None
    assert mgr.conflicts("f7", ignoring="dictation") is None


def test_paused_manager_ignores_the_key(manager):
    """While the settings window is capturing a new key, the hotkey must not fire."""
    mgr, rec, dsp = manager
    mgr.pause()
    tap(dsp, "F7", 0.2)
    time.sleep(GRACE_S + 0.3)
    assert rec.sequence == []

    mgr.resume()
    tap(dsp, "F7", 0.2)
    time.sleep(GRACE_S + 0.4)
    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]
