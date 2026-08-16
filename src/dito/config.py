"""Typed dataclasses <-> TOML: atomic writes, unknown keys preserved, versioned schema."""

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
    # XGrabKey consumes the key instead of observing it — see docs/armadilhas.md 2.6.
    grab: bool = True


@dataclass
class Alerts:
    # Measured, not guessed — see docs/armadilhas.md 1.6.
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
    # Off by default — see docs/armadilhas.md 10.4: the vault is a git repo with auto-commit.
    copy_audio: bool = False


@dataclass
class Meeting:
    # A meeting has no time cap: it records until told to stop. That is a requirement, not a
    # default, so there is deliberately no setting for it.
    obsidian: Obsidian = field(default_factory=Obsidian)


@dataclass
class Library:
    folder: str = "~/Documentos/Dito"


@dataclass
class Ui:
    theme: str = "auto"               # auto | light | dark
    # Interface language, independent of `stt.language`, which is what Whisper transcribes.
    language: str = "auto"            # auto | en | pt_BR
    tray: bool = True


@dataclass
class Config:
    schema: int = SCHEMA
    hotkeys: Hotkeys = field(default_factory=Hotkeys)
    audio: Audio = field(default_factory=Audio)
    stt: Stt = field(default_factory=Stt)
    output: Output = field(default_factory=Output)
    meeting: Meeting = field(default_factory=Meeting)
    library: Library = field(default_factory=Library)
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
            # bool before int: `isinstance(True, int)` is True, so int first lets `dead_ms = true`
            # slip through as 1.
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
            # Wrong type keeps the default and preserves the value, so saving loses nothing.
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
        # Unreadable config never blocks startup; the broken file is kept, not overwritten.
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
