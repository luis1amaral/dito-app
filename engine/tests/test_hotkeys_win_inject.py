"""Drives the real Windows hotkey manager with synthetic keystrokes and checks the timing.

The twin of `test_hotkeys_x11.py`. An integration test on purpose: the whole point of the Windows
backend is behaviour that only exists against a live low-level hook — suppression aborting
pynput's conversion, GetAsyncKeyState as the physical truth, the grace window — and a mock would
test the mock.

F7/F8 are used because they are normally unbound, and because F9 belongs to the dictation daemon.
SendInput injects at the system, so the keystrokes are global for the fraction of a second they
last; `pytest -m "not winkeys"` skips this file if that is not acceptable right now. They are also
grabbed, so the hook swallows them before any other window sees them.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes

import pytest

pytestmark = [
    pytest.mark.winkeys,
    pytest.mark.skipif(sys.platform != "win32", reason="backend do Windows"),
]

pytest.importorskip("pynput", reason="pynput não instalado")

if sys.platform == "win32":
    from dito.platform.windows.hotkeys import GRACE_S, HotkeyManager, Mode, vk_for

_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTUNION(ctypes.Union):
    # Sized after MOUSEINPUT, the largest member: a short union makes SendInput reject the call.
    _fields_ = [("ki", _KEYBDINPUT), ("padding", ctypes.c_ubyte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(vk: int, up: bool) -> None:
    event = _INPUT(
        type=_INPUT_KEYBOARD,
        u=_INPUTUNION(ki=_KEYBDINPUT(wVk=vk, dwFlags=_KEYEVENTF_KEYUP if up else 0)),
    )
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_INPUT))
    assert sent == 1, f"SendInput recusou a injeção (sizeof INPUT = {ctypes.sizeof(_INPUT)})"


def tap(key: str, hold_s: float) -> None:
    vk = vk_for(key)
    assert vk, f"tecla desconhecida: {key}"
    _send(vk, up=False)
    time.sleep(hold_s)
    _send(vk, up=True)


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


@pytest.fixture
def manager():
    rec = Recorder()
    mgr = HotkeyManager(on_start=rec.start, on_stop=rec.stop, grab=True)
    mgr.bind("dictation", "f7", Mode.HOLD)
    mgr.bind("meeting", "f8", Mode.TOGGLE)
    mgr.start()
    time.sleep(0.6)          # let the hook attach before injecting anything
    try:
        yield mgr, rec
    finally:
        mgr.stop()


def test_hold_lasts_as_long_as_the_key_is_physically_down(manager):
    """A consumed key never reaches pynput's `on_press`, so this also proves the event filter is
    feeding the queue itself — the difference from X11 (docs/armadilhas.md 2.12)."""
    _mgr, rec = manager
    tap("f7", 1.2)
    time.sleep(GRACE_S + 0.5)

    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]
    held = rec.gap(0, 1)
    assert 1.2 <= held <= 1.2 + GRACE_S + 0.5, (
        f"segurou {held:.2f}s, esperado ~{1.2 + GRACE_S:.2f}s"
    )


def test_short_tap_still_produces_one_start_and_one_stop(manager):
    _mgr, rec = manager
    tap("f7", 0.15)
    time.sleep(GRACE_S + 0.5)

    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]


def test_toggle_needs_a_second_press_not_a_release(manager):
    """A meeting has no time limit: releasing the key must not end the recording."""
    _mgr, rec = manager
    tap("f8", 0.1)
    time.sleep(0.8)
    assert rec.sequence == [("START", "meeting")], "soltar a tecla não pode parar a reunião"

    tap("f8", 0.1)
    time.sleep(0.5)
    assert rec.sequence == [("START", "meeting"), ("STOP", "meeting")]


def test_holding_the_toggle_key_starts_once_and_only_once(manager):
    """Windows auto-repeat delivers WM_KEYDOWN again and again while the key is held, and a toggle
    that trusts each one starts and stops for as long as you hold. See docs/armadilhas.md 2.11."""
    _mgr, rec = manager
    tap("f8", 1.5)
    time.sleep(GRACE_S + 0.5)

    assert rec.sequence == [("START", "meeting")], f"segurar a tecla produziu {rec.sequence}"

    tap("f8", 0.1)
    time.sleep(0.5)
    assert rec.sequence == [("START", "meeting"), ("STOP", "meeting")], (
        "depois de segurar, o próximo toque tem que parar"
    )


def test_paused_manager_ignores_the_key(manager):
    """While the settings window is capturing a new key, the hotkey must not fire."""
    mgr, rec = manager
    mgr.pause()
    tap("f7", 0.2)
    time.sleep(GRACE_S + 0.4)
    assert rec.sequence == []

    mgr.resume()
    tap("f7", 0.2)
    time.sleep(GRACE_S + 0.5)
    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]


def test_an_unbound_key_is_left_alone(manager):
    """Only the bound keys get swallowed; everything else has to pass straight through."""
    _mgr, rec = manager
    tap("f6", 0.2)
    time.sleep(GRACE_S + 0.4)
    assert rec.sequence == []
