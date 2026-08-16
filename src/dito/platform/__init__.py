"""Which backend the rest of the app talks to. `sys.platform` is decided here and nowhere else.

Above this line nobody names a platform: `app.py`, `cli.py` and `core/session.py` ask for
`instance` or `hotkeys` and get whichever one this machine has.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .windows import alsa_mixer, audio_system, focus, hotkeys, instance, notify
else:
    from .linux_x11 import alsa_mixer, audio_system, focus, hotkeys, instance, notify

FocusBroker = focus.FocusBroker
HotkeyManager = hotkeys.HotkeyManager
KeyMode = hotkeys.Mode

__all__ = [
    "FocusBroker",
    "HotkeyManager",
    "KeyMode",
    "alsa_mixer",
    "audio_system",
    "focus",
    "hotkeys",
    "instance",
    "notify",
]
