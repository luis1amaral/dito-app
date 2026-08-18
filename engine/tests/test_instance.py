"""The single-instance lock and the control socket.

Both tests here guard against a bug that already happened.

The lock NAME is a contract with another repository: the sibling project `defalt` claims the same
abstract socket on purpose, so that a dictation listener and that project can never run at once.
Renaming it on one side alone silently lets both run, fighting over the microphone and pasting
every sentence twice.

The lock's LIFETIME is the other half, and the old implementation got it wrong: it called
`claim_single_instance()` and threw the returned socket away, so CPython closed it immediately and
the lock was released the moment it was taken. Verified in the field — with the old daemon
running, a second process took the same lock without complaint.
"""

from __future__ import annotations

import os
import socket
import sys

import pytest

from dito.platform.linux_x11 import instance

# The abstract socket IS the mechanism under test, and AF_UNIX does not exist on Windows. The
# same guarantees are checked against the named mutex and pipe in test_instance_windows.py.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="backend de Linux — o equivalente está em test_instance_windows"
)

# A name of our own: the real one may be held by a Dito that is actually running, and a test that
# goes red because the application is working is worse than no test. The frozen-name test below
# still checks the real constant.
TEST_LOCK = f"dito-test-{os.getpid()}"


def test_the_lock_name_is_frozen():
    """A contract with the `defalt` project. Changing this string is a cross-repository break, so
    it fails here rather than silently at runtime on someone's machine."""
    assert instance.LEGACY_LOCK_NAME == "defalt-voice-input"


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


def test_holding_the_lock_requires_keeping_the_socket_alive():
    """The exact bug in the previous version: the returned socket was discarded, refcounting
    closed it, and the lock evaporated. This asserts the mechanism really depends on the caller
    holding on — so anyone who 'cleans up' the assignment sees this fail."""
    lock = instance.claim(TEST_LOCK)
    held_name = lock.getsockname()
    assert held_name  # bound

    del lock                            # simulate discarding the return value
    import gc

    gc.collect()

    # With nothing holding it, the name is free again — which is why DitoApp keeps it in a field.
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.bind("\0" + TEST_LOCK)
    finally:
        probe.close()


def test_control_socket_answers_ping_and_show(tmp_path, monkeypatch):
    monkeypatch.setattr(instance.paths, "control_socket", lambda: tmp_path / "dito.sock")
    seen: list[str] = []

    def handle(command: str) -> str:
        seen.append(command)
        return "ok"

    server = instance.ControlServer(handle)
    assert server.start()
    try:
        assert instance.send(instance.PING) == "ok"
        assert instance.send(instance.SHOW) == "ok"
    finally:
        server.stop()
    assert seen == [instance.PING, instance.SHOW]


def test_send_returns_none_when_nobody_is_listening(tmp_path, monkeypatch):
    """A second launch with no daemon running must fall through to starting one, not hang."""
    monkeypatch.setattr(instance.paths, "control_socket", lambda: tmp_path / "absent.sock")
    assert instance.send(instance.SHOW) is None


def test_a_stale_socket_file_does_not_block_startup(tmp_path, monkeypatch):
    """Killed with -9, the socket file survives. The next start has to reclaim it."""
    path = tmp_path / "dito.sock"
    path.write_text("resto de um processo morto")
    monkeypatch.setattr(instance.paths, "control_socket", lambda: path)

    server = instance.ControlServer(lambda _c: "ok")
    assert server.start()
    server.stop()
