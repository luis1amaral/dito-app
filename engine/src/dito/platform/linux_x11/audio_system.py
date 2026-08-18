"""What `pactl` knows about the mic — the right message, not the truth (armadilhas 1.2, 1.3)."""

from __future__ import annotations

import shutil
import subprocess

from ..source_health import SourceHealth

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
    """Loudest channel, from `Volume: front-left: 65536 / 100% / 0,00 dB, front-right: ...`."""
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


def health(source: str = DEFAULT_SOURCE) -> SourceHealth:
    return SourceHealth(
        muted=is_muted(source),
        volume=volume_pct(source),
        name=default_source_name(),
    )
