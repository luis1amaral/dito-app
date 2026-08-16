"""The single-instance mutex and the control pipe — the Windows half of test_instance.py.

Same two guarantees, different mechanism. The lock NAME is a contract with the sibling project
`defalt`: both claim `Local\\defalt-voice-input` on purpose, so a dictation listener and that
project can never run at once. Renaming it on one side alone silently lets both run, fighting over
the microphone and pasting every sentence twice.

The lock's LIFETIME is the other half: a handle that nobody holds is closed by CPython, and the
mutex dies with it. The old Linux daemon shipped that exact bug, so it is asserted here too.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="backend do Windows")

if sys.platform == "win32":
    from dito.platform.windows import instance

# A name of our own: the real one may be held by a Dito that is actually running, and a test that
# goes red because the application is working is worse than no test.
TEST_LOCK = f"dito-test-{os.getpid()}"
TEST_PIPE = rf"\\.\pipe\dito-test-{os.getpid()}"


def test_the_lock_name_is_frozen():
    """A contract with the `defalt` project. Changing this string is a cross-repository break, so
    it fails here rather than silently at runtime on someone's machine."""
    assert instance.LEGACY_LOCK_NAME == "defalt-voice-input"
    assert instance.MUTEX_NAME == "Local\\defalt-voice-input"


def test_a_second_claim_is_refused_while_the_first_is_held():
    first = instance.claim(TEST_LOCK)
    try:
        with pytest.raises(instance.AlreadyRunning):
            instance.claim(TEST_LOCK)
    finally:
        first.close()


def test_the_lock_is_released_when_the_holder_closes_it():
    first = instance.claim(TEST_LOCK)
    first.close()
    second = instance.claim(TEST_LOCK)   # must not raise
    second.close()


def test_holding_the_lock_requires_keeping_the_handle_alive():
    """Drop the reference and the mutex goes with it — which is why DitoApp keeps it in a field."""
    import gc

    lock = instance.claim(TEST_LOCK)
    del lock
    gc.collect()

    again = instance.claim(TEST_LOCK)    # free again, so this must not raise
    again.close()


def test_control_pipe_answers_ping_and_show():
    seen: list[str] = []

    def handle(command: str) -> str:
        seen.append(command)
        return "ok"

    server = instance.ControlServer(handle, pipe=TEST_PIPE)
    assert server.start()
    try:
        assert instance.send(instance.PING, pipe=TEST_PIPE) == "ok"
        assert instance.send(instance.SHOW, pipe=TEST_PIPE) == "ok"
    finally:
        server.stop()
    assert seen == [instance.PING, instance.SHOW]


def test_send_returns_none_when_nobody_is_listening():
    """A second launch with no daemon running must fall through to starting one, not hang."""
    assert instance.send(instance.SHOW, pipe=rf"\\.\pipe\dito-absent-{os.getpid()}") is None


def test_a_second_server_refuses_the_same_pipe():
    """The pipe name is exclusive: the loser has to know it lost instead of listening to nothing."""
    first = instance.ControlServer(lambda _c: "ok", pipe=TEST_PIPE)
    assert first.start()
    try:
        second = instance.ControlServer(lambda _c: "ok", pipe=TEST_PIPE)
        assert second.start() is False
    finally:
        first.stop()


def test_stopping_releases_the_name_for_the_next_start():
    """Closing alone leaves the serve thread parked in accept(), and the name stuck with it."""
    first = instance.ControlServer(lambda _c: "ok", pipe=TEST_PIPE)
    assert first.start()
    first.stop()

    second = instance.ControlServer(lambda _c: "ok", pipe=TEST_PIPE)
    assert second.start(), "o nome do pipe não foi liberado pelo stop()"
    try:
        assert instance.send(instance.STATUS, pipe=TEST_PIPE) == "ok"
    finally:
        second.stop()
