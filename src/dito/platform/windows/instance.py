"""Windows single-instance mutex. Do NOT rename: contract with `defalt` (armadilhas 5.1)."""

from __future__ import annotations

import sys

from ..linux_x11.instance import LEGACY_LOCK_NAME, AlreadyRunning

# Never run on a Windows machine yet, and not claimed as working until it has been.
MUTEX_NAME = f"Local\\{LEGACY_LOCK_NAME}"
_ERROR_ALREADY_EXISTS = 183


def claim() -> object:
    """Take the mutex; the handle must stay referenced (armadilhas 5.1b — not boilerplate)."""
    if sys.platform != "win32":
        raise RuntimeError("adaptador do Windows chamado fora do Windows")

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        raise AlreadyRunning(
            "já existe um ditado rodando — duas instâncias colariam o texto duplicado"
        )
    return handle
