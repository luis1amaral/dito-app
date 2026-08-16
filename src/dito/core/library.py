"""The index of everything that was recorded — what the "Transcrições" tab lists, and what the
retention policy acts on.

Two opposite rules shape this module.

**Reading is defensive.** A folder whose `session.json` was truncated by a crash is precisely the
one the user came looking for; raising on it would hide every *other* session as well. So nothing
here throws: an unreadable folder is still listed, as `unknown`, with whatever the folder name and
the files on disk can tell us.

**Deleting is narrow.** Garbage collection removes audio files it knows by name, only from
sessions that finished with text, only past the configured window. It never touches
`session.json` or `transcript.jsonl`: those are a few kB, and they are the part that cannot be
recovered from anything else on disk.
"""

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

# Named, never globbed: this tuple is the list of things garbage collection is allowed to delete,
# and a glob is one typo away from taking the transcript with it. Opus first — after compression
# it is the surviving copy.
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
    """Hand the folder to the file manager. Returns whether the command started; a desktop with
    no `xdg-open` is a missing convenience, never a reason to take a click down with a traceback."""
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

        # And never a `done` session with no text either. That is the failure from armadilhas 1.1
        # — the microphone delivered zeros, Whisper recognized nothing, the session closed clean —
        # and the WAV is the only remaining evidence of what was said.
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
    """Anything unreadable reads as "no metadata" — the folder name and the files still describe
    the session well enough to list it and to offer it for recovery."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _from_folder_name(name: str) -> tuple[datetime | None, str]:
    """`2026-08-15_143200_meeting` -> the timestamp and the mode. The folder name is the one piece
    of metadata a corrupt `session.json` cannot take away."""
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
    # session.py writes naive local timestamps; a hand-edited aware one must not blow up the
    # comparison against `datetime.now()` further down.
    return when.astimezone().replace(tzinfo=None) if when.tzinfo else when


def _wav_seconds(folder: Path) -> float:
    """Duration straight from the size on disk, for the crashed session whose `session.json` still
    says 0 seconds. Physical size rather than the declared one on purpose: a process killed
    mid-recording leaves bytes past the size the RIFF header admits to (armadilhas 1.4), and here
    the point is to show the user how much audio is really there."""
    path = folder / "audio.wav"
    try:
        size = path.stat().st_size
    except OSError:
        return 0.0
    if size <= _WAV_HEADER:
        return 0.0
    return (size - _WAV_HEADER) / (SAMPLE_RATE * 2)      # int16 mono, what writer.py records


def _transcript_head(path: Path, lines: int = 5) -> str:
    """A meeting that crashed has no `text` in its metadata, but every chunk it managed to
    transcribe is already in the jsonl. Enough of it for a preview costs one small read."""
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
    """Symlinks are not followed and not counted: a linked file lives somewhere else and counting
    it here would report disk that deleting this folder does not give back (armadilhas 6.3)."""
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
    """`None` = keep forever. Zero means the same thing in the config (see `Retention`), and an
    unrecognized mode is never collected: guessing wrong here deletes audio."""
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
    """Fallback for a session with no usable timestamp anywhere. Returns 0 — "as new as it gets" —
    when even the folder cannot be stat'd, because the safe answer is to keep the audio."""
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
