"""Every filesystem location the app uses; one place decides and the rest asks here."""

from __future__ import annotations

import os
from datetime import datetime
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


def session_dir(root: Path, started: datetime) -> Path:
    """`<root>/2026/08/16`: a year of dictation has to stay findable by hand, by anyone."""
    return root / f"{started:%Y}" / f"{started:%m}" / f"{started:%d}"


def session_stem(started: datetime) -> str:
    """`07-42-13` — the second the recording began, which is what makes the name unique."""
    return f"{started:%H-%M-%S}"


def free_stem(folder: Path, stem: str) -> str:
    """Two keys pressed in the same second must not overwrite each other, so the second gets -2."""
    candidate, n = stem, 1
    while (folder / f"{candidate}{SESSION_SUFFIX}").exists():
        n += 1
        candidate = f"{stem}-{n}"
    return candidate


def selftest_audio() -> Path:
    """Outside sessions/: a diagnostic is not a recording, and seven of them once showed up in
    the window as «to recover». One file, overwritten each run."""
    return state_dir() / "selftest.wav"


def log_file() -> Path:
    return state_dir() / "dito.log"


def history_file() -> Path:
    return state_dir() / "history.jsonl"


def control_socket() -> Path:
    return runtime_dir() / "dito.sock"


def ensure_dirs() -> None:
    for d in (config_dir(), data_dir(), state_dir(), sessions_dir(), runtime_dir()):
        d.mkdir(parents=True, exist_ok=True)
