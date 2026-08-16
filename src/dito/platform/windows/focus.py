"""Focus grab/restore on a private thread, same contract as X11 (armadilhas 2.3, 2.4)."""

from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes

_GRAB = "grab"
_RESTORE = "restore"

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, wintypes.LPDWORD]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def _raise(hwnd: int) -> bool:
    """Windows only grants the foreground to whoever already owns it, hence the thread attach."""
    if not hwnd or not _user32.IsWindow(hwnd):
        return False
    if _user32.SetForegroundWindow(hwnd):
        return True

    foreground = _user32.GetForegroundWindow()
    owner = _user32.GetWindowThreadProcessId(foreground, None)
    mine = _kernel32.GetCurrentThreadId()
    if not owner or owner == mine:
        return False
    _user32.AttachThreadInput(mine, owner, True)
    try:
        return bool(_user32.SetForegroundWindow(hwnd))
    finally:
        _user32.AttachThreadInput(mine, owner, False)


class FocusBroker:
    """Serialises focus changes onto one thread. Fire-and-forget: callers never block."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[str, int]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._previous: int | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._serve, daemon=True, name="dito-focus")
        self._thread.start()

    def take(self, window_id: int) -> None:
        self.start()
        self._queue.put((_GRAB, window_id))

    def give_back(self) -> None:
        """Must land before the paste, or the text goes into Dito's own review card."""
        if self._thread is not None:
            self._queue.put((_RESTORE, 0))

    def _serve(self) -> None:
        while True:
            op, window_id = self._queue.get()
            try:
                if op == _GRAB:
                    owner = _user32.GetForegroundWindow()
                    # Never remember ourselves: two grabs in a row would return focus to us.
                    if owner and owner != window_id:
                        self._previous = owner
                    _raise(window_id)
                elif op == _RESTORE:
                    previous, self._previous = self._previous, None
                    if previous:
                        _raise(previous)
            except Exception:
                # A window closed under us: losing one restore beats losing the thread forever.
                continue
