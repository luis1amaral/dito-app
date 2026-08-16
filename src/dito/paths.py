"""Every filesystem location the app uses. One place decides; the rest asks here.

XDG_* variables can be DEFINED AND EMPTY — that is the case on this machine, where Cinnamon
exports none of them. `os.environ.get("XDG_CONFIG_HOME", fallback)` returns the empty string in
that case, and `Path("") / "dito"` is the RELATIVE path `dito/`, created inside whatever the
caller's working directory happens to be. `_xdg` treats empty as absent for that reason.
"""

from __future__ import annotations

import os
from pathlib import Path

APP = "dito"


def _xdg(var: str, fallback: Path) -> Path:
    value = os.environ.get(var, "").strip()
    return Path(value).expanduser() if value else fallback


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", Path.home() / ".config") / APP


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP


def runtime_dir() -> Path:
    """$XDG_RUNTIME_DIR is a tmpfs wiped at logout — the right home for the control socket.
    Without it (a session with no systemd-logind), fall back to the state dir, which at least
    exists and is writable."""
    value = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    return Path(value) / APP if value else state_dir()


def config_file() -> Path:
    return config_dir() / "config.toml"


def sessions_dir() -> Path:
    return data_dir() / "sessions"


def log_file() -> Path:
    return state_dir() / "dito.log"


def history_file() -> Path:
    return state_dir() / "history.jsonl"


def control_socket() -> Path:
    return runtime_dir() / "dito.sock"


def ensure_dirs() -> None:
    for d in (config_dir(), data_dir(), state_dir(), sessions_dir(), runtime_dir()):
        d.mkdir(parents=True, exist_ok=True)
