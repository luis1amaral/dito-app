"""What PulseAudio/PipeWire knows about the microphone, read through `pactl`.

This is the detector that produces the RIGHT MESSAGE ("your mic is muted in the system", with a
button that unmutes it). It is not the detector that produces the TRUTH: a wireless headset can
mute inside its own dongle while the server still reports `Mute: no` and hands over zeros —
exactly the case that cost 99 seconds of speech. Truth comes from signal level (`audio/level.py`).

Nothing here raises. A machine without `pactl` simply has no such layer, and the level watchdog
still covers it alone.

User-facing strings stay in Portuguese: they are shown in the UI.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

DEFAULT_SOURCE = "@DEFAULT_SOURCE@"
_TIMEOUT = 2.0


def available() -> bool:
    return shutil.which("pactl") is not None


def _pactl(*args: str) -> str | None:
    if not available():
        return None
    try:
        done = subprocess.run(
            ["pactl", *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def is_muted(source: str = DEFAULT_SOURCE) -> bool | None:
    """True/False, or None when it could not be determined (no pactl, error, odd format)."""
    out = _pactl("get-source-mute", source)
    if not out:
        return None
    value = out.split(":", 1)[-1].strip().lower()
    if value in ("yes", "sim"):
        return True
    if value in ("no", "nao", "não"):
        return False
    return None


def volume_pct(source: str = DEFAULT_SOURCE) -> int | None:
    """Loudest channel, as a percentage. `pactl` prints something like
    `Volume: front-left: 65536 / 100% / 0,00 dB,   front-right: ...`"""
    out = _pactl("get-source-volume", source)
    if not out:
        return None
    values = []
    for part in out.split("/"):
        part = part.strip()
        if not part.endswith("%"):
            continue
        try:
            values.append(int(float(part.rstrip("%").replace(",", "."))))
        except ValueError:
            continue
    return max(values) if values else None


def unmute(source: str = DEFAULT_SOURCE) -> bool:
    return _pactl("set-source-mute", source, "0") is not None


def set_volume(pct: int, source: str = DEFAULT_SOURCE) -> bool:
    return _pactl("set-source-volume", source, f"{int(pct)}%") is not None


def default_source_name() -> str | None:
    return _pactl("get-default-source") or None


@dataclass(frozen=True)
class SourceHealth:
    muted: bool | None
    volume: int | None
    name: str | None

    @property
    def blocks_recording(self) -> bool:
        """Only blocks on CERTAIN trouble. `None` (don't know) never blocks: the level watchdog
        covers the rest, and refusing to record for lack of information is worse than recording."""
        if self.muted is True:
            return True
        return self.volume is not None and self.volume < 5

    @property
    def reason(self) -> str | None:
        if self.muted is True:
            return "o microfone está mudo no sistema"
        if self.volume is not None and self.volume < 5:
            return f"o volume de entrada está em {self.volume}%"
        return None


def health(source: str = DEFAULT_SOURCE) -> SourceHealth:
    return SourceHealth(
        muted=is_muted(source),
        volume=volume_pct(source),
        name=default_source_name(),
    )


def subscribe_events() -> subprocess.Popen[str] | None:
    """`pactl subscribe` in a subprocess, one line per event: this is how a mute that appears
    MID-RECORDING, or a device that is unplugged, gets noticed. Caller reads stdout line by line."""
    if not available():
        return None
    try:
        return subprocess.Popen(
            ["pactl", "subscribe"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except (OSError, subprocess.SubprocessError):
        return None
