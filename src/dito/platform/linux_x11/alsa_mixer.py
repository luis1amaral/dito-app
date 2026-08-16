"""ALSA capture gain — the blind spot that `pactl` alone cannot see.

PipeWire's volume and the ALSA capture gain underneath it are different knobs. This machine has
already been caught with the server reporting 94% while the hardware control read
`Capture 0 [0%]`: every reading `pactl` gives back looks healthy, and the microphone delivers
silence anyway. It is one of the plausible causes of the 99-second loss that started this project.

So the mute/volume story needs three layers, not two:

    pactl        the software mute and volume   -> a friendly, fixable message
    amixer       the hardware capture gain      -> the blind spot this module covers
    level.py     the samples themselves         -> the only thing that never lies

Nothing here raises: a machine without `amixer` simply has no such layer.
User-facing strings stay in Portuguese; they are shown in the UI.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

_TIMEOUT = 2.0
# 'Capture' covers the built-in HDA codecs, 'Mic' the USB headsets. Both appear as simple
# controls with a capture channel; the boost controls are deliberately left out, since a boost
# at zero is normal and not a fault.
_CAPTURE_CONTROLS = ("Capture", "Mic", "Digital", "Front Mic", "Rear Mic")

_PCT = re.compile(r"Capture\s+\d+\s+\[(\d+)%\].*?\[(on|off)\]", re.IGNORECASE)


def available() -> bool:
    return shutil.which("amixer") is not None


def _run(*args: str) -> str | None:
    try:
        done = subprocess.run(
            list(args), capture_output=True, text=True, timeout=_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def card_of_source(source_name: str | None) -> int | None:
    """Map a PulseAudio source to its ALSA card index, via the `alsa.card` property.

    Guessing the card would be worse than not checking: reporting the gain of the motherboard
    codec while the user records on a USB headset is a confident wrong answer.
    """
    if not source_name or not shutil.which("pactl"):
        return None
    out = _run("pactl", "list", "sources")
    if not out:
        return None
    for block in out.split("\nSource #"):
        if f"Name: {source_name}" not in block:
            continue
        found = re.search(r'alsa\.card\s*=\s*"(\d+)"', block)
        return int(found.group(1)) if found else None
    return None


@dataclass(frozen=True)
class Control:
    name: str
    pct: int
    on: bool


@dataclass(frozen=True)
class CaptureGain:
    card: int | None
    controls: tuple[Control, ...]

    @property
    def checked(self) -> bool:
        return bool(self.controls)

    @property
    def silent(self) -> bool:
        """True when every capture control is either switched off or sitting at zero. Requiring
        *all* of them avoids a false alarm on a codec that exposes several inputs and has only
        the one in use turned up."""
        return self.checked and all((not c.on) or c.pct == 0 for c in self.controls)

    @property
    def reason(self) -> str | None:
        if not self.silent:
            return None
        off = [c for c in self.controls if not c.on]
        if off:
            return f"a captura está DESLIGADA no hardware (amixer «{off[0].name}»)"
        return "o ganho de captura do hardware está em 0%"

    @property
    def fix_command(self) -> str | None:
        if not self.silent or self.card is None or not self.controls:
            return None
        return f"amixer -c {self.card} sset {self.controls[0].name},0 100% cap"


def capture_gain(card: int | None) -> CaptureGain:
    if card is None or not available():
        return CaptureGain(card, ())
    found: list[Control] = []
    for control in _CAPTURE_CONTROLS:
        out = _run("amixer", "-c", str(card), "sget", control)
        if not out:
            continue
        match = _PCT.search(out)
        if match:
            found.append(Control(control, int(match.group(1)), match.group(2).lower() == "on"))
    return CaptureGain(card, tuple(found))
