"""ALSA hardware capture gain — the blind spot `pactl` cannot see (docs/armadilhas.md 1.2)."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

_TIMEOUT = 2.0
# See docs/armadilhas.md 9.3: HDA and USB names, and no boost control — boost at 0 is normal.
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
    """Source -> ALSA card via `alsa.card`; armadilhas 1.2: guessing is worse than not checking."""
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
        """Only when ALL controls are off or at zero — armadilhas 9.3: less cries wolf."""
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
