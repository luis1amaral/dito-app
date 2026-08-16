"""One Dito at a time (a named mutex), plus a named pipe a second launch talks to."""

from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable
from ctypes import wintypes
from multiprocessing.connection import Client, Listener

from ...i18n import _
from ..control import ENCODING as _ENCODING
from ..control import LEGACY_LOCK_NAME, PING, QUIT, SHOW, STATUS, AlreadyRunning

__all__ = [
    "LEGACY_LOCK_NAME", "PING", "QUIT", "SHOW", "STATUS", "AlreadyRunning",
    "MUTEX_NAME", "PIPE_NAME", "claim", "send", "ControlServer",
]

# Do NOT rename: contract with the sibling `defalt` project (docs/armadilhas.md 5.1).
MUTEX_NAME = f"Local\\{LEGACY_LOCK_NAME}"
PIPE_NAME = r"\\.\pipe\dito-control"

_ERROR_ALREADY_EXISTS = 183
_MAX_COMMAND = 64
_MAX_REPLY = 256

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class _Mutex:
    """Closing releases the lock, exactly like dropping the Linux socket does (armadilhas 5.1b)."""

    def __init__(self, handle: int) -> None:
        self._handle: int | None = handle

    def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            _kernel32.CloseHandle(handle)

    def __del__(self) -> None:
        self.close()


def claim(name: str = LEGACY_LOCK_NAME) -> _Mutex:
    """Take the lock; the returned object must stay referenced (armadilhas 5.1b)."""
    # `name` lets tests take their own lock instead of fighting the live daemon for the real one.
    mutex_name = MUTEX_NAME if name == LEGACY_LOCK_NAME else f"Local\\{name}"
    handle = _kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        raise AlreadyRunning(_("could not take the single-instance lock"))
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        raise AlreadyRunning(
            _("dictation is already running — two instances would paste everything twice")
        )
    return _Mutex(handle)


class ControlServer:
    """Listens for a second launch on its own thread; requests reach the UI via the callback."""

    def __init__(self, on_command: Callable[[str], str], pipe: str = PIPE_NAME) -> None:
        self._on_command = on_command
        self._pipe = pipe
        self._listener: Listener | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        # A pipe dies with the process that made it, so there is no stale node to clear first.
        try:
            self._listener = Listener(address=self._pipe, family="AF_PIPE")
        except OSError:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, daemon=True, name="dito-control")
        self._thread.start()
        return True

    def _serve(self) -> None:
        while not self._stop.is_set() and self._listener is not None:
            try:
                conn = self._listener.accept()
            except OSError:
                return
            with conn:
                if self._stop.is_set():
                    return
                try:
                    command = conn.recv_bytes(_MAX_COMMAND).decode(_ENCODING).strip()
                    conn.send_bytes(self._on_command(command).encode(_ENCODING))
                except (OSError, EOFError, UnicodeDecodeError):
                    continue

    def stop(self) -> None:
        """Closing alone leaves the thread parked in accept(), so it gets poked awake first."""
        self._stop.set()
        listener, self._listener = self._listener, None
        if listener is not None:
            try:
                Client(self._pipe, family="AF_PIPE").close()
            except OSError:
                pass
            thread, self._thread = self._thread, None
            if thread is not None:
                thread.join(timeout=1.0)
            try:
                listener.close()
            except OSError:
                pass


def send(command: str, timeout: float = 1.5, pipe: str = PIPE_NAME) -> str | None:
    """Talk to a running Dito. `None` means nobody answered."""
    try:
        conn = Client(pipe, family="AF_PIPE")
    except OSError:
        return None
    with conn:
        try:
            conn.send_bytes(command.encode(_ENCODING))
            if not conn.poll(timeout):
                return None
            return conn.recv_bytes(_MAX_REPLY).decode(_ENCODING).strip()
        except (OSError, EOFError, UnicodeDecodeError):
            return None
