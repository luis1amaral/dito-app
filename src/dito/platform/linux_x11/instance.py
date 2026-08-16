"""One Dito at a time, and a way for a second launch to talk to the first.

Two separate mechanisms, for two separate jobs:

**The exclusion lock** is an abstract UNIX socket named `defalt-voice-input`. That name is a
CONTRACT WITH ANOTHER REPOSITORY: the sibling project `defalt` claims the same name (a named
mutex `Local\\defalt-voice-input` on Windows) precisely so the two can never run at once. Two
dictation listeners fight over the microphone and paste every sentence twice. Renaming this on
one side alone silently lets both run — which is the bug the lock exists to prevent, reintroduced
by a tidy-up. There is a test that fails if the string changes.

Abstract sockets (a leading NUL) are used rather than a PID file because the kernel reclaims them
when the process dies. A PID file goes stale — this project has already seen one claiming 117814
while the live process was 1812 — and then the "is it running?" check answers wrong.

**The control socket** is separate, and Dito's own: `$XDG_RUNTIME_DIR/dito/dito.sock`. It is how
`dito ui` reaches an already-running daemon and asks it to show the window, instead of starting a
second process that would immediately lose the exclusion lock and exit.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from pathlib import Path

from ... import paths

# Do not rename. See the module docstring: this is shared with the `defalt` project on purpose.
LEGACY_LOCK_NAME = "defalt-voice-input"

SHOW = "show"
PING = "ping"
QUIT = "quit"
STATUS = "status"
_ENCODING = "utf-8"


class AlreadyRunning(RuntimeError):
    pass


def claim(name: str = LEGACY_LOCK_NAME) -> socket.socket:
    """Take the exclusion lock, or raise. The returned socket must stay alive for the whole
    process: closing it releases the lock.

    `name` exists so the tests can exercise the mechanism under their own name. Without it they
    would fight the running daemon for the real lock and fail — a test that goes red because the
    application is working is worse than no test.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind("\0" + name)
    except OSError as exc:
        sock.close()
        raise AlreadyRunning(
            "já existe um ditado rodando — duas instâncias colariam o texto duplicado"
        ) from exc
    return sock


class ControlServer:
    """Listens for `show` from a second launch. Runs on its own thread; a request never touches
    the UI directly, it goes through the callback the app hands over."""

    def __init__(self, on_command: Callable[[str], str]) -> None:
        self._on_command = on_command
        self._path: Path = paths.control_socket()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # A socket left behind by a killed process would block bind(); the exclusion lock has
        # already established that no other Dito is alive, so removing it here is safe.
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(str(self._path))
            sock.listen(4)
            sock.settimeout(0.5)
        except OSError:
            return False

        self._sock = sock
        self._thread = threading.Thread(target=self._serve, daemon=True, name="dito-control")
        self._thread.start()
        return True

    def _serve(self) -> None:
        while not self._stop.is_set() and self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except (TimeoutError, OSError):
                continue
            with conn:
                try:
                    command = conn.recv(64).decode(_ENCODING).strip()
                    conn.sendall(self._on_command(command).encode(_ENCODING))
                except (OSError, UnicodeDecodeError):
                    continue

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        try:
            self._path.unlink()
        except OSError:
            pass


def send(command: str, timeout: float = 1.5) -> str | None:
    """Talk to a running Dito. `None` means nobody answered."""
    path = paths.control_socket()
    if not path.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
            sock.sendall(command.encode(_ENCODING))
            return sock.recv(256).decode(_ENCODING).strip()
    except OSError:
        return None
