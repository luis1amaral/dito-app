"""Notification and alert sound on Windows — docs/armadilhas.md 9.4: why three channels."""

from __future__ import annotations

import winsound
from collections.abc import Callable

APP_NAME = "Dito"

ALARM_MS = 15_000
NORMAL_MS = 6_000

# Unambiguous rather than pleasant: speech is being lost. The Windows twin of dialog-warning.oga.
_ALARM_ALIAS = "SystemExclamation"

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
