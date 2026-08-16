"""ALSA hardware capture gain — the blind spot `pactl` cannot see (docs/armadilhas.md 1.2)."""

from __future__ import annotations

import re
import shutil
import subprocess

from ..mixer import CaptureGain, Control

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
