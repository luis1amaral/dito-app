"""The input list, and the trap it was: offering a microphone the app can never open.

Written against a live defect — every F9 answered «microphone unavailable: Invalid sample rate»
while the same microphone recorded fine everywhere else on the machine. The chosen device was a
raw ALSA card that does not do 16 kHz, and the app's own picker had offered it. See
docs/armadilhas.md 1.12.
"""

from __future__ import annotations

from dito.audio import devices


def _fake(index: int, name: str, default: bool = False) -> devices.Device:
    return devices.Device(index=index, name=name, channels=2, default=default)


THIS_MACHINE = [
    _fake(4, "HD-Audio Generic: ALC887-VD Analog (hw:1,0)"),
    _fake(5, "HD-Audio Generic: ALC887-VD Alt Analog (hw:1,2)"),
    _fake(7, "pipewire"),
    _fake(8, "default", default=True),
]
OPENS = {7, 8}


def _wire(monkeypatch) -> None:
    monkeypatch.setattr(devices, "list_inputs", lambda: THIS_MACHINE)
    monkeypatch.setattr(devices, "supports_rate", lambda index, rate=16000: index in OPENS)


def test_the_picker_drops_what_cannot_open_at_the_apps_rate(monkeypatch):
    _wire(monkeypatch)
    usable = [d.name for d in devices.list_usable_inputs()]
    assert usable == ["pipewire", "default"]


def test_a_device_that_is_present_can_still_be_unusable(monkeypatch):
    """`missing()` answers "is it there", which is not the same question as "does it record"."""
    _wire(monkeypatch)
    pinned = "HD-Audio Generic: ALC887-VD Alt Analog (hw:1,2)"
    assert not devices.missing(pinned)
    assert devices.resolve(pinned) == 5
    assert not devices.supports_rate(devices.resolve(pinned))


def test_supports_rate_says_no_instead_of_raising():
    """It runs inside preflight: an exception there is a dead hotkey, not a refusal."""
    assert devices.supports_rate(999_999) is False


def test_describe_carries_no_hardcoded_portuguese():
    """Source strings are English and go through gettext — this module was missed in that pass."""
    source = (devices.__file__ or "").replace("__pycache__", "")
    text = open(source, encoding="utf-8").read()
    for leftover in ("não está conectado", "nenhuma entrada", "(padrão)"):
        assert leftover not in text
