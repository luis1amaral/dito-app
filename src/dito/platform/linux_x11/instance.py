"""One Dito at a time (the exclusion lock), plus a control socket a second launch talks to."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from pathlib import Path

from ... import paths

# Do NOT rename: contract with the sibling `defalt` project (docs/armadilhas.md 5.1).
LEGACY_LOCK_NAME = "defalt-voice-input"

SHOW = "show"
PING = "ping"
QUIT = "quit"
STATUS = "status"
_ENCODING = "utf-8"


class AlreadyRunning(RuntimeError):
    pass


# Abstract socket, not a PID file: the kernel reclaims the name on death (armadilhas 5.2).
def claim(name: str = LEGACY_LOCK_NAME) -> socket.socket:
    """Take the lock; the returned socket must stay referenced (armadilhas 5.1b)."""
    # `name` lets tests take their own lock instead of fighting the live daemon for the real one.
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
    """Listens for a second launch on its own thread; requests reach the UI via the callback."""

    def __init__(self, on_command: Callable[[str], str]) -> None:
        self._on_command = on_command
        self._path: Path = paths.control_socket()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # The exclusion lock already proved no other Dito is alive, so a leftover node can go.
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
