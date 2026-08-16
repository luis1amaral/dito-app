"""Notification and alert sound on Windows — docs/armadilhas.md 9.4: why three channels."""

from __future__ import annotations

import ctypes
import winsound
from collections.abc import Callable
from ctypes import wintypes

APP_NAME = "Dito"

ALARM_MS = 15_000
NORMAL_MS = 6_000

# Unambiguous rather than pleasant: speech is being lost. The Windows twin of dialog-warning.oga.
_ALARM_ALIAS = "SystemExclamation"

_NIM_MODIFY = 0x00000001
_NIF_INFO = 0x00000010
_NIIF_INFO = 0x00000001
_NIIF_WARNING = 0x00000002
# The whole reason this file talks to Win32 at all — see docs/armadilhas.md 9.8.
_NIIF_NOSOUND = 0x00000010

# Qt names the window this since forever; the CLASS carries the Qt version and would rot.
_TRAY_WINDOW_TITLE = "QTrayIconMessageWindow"

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HANDLE),
    ]


def _tray_window() -> int | None:
    """Qt's hidden tray window, in this process — the balloon has to ride on the existing icon."""
    hwnd = _user32.FindWindowW(None, _TRAY_WINDOW_TITLE)
    return hwnd or None


def balloon(title: str, body: str, urgent: bool, msecs: int) -> bool:
    """Qt's showMessage() always dings; this is the same balloon with NIIF_NOSOUND on it."""
    hwnd = _tray_window()
    if not hwnd:
        return False
    data = _NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
    data.hWnd = hwnd
    data.uID = 0
    data.uFlags = _NIF_INFO
    data.szInfoTitle = title[:63]
    data.szInfo = body[:255]
    data.uVersion = msecs
    data.dwInfoFlags = (_NIIF_WARNING if urgent else _NIIF_INFO) | _NIIF_NOSOUND
    return bool(_shell32.Shell_NotifyIconW(_NIM_MODIFY, ctypes.byref(data)))

# The tray owns the only toast channel Windows gives us; app.py plugs it in (platform/ never
# imports ui/). Without it there is no notification, and saying so beats pretending.
_sink: Callable[[str, str, bool, int], bool] | None = None


def set_sink(sink: Callable[[str, str, bool, int], bool] | None) -> None:
    """Register who shows toasts; `notify()` answers False until someone does."""
    global _sink
    _sink = sink


def notify(title: str, body: str = "", urgent: bool = False, icon: str | None = None) -> bool:
    if _sink is None:
        return False
    try:
        return bool(_sink(title, body, urgent, ALARM_MS if urgent else NORMAL_MS))
    except Exception:
        return False


def alarm_sound() -> bool:
    try:
        winsound.PlaySound(_ALARM_ALIAS, winsound.SND_ALIAS | winsound.SND_ASYNC)
    except RuntimeError:
        return False
    return True
