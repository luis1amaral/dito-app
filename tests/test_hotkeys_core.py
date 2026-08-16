"""The hold/toggle machine, with a fake keyboard instead of a real one.

`test_hotkeys_x11.py` drives the same behaviour against a live X server, which is the only way to
prove the X11 half — but it skips everywhere else, so until now these regressions had no cover on
Windows at all. Here the physical key state is a set the test controls, so the machine itself gets
tested on both platforms and the backends only have to be adapters.
"""

from __future__ import annotations

import threading
import time

import pytest

from dito.platform.hotkeys_core import GRACE_S, HotkeyManager, Mode


class FakeKeys:
    """Stands in for the X keymap / GetAsyncKeyState: the test decides what is physically down."""

    def __init__(self) -> None:
        self._down: set[str] = set()
        self._lock = threading.Lock()

    def press(self, key: str) -> None:
        with self._lock:
            self._down.add(key)

    def release(self, key: str) -> None:
        with self._lock:
            self._down.discard(key)

    def is_down(self, key: str) -> bool:
        with self._lock:
            return key in self._down

    def close(self) -> None:
        pass


class FakeListener:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class FakeKey:
    """Shaped like a pynput key, which is all `_key_name` ever looks at."""

    def __init__(self, name: str) -> None:
        self.name = name


class Manager(HotkeyManager):
    def __init__(self, keys: FakeKeys, **kwargs) -> None:
        super().__init__(**kwargs)
        self._keys = keys

    def _make_state(self) -> FakeKeys:
        return self._keys

    def _make_listener(self, on_press, on_release) -> FakeListener:
        return FakeListener()


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
def wired():
    keys = FakeKeys()
    rec = Recorder()
    mgr = Manager(keys, on_start=rec.start, on_stop=rec.stop, grab=False)
    mgr.bind("dictation", "f7", Mode.HOLD)
    mgr.bind("meeting", "f8", Mode.TOGGLE)
    mgr.start()
    try:
        yield mgr, keys, rec
    finally:
        mgr.stop()


def tap(mgr, keys: FakeKeys, key: str, hold_s: float, repeats: int = 1) -> None:
    """Down, then `repeats` presses while held — auto-repeat delivers Press over and over."""
    keys.press(key)
    for i in range(repeats):
        mgr._on_event(FakeKey(key), pressed=True)
        if i + 1 < repeats:
            time.sleep(hold_s / repeats)
    time.sleep(hold_s if repeats == 1 else hold_s / repeats)
    keys.release(key)


def test_hold_lasts_as_long_as_the_key_is_physically_down(wired):
    """The regression that mattered most: a long hold used to be cut short by auto-repeat,
    because the release event arrives while the key is still down."""
    mgr, keys, rec = wired
    tap(mgr, keys, "f7", 0.8)
    time.sleep(GRACE_S + 0.3)

    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]
    held = rec.gap(0, 1)
    assert 0.8 <= held <= 0.8 + GRACE_S + 0.3, (
        f"segurou {held:.2f}s, esperado ~{0.8 + GRACE_S:.2f}s"
    )


def test_a_ghost_release_does_not_cut_the_recording(wired):
    """The event says up, the keymap says down: only the keymap is believed (armadilhas 2.1)."""
    mgr, keys, rec = wired
    keys.press("f7")
    mgr._on_event(FakeKey("f7"), pressed=True)
    time.sleep(0.2)
    mgr._on_event(FakeKey("f7"), pressed=False)     # the lie
    time.sleep(GRACE_S + 0.2)

    assert rec.sequence == [("START", "dictation")], "soltar mentindo não pode parar a gravação"
    keys.release("f7")
    time.sleep(GRACE_S + 0.3)
    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]


def test_short_tap_still_produces_one_start_and_one_stop(wired):
    mgr, keys, rec = wired
    tap(mgr, keys, "f7", 0.1)
    time.sleep(GRACE_S + 0.3)

    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]


def test_toggle_needs_a_second_press_not_a_release(wired):
    """A meeting has no time limit: releasing the key must not end the recording."""
    mgr, keys, rec = wired
    tap(mgr, keys, "f8", 0.1)
    time.sleep(GRACE_S + 0.3)
    assert rec.sequence == [("START", "meeting")], "soltar a tecla não pode parar a reunião"

    tap(mgr, keys, "f8", 0.1)
    time.sleep(GRACE_S + 0.3)
    assert rec.sequence == [("START", "meeting"), ("STOP", "meeting")]


def test_holding_the_toggle_key_starts_once_and_only_once(wired):
    """The defect the owner hit: auto-repeat delivers Press again and again while the key is
    held, and the toggle acted on every one — five empty sessions in three seconds (2.11)."""
    mgr, keys, rec = wired
    tap(mgr, keys, "f8", 0.6, repeats=6)
    time.sleep(GRACE_S + 0.3)

    assert rec.sequence == [("START", "meeting")], f"segurar a tecla produziu {rec.sequence}"

    tap(mgr, keys, "f8", 0.1)
    time.sleep(GRACE_S + 0.3)
    assert rec.sequence == [("START", "meeting"), ("STOP", "meeting")], (
        "depois de segurar, o próximo toque tem que parar"
    )


def test_auto_repeat_does_not_restart_a_hold(wired):
    mgr, keys, rec = wired
    tap(mgr, keys, "f7", 0.5, repeats=5)
    time.sleep(GRACE_S + 0.3)

    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]


def test_paused_manager_ignores_the_key(wired):
    """While the settings window is capturing a new key, the hotkey must not fire."""
    mgr, keys, rec = wired
    mgr.pause()
    tap(mgr, keys, "f7", 0.1)
    time.sleep(GRACE_S + 0.2)
    assert rec.sequence == []

    mgr.resume()
    tap(mgr, keys, "f7", 0.1)
    time.sleep(GRACE_S + 0.3)
    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]


def test_conflicts_names_the_action_already_using_the_key(wired):
    mgr, _keys, _rec = wired
    assert mgr.conflicts("f7") == "dictation"
    assert mgr.conflicts("f8") == "meeting"
    assert mgr.conflicts("f12") is None
    assert mgr.conflicts("f7", ignoring="dictation") is None


def test_a_backend_that_consumes_the_key_dispatches_by_name(wired):
    """Windows suppresses the event before pynput builds a key object, so it feeds the name."""
    mgr, keys, rec = wired
    keys.press("f7")
    mgr._on_key_name("f7", True)
    time.sleep(0.1)
    keys.release("f7")
    time.sleep(GRACE_S + 0.3)

    assert rec.sequence == [("START", "dictation"), ("STOP", "dictation")]
