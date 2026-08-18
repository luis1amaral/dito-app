"""Resolves the configured input device; "it is gone" is data — docs/armadilhas.md 1.8."""

from __future__ import annotations

from dataclasses import dataclass

from ..i18n import _

SAMPLE_RATE = 16000   # what Whisper expects; resampling anything else is wasted work


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    channels: int
    default: bool

    def __str__(self) -> str:
        marca = " " + _("(default)") if self.default else ""
        return f"{self.index}: {self.name}{marca}"


def list_inputs() -> list[Device]:
    import sounddevice as sd

    try:
        default_index = sd.default.device[0]
    except Exception:
        default_index = None

    found: list[Device] = []
    try:
        devices = sd.query_devices()
    except Exception:
        return found

    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) <= 0:
            continue
        found.append(
            Device(
                index=i,
                name=str(d.get("name", f"device {i}")),
                channels=int(d["max_input_channels"]),
                default=(i == default_index),
            )
        )
    return found


def supports_rate(device: int | str | None, rate: int = SAMPLE_RATE) -> bool:
    """See docs/armadilhas.md 1.12: a raw `hw:` card refuses 16 kHz, and only fails at F9."""
    import sounddevice as sd

    try:
        sd.check_input_settings(device=device, channels=1, samplerate=rate, dtype="int16")
    except Exception:
        return False
    return True


def list_usable_inputs() -> list[Device]:
    """What the picker may offer: an input the app cannot open is not a choice, it is a trap."""
    return [d for d in list_inputs() if supports_rate(d.index)]


def resolve(setting: str) -> int | str | None:
    """Config value -> device for sounddevice; None is "default" or gone, see `missing()`."""
    setting = (setting or "").strip()
    if not setting:
        return None
    if setting.isdigit():
        index = int(setting)
        return index if any(d.index == index for d in list_inputs()) else None
    lowered = setting.lower()
    for d in list_inputs():
        if lowered in d.name.lower():
            return d.index
    return None


def missing(setting: str) -> bool:
    """True when a device was configured by name/index and is not present right now."""
    setting = (setting or "").strip()
    return bool(setting) and resolve(setting) is None


def describe(setting: str) -> str:
    resolved = resolve(setting)
    if resolved is None and (setting or "").strip():
        return _("«{device}» is not connected").format(device=setting)
    inputs = list_inputs()
    if resolved is None:
        padrao = next((d for d in inputs if d.default), None)
        return padrao.name if padrao else _("no input found")
    match = next((d for d in inputs if d.index == resolved), None)
    return match.name if match else str(resolved)
