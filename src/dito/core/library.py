"""The index of what was recorded. See docs/armadilhas.md 8: read defensive, delete narrow."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import paths
from ..audio.devices import SAMPLE_RATE
from ..config import Config

META_FILE = "session.json"
TRANSCRIPT_FILE = "transcript.jsonl"

# See docs/armadilhas.md 8.2: named, never globbed. Opus first — it is the surviving copy.
AUDIO_FILES = ("audio.opus", "audio.wav")

# States written by core/session.py::_write_meta. Anything else on disk reads as UNKNOWN.
DONE = "done"
UNKNOWN = "unknown"

MODE_DICTATION = "dictation"
MODE_MEETING = "meeting"

PREVIEW_CHARS = 90

_STAMP_FORMAT = "%Y-%m-%d_%H%M%S"
_WAV_HEADER = 44


@dataclass(frozen=True)
class SessionInfo:
    id: str
    mode: str
    started: datetime | None
    seconds: float
    size_bytes: int
    preview: str
    state: str
    folder: Path
    has_audio: bool

    @property
    def done(self) -> bool:
        return self.state == DONE


def list_sessions(root: Path | None = None) -> list[SessionInfo]:
    """Newest first. A folder that cannot be read is listed as `unknown`, never skipped."""
    root = root or paths.sessions_dir()
    try:
        with os.scandir(root) as entries:
            folders = [Path(e.path) for e in entries if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []

    sessions = [_read(folder) for folder in folders]
    sessions.sort(key=lambda s: (s.started or datetime.min, s.id), reverse=True)
    return sessions


def recoverable(root: Path | None = None) -> list[SessionInfo]:
    """Everything that did not reach `done` — what the app offers to retry after a crash."""
    return [s for s in list_sessions(root) if not s.done]


def open_folder(path: Path | str) -> bool:
    """Hand the folder to the file manager; a missing `xdg-open` is never worth a traceback."""
    try:
        subprocess.Popen(
            ["xdg-open", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,          # outlives Dito, so closing the app keeps the window
        )
    except OSError:
        return False
    return True


def collect_garbage(
    cfg: Config, root: Path | None = None, now: datetime | None = None
) -> int:
    """Apply the retention policy to recorded audio. Returns the bytes freed."""
    now = now or datetime.now()
    freed = 0

    for session in list_sessions(root):
        window = _retention_seconds(cfg, session.mode)
        if window is None or not session.has_audio:
            continue

        # Never the audio of a session that failed: that is the one the user will want back.
        if not session.done:
            continue

        # See docs/armadilhas.md 1.1: with no text, the WAV is the only evidence of what was said.
        if not session.preview:
            continue

        if _age_seconds(session, now) < window:
            continue

        for name in AUDIO_FILES:
            freed += _remove(session.folder / name)

    return freed


def total_size(root: Path | None = None) -> int:
    return sum(s.size_bytes for s in list_sessions(root))


# ---- reading one folder ---------------------------------------------------------------------


def _read(folder: Path) -> SessionInfo:
    meta = _load_meta(folder / META_FILE)
    stamp, mode_from_name = _from_folder_name(folder.name)

    seconds = _as_float(meta.get("seconds"))
    if seconds <= 0:
        seconds = _wav_seconds(folder)

    text = _as_str(meta.get("text")) or _transcript_head(folder / TRANSCRIPT_FILE)

    return SessionInfo(
        id=_as_str(meta.get("id")) or folder.name,
        mode=_as_str(meta.get("mode")) or mode_from_name,
        started=_parse_started(meta.get("started")) or stamp,
        seconds=seconds,
        size_bytes=_folder_size(folder),
        preview=_preview(text),
        state=_as_str(meta.get("state")) or UNKNOWN,
        folder=folder,
        has_audio=any((folder / name).is_file() for name in AUDIO_FILES),
    )


def _load_meta(path: Path) -> dict[str, Any]:
    """Anything unreadable reads as "no metadata"; the folder name still describes the session."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _from_folder_name(name: str) -> tuple[datetime | None, str]:
    """`2026-08-15_143200_meeting` -> the metadata a corrupt `session.json` cannot take away."""
    stamp, _, mode = name.rpartition("_")
    try:
        when = datetime.strptime(stamp, _STAMP_FORMAT)
    except ValueError:
        when = None
    return when, mode if mode in (MODE_DICTATION, MODE_MEETING) else UNKNOWN


def _parse_started(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    # session.py writes naive local stamps; a hand-edited aware one must still compare to now().
    return when.astimezone().replace(tzinfo=None) if when.tzinfo else when


def _wav_seconds(folder: Path) -> float:
    """Physical size, not the declared one: armadilhas 1.4 — the RIFF header under-reports."""
    path = folder / "audio.wav"
    try:
        size = path.stat().st_size
    except OSError:
        return 0.0
    if size <= _WAV_HEADER:
        return 0.0
    return (size - _WAV_HEADER) / (SAMPLE_RATE * 2)      # int16 mono, what writer.py records


def _transcript_head(path: Path, lines: int = 5) -> str:
    """A crashed meeting has no `text` in its metadata, but its chunks are already in the jsonl."""
    try:
        with path.open(encoding="utf-8") as fh:
            heads = [next(fh, "") for _ in range(lines)]
    except OSError:
        return ""

    parts = []
    for line in heads:
        try:
            parts.append(str(json.loads(line).get("text", "")))
        except (ValueError, AttributeError):
            continue
    return " ".join(p for p in parts if p)


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= PREVIEW_CHARS:
        return flat
    cut = flat[:PREVIEW_CHARS].rsplit(" ", 1)[0]
    return f"{cut or flat[:PREVIEW_CHARS]}…"


def _folder_size(folder: Path) -> int:
    """Symlinks are neither followed nor counted — armadilhas 6.3: that disk is not ours to free."""
    total = 0
    stack = [folder]
    while stack:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    return total


# ---- retention ------------------------------------------------------------------------------


def _retention_seconds(cfg: Config, mode: str) -> float | None:
    """`None` (and 0 in the config) = keep forever; an unknown mode is never collected."""
    if mode == MODE_DICTATION:
        hours = cfg.retention.dictation_audio_hours
        return hours * 3600 if hours > 0 else None
    if mode == MODE_MEETING:
        days = cfg.retention.meeting_audio_days
        return days * 86400 if days > 0 else None
    return None


def _age_seconds(session: SessionInfo, now: datetime) -> float:
    if session.started is not None:
        return (now - session.started).total_seconds()
    return _mtime_age(session.folder, now)


def _mtime_age(folder: Path, now: datetime) -> float:
    """Last resort; returns 0 ("brand new") when even the stat fails, so the audio is kept."""
    try:
        modified = datetime.fromtimestamp(folder.stat().st_mtime)
    except OSError:
        return 0.0
    return (now - modified).total_seconds()


def _remove(path: Path) -> int:
    try:
        size = path.stat().st_size
        path.unlink()
    except OSError:
        return 0
    return size


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_float(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
