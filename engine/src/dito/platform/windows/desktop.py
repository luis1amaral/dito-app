"""Telling Windows who this process is, so the shell stops calling it Python."""

from __future__ import annotations

import ctypes


def set_app_id(app_id: str) -> bool:
    """Without this the taskbar groups us under the interpreter and shows ITS icon, not ours."""
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        return shell32.SetCurrentProcessExplicitAppUserModelID(app_id) == 0
    except (OSError, AttributeError):
        return False
