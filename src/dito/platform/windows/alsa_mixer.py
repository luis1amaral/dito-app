"""Windows has no second gain layer under WASAPI, so this one answers "not checked", honestly.

On Linux this is the blind spot `pactl` cannot see. Here `audio_system` already reads the endpoint
itself, and the level watchdog is the last line — see docs/porte-windows.md.
"""

from __future__ import annotations

from ..mixer import CaptureGain, Control

__all__ = ["CaptureGain", "Control", "available", "card_of_source", "capture_gain"]


def available() -> bool:
    return False


def card_of_source(source_name: str | None) -> int | None:
    return None


def capture_gain(card: int | None) -> CaptureGain:
    """Empty controls means `checked` is False: the doctor prints "could not be checked"."""
    return CaptureGain(card, ())
