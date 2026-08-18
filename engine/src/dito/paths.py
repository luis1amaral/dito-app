"""Every filesystem location the app uses; one place decides and the rest asks here."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

APP = "dito"

# One session is one JSON file; the audio and the meeting partials sit beside it, same name.
SESSION_SUFFIX = ".json"
AUDIO_SUFFIX = ".wav"
PARTIALS_SUFFIX = ".jsonl"

_CSIDL_PERSONAL = 5


def _windows() -> bool:
    return sys.platform == "win32"


def _env(var: str, fallback: Path) -> Path:
    # See docs/armadilhas.md 5.4: the var can be defined AND empty, so `get(var, default)` lies.
    value = os.environ.get(var, "").strip()
    return Path(value).expanduser() if value else fallback


def config_dir() -> Path:
    if _windows():
        return _env("APPDATA", Path.home() / "AppData" / "Roaming") / APP
    return _env("XDG_CONFIG_HOME", Path.home() / ".config") / APP


def data_dir() -> Path:
    if _windows():
        return _env("LOCALAPPDATA", Path.home() / "AppData" / "Local") / APP
    return _env("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP


def state_dir() -> Path:
    if _windows():
        return data_dir() / "state"
    return _env("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP


def cuda_dir() -> Path:
    """The CUDA pack the Windows installer downloads — see docs/armadilhas.md 3.11."""
    return data_dir() / "cuda"


def runtime_dir() -> Path:
    """Control socket home; falls back to the state dir on a session without systemd-logind."""
    if _windows():
        return state_dir()
    value = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    return Path(value) / APP if value else state_dir()


def documents_dir() -> Path:
    """Where the recordings live. OneDrive moves this folder, so the shell is asked, not guessed."""
    if not _windows():
        return Path.home() / "Documentos"
    import ctypes

    buffer = ctypes.create_unicode_buffer(260)
    try:
        if ctypes.windll.shell32.SHGetFolderPathW(None, _CSIDL_PERSONAL, None, 0, buffer) == 0:
            return Path(buffer.value)
    except (AttributeError, OSError):
        pass
    return Path.home() / "Documents"


def default_library() -> Path:
    """A plain folder on purpose: any program picks it up as context, knowing nothing about Dito."""
    return documents_dir() / "Dito"


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


def control_socket() -> Path:
    return runtime_dir() / "dito.sock"


def ensure_dirs() -> None:
    for d in (config_dir(), data_dir(), state_dir(), sessions_dir(), runtime_dir()):
        d.mkdir(parents=True, exist_ok=True)
