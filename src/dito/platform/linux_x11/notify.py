"""Notification and alert sound, best-effort — docs/armadilhas.md 9.4: why three channels."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

APP_NAME = "Dito"

# In every freedesktop theme, and chosen to be unambiguous, not pleasant: speech is being lost.
_ALARM_SOUNDS = (
    "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga",
    "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
)


def _run(args: list[str]) -> bool:
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    return True


def notify(title: str, body: str = "", urgent: bool = False, icon: str | None = None) -> bool:
    if not shutil.which("notify-send"):
        return False
    args = ["notify-send", "--app-name", APP_NAME]
    if urgent:
        # Sticks until dismissed: reserved for lost audio, or the user learns to ignore it.
        args += ["--urgency", "critical"]
    if icon:
        args += ["--icon", icon]
    args += [title, body]
    return _run(args)


def alarm_sound() -> bool:
    if not shutil.which("paplay"):
        return False
    for candidate in _ALARM_SOUNDS:
        if Path(candidate).exists():
            return _run(["paplay", candidate])
    return False
