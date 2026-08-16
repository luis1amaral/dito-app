"""System notification and alert sound.

The alarm fires on three channels on purpose, because each one alone is missable: the pill can be
behind a fullscreen window, the notification disappears on its own, and the tray icon is easy not
to look at. Sound is the only one that reaches you when you are looking at your keyboard and
talking — which is exactly the posture of someone dictating.

Everything here is best-effort. A desktop without `notify-send` or `paplay` loses a channel; it
must never lose the recording.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

APP_NAME = "Dito"

# Shipped with every freedesktop sound theme. Picked for being short and unambiguous rather than
# pleasant: this plays when speech is being lost.
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
        # Critical notifications stay on screen until dismissed on most desktops. Reserved for
        # audio actually being lost; using it for anything else trains the user to ignore it.
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
