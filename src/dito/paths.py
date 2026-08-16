"""Every filesystem location the app uses; one place decides and the rest asks here."""

from __future__ import annotations

import os
from pathlib import Path

APP = "dito"

# One session is one JSON file; the audio and the meeting partials sit beside it, same name.
SESSION_SUFFIX = ".json"
AUDIO_SUFFIX = ".wav"
PARTIALS_SUFFIX = ".jsonl"


def _xdg(var: str, fallback: Path) -> Path:
    # See docs/armadilhas.md 5.4: XDG_* are defined AND empty here, so `get(var, default)` lies.
    value = os.environ.get(var, "").strip()
    return Path(value).expanduser() if value else fallback


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", Path.home() / ".config") / APP


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP


def runtime_dir() -> Path:
    """Control socket home; falls back to the state dir on a session without systemd-logind."""
    value = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    return Path(value) / APP if value else state_dir()


def config_file() -> Path:
    return config_dir() / "config.toml"


def sessions_dir() -> Path:
    return data_dir() / "sessions"


def session_file(session_id: str) -> Path:
    """`2026-08-15_223322_dictation.json` — the name carries date, time and mode, no subfolder."""
    return sessions_dir() / f"{session_id}{SESSION_SUFFIX}"


def session_audio(session_id: str) -> Path:
    """The safety net while recording; it goes as soon as the transcription is on disk."""
    return sessions_dir() / f"{session_id}{AUDIO_SUFFIX}"


def session_partials(session_id: str) -> Path:
    """A meeting's chunks as they land; deleted once the final JSON carries the whole text."""
    return sessions_dir() / f"{session_id}{PARTIALS_SUFFIX}"


def log_file() -> Path:
    return state_dir() / "dito.log"


def history_file() -> Path:
    return state_dir() / "history.jsonl"


def control_socket() -> Path:
    return runtime_dir() / "dito.sock"


def ensure_dirs() -> None:
    for d in (config_dir(), data_dir(), state_dir(), sessions_dir(), runtime_dir()):
        d.mkdir(parents=True, exist_ok=True)
