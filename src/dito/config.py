"""Typed dataclasses <-> TOML at ~/.config/dito/config.toml.

Three properties this module has to hold:

1. **Atomic writes.** Serialize to a temp file in the SAME directory, then `os.replace`. Half a
   config on disk is worse than a stale one: a truncated TOML fails to parse, the app silently
   falls back to defaults, and the user's hotkeys are gone.

2. **Unknown keys survive.** Anything the current schema does not know goes to `_extras` and is
   written back out. Without it, opening a config written by a newer version — or hand-edited —
   would quietly drop whatever it had extra.

3. **A versioned `schema`**, so a future migration is a decision rather than a guess.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import tomli_w

from . import paths

SCHEMA = 1


@dataclass
class Hotkeys:
    push_to_talk: str = "f9"
    meeting_toggle: str = "f10"
    cancel: str = "space"
    # XGrabKey CONSUMES the key instead of merely observing it. Without it the cancel key types a
    # character into whatever field has focus on X11 — pynput's suppress_event is win32-only.
    grab: bool = True


@dataclass
class Alerts:
    # Thresholds come from audio actually measured on this machine, not from a guess: speech
    # peaks at 0.036-0.272 and the headset's room-tone floor is 0.0038. Exact digital silence is
    # the observed failure mode — 99s recorded at peak=0.0000. See audio/level.py.
    dead_ms: int = 700       # peak < 1e-4 for this long => NO AUDIO (red)
    quiet_ms: int = 2500     # peak < 8e-3 for this long, before any sound => too quiet (amber)
    sound: bool = True
    notify: bool = True


@dataclass
class Audio:
    device: str = ""         # "" = system default; index ("2") or name fragment ("H510")
    alerts: Alerts = field(default_factory=Alerts)


@dataclass
class Stt:
    model: str = "small"
    language: str = "pt"
    device: str = "auto"     # auto | cpu | cuda
    beam_dictation: int = 5
    beam_meeting: int = 1
    idle_unload_min: float = 10.0


@dataclass
class Output:
    paste: bool = True
    enter: bool = True
    confirm: bool = True
    restore_clipboard: bool = True


@dataclass
class Obsidian:
    vault: str = "~/notas"
    folder: str = "trabalho"
    # The vault is a git repo with auto-commit: tens of MB of audio committed by accident is
    # expensive to remove from history. The note links to the session folder instead.
    copy_audio: bool = False


@dataclass
class Meeting:
    save_audio: bool = True
    compress_audio: bool = True
    # 0 = NO LIMIT. Records until told to stop — explicit requirement. What replaces a time cap
    # is the low-disk warning below, which warns and never interrupts.
    max_hours: float = 0.0
    low_disk_warn_gb: float = 2.0
    obsidian: Obsidian = field(default_factory=Obsidian)


@dataclass
class Library:
    folder: str = "~/Documentos/Dito"


@dataclass
class Retention:
    dictation_audio_hours: float = 48.0
    meeting_audio_days: float = 0.0   # 0 = keep forever


@dataclass
class Ui:
    theme: str = "auto"               # auto | light | dark
    # Interface language, independent of `stt.language`, which is what Whisper transcribes.
    language: str = "auto"            # auto | en | pt_BR
    overlay_position: str = "bottom-center"
    tray: bool = True
    autostart: bool = True


@dataclass
class Config:
    schema: int = SCHEMA
    hotkeys: Hotkeys = field(default_factory=Hotkeys)
    audio: Audio = field(default_factory=Audio)
    stt: Stt = field(default_factory=Stt)
    output: Output = field(default_factory=Output)
    meeting: Meeting = field(default_factory=Meeting)
    library: Library = field(default_factory=Library)
    retention: Retention = field(default_factory=Retention)
    ui: Ui = field(default_factory=Ui)

    _extras: dict[str, Any] = field(default_factory=dict, repr=False)

    def library_dir(self) -> Path:
        return Path(self.library.folder).expanduser()

    def vault_dir(self) -> Path:
        return Path(self.meeting.obsidian.vault).expanduser()


def _fill(cls: type, data: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """Build the dataclass from what it knows; hand back everything left over."""
    known = {f.name for f in fields(cls) if not f.name.startswith("_")}
    defaults = cls()
    kwargs: dict[str, Any] = {}
    leftover: dict[str, Any] = {}

    for key, value in data.items():
        if key not in known:
            leftover[key] = value
            continue
        default = getattr(defaults, key)

        if is_dataclass(default) and isinstance(value, dict):
            child, child_leftover = _fill(type(default), value)
            kwargs[key] = child
            if child_leftover:
                leftover[key] = child_leftover
        elif isinstance(default, bool):
            # bool before int: in Python `isinstance(True, int)` is True, so checking int first
            # would let `dead_ms = true` through as the integer 1.
            if isinstance(value, bool):
                kwargs[key] = value
            else:
                leftover[key] = value
        elif isinstance(default, float) and _is_number(value):
            kwargs[key] = float(value)
        elif isinstance(default, int) and isinstance(value, int) and not isinstance(value, bool):
            kwargs[key] = value
        elif isinstance(default, str) and isinstance(value, str):
            kwargs[key] = value
        else:
            # A wrong type in the file must not take the app down: keep the default, and preserve
            # the offending value so saving does not delete what the user wrote.
            leftover[key] = value

    return cls(**kwargs), leftover


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load(path: Path | None = None) -> Config:
    path = path or paths.config_file()
    if not path.exists():
        return Config()
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError):
        # An unreadable config must never stop dictation from starting. Defaults take over, and
        # the broken file is kept under another name instead of being silently overwritten.
        try:
            path.replace(path.with_suffix(".toml.broken"))
        except OSError:
            pass
        return Config()
    cfg, leftover = _fill(Config, data)
    cfg._extras = leftover
    return cfg


def _merge(base: dict[str, Any], extras: dict[str, Any]) -> dict[str, Any]:
    for key, value in extras.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def save(cfg: Config, path: Path | None = None) -> Path:
    path = path or paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in asdict(cfg).items() if not k.startswith("_")}
    data = _merge(data, cfg._extras)

    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as fh:
        tomli_w.dump(data, fh)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)          # atomic within the same filesystem
    return path
