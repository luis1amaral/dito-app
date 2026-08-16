"""Single-instance lock on Windows.

The name `Local\\defalt-voice-input` is a CONTRACT WITH ANOTHER REPOSITORY. The sibling project
`defalt` creates the same named mutex on purpose, so that it and the dictation listener can never
run at the same time — two listeners fight over the microphone and paste every sentence twice.
Renaming it on one side alone silently lets both run, which is the exact bug the mutex prevents.

Do not rename. `tests/test_instance.py` fails if the Linux side of the same contract changes.

Not exercised yet: there is no Windows machine here to run it on, and it will not be claimed as
working until there is.
"""

from __future__ import annotations

import sys

from ..linux_x11.instance import LEGACY_LOCK_NAME, AlreadyRunning

MUTEX_NAME = f"Local\\{LEGACY_LOCK_NAME}"
_ERROR_ALREADY_EXISTS = 183


def claim() -> object:
    """Take the mutex, or raise. The returned handle must stay referenced for the whole process.

    That last sentence is not boilerplate: the previous version called its Linux equivalent and
    threw the return value away, so CPython closed the socket immediately and the lock was
    released the instant it was taken. It never protected anything. See docs/armadilhas.md §5.1b.
    """
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
