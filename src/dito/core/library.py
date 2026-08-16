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

# A session is `<stamp>_<mode>.json` plus, while they exist, the two files that share its name.
SESSION_SUFFIXES = (paths.SESSION_SUFFIX, paths.AUDIO_SUFFIX, paths.PARTIALS_SUFFIX)

# The folder layout used until 2026-08. Never written again, always still listed.
META_FILE = "session.json"
TRANSCRIPT_FILE = "transcript.jsonl"

# See docs/armadilhas.md 8.2: named, never globbed. Opus first — it was the surviving copy.
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
    # The session's JSON file; for a pre-2026-08 session, the folder it still lives in.
    path: Path
    has_audio: bool

    @property
    def done(self) -> bool:
        return self.state == DONE


def list_sessions(root: Path | None = None) -> list[SessionInfo]:
    """Newest first, both layouts. What cannot be read is listed as `unknown`, never skipped."""
    root = root or paths.sessions_dir()
    try:
        with os.scandir(root) as entries:
            found = [(Path(e.path), e.is_dir(follow_symlinks=False)) for e in entries]
    except OSError:
        return []

    stems = {p.stem for p, is_dir in found if not is_dir and p.suffix in SESSION_SUFFIXES}
    sessions = [_read_files(root, stem) for stem in stems]
    sessions += [_read_folder(p) for p, is_dir in found if is_dir and _is_legacy_session(p)]

    sessions.sort(key=lambda s: (s.started or datetime.min, s.id), reverse=True)
    return sessions


def recoverable(root: Path | None = None) -> list[SessionInfo]:
    """Everything that did not reach `done` — what the app offers to retry after a crash."""
    return [s for s in list_sessions(root) if not s.done]


def open_folder(path: Path | str) -> bool:
    """Hand the folder to the file manager; a session file opens the folder holding it."""
    target = Path(path)
    if not target.is_dir():
        target = target.parent
    try:
        subprocess.Popen(
            ["xdg-open", str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,          # outlives Dito, so closing the app keeps the window
        )
    except OSError:
        return False
    return True


def total_size(root: Path | None = None) -> int:
    return sum(s.size_bytes for s in list_sessions(root))


# ---- reading one session ----------------------------------------------------------------------


def _read_files(root: Path, stem: str) -> SessionInfo:
    """The current layout: one JSON, and the audio only while there is no text to replace it."""
    meta_path = root / f"{stem}{paths.SESSION_SUFFIX}"
    audio = root / f"{stem}{paths.AUDIO_SUFFIX}"
    partials = root / f"{stem}{paths.PARTIALS_SUFFIX}"

    meta = _load_meta(meta_path)
    stamp, mode_from_name = _from_name(stem)

    seconds = _as_float(meta.get("seconds"))
    if seconds <= 0:
        seconds = _wav_seconds(audio)

    text = _as_str(meta.get("text")) or _transcript_head(partials)

    return SessionInfo(
        id=_as_str(meta.get("id")) or stem,
        mode=_as_str(meta.get("mode")) or mode_from_name,
        started=_parse_started(meta.get("started")) or stamp,
        seconds=seconds,
        size_bytes=sum(_size(p) for p in (meta_path, audio, partials)),
        preview=_preview(text),
        state=_as_str(meta.get("state")) or UNKNOWN,
        path=meta_path,
        has_audio=audio.is_file(),
    )


def _read_folder(folder: Path) -> SessionInfo:
    """A session recorded before one-file sessions: same fields, read out of the old folder."""
    meta = _load_meta(folder / META_FILE)
    stamp, mode_from_name = _from_name(folder.name)

    seconds = _as_float(meta.get("seconds"))
    if seconds <= 0:
        seconds = _wav_seconds(folder / "audio.wav")

    text = _as_str(meta.get("text")) or _transcript_head(folder / TRANSCRIPT_FILE)

    return SessionInfo(
        id=_as_str(meta.get("id")) or folder.name,
        mode=_as_str(meta.get("mode")) or mode_from_name,
        started=_parse_started(meta.get("started")) or stamp,
        seconds=seconds,
        size_bytes=_folder_size(folder),
        preview=_preview(text),
        state=_as_str(meta.get("state")) or UNKNOWN,
        path=folder,
        has_audio=any((folder / name).is_file() for name in AUDIO_FILES),
    )


def _is_legacy_session(folder: Path) -> bool:
    """Only what an old session left behind; another folder in here is not a recording."""
    if _from_name(folder.name)[0] is not None:
        return True
    return any((folder / name).is_file() for name in (META_FILE, TRANSCRIPT_FILE, *AUDIO_FILES))


def _load_meta(path: Path) -> dict[str, Any]:
    """Anything unreadable reads as "no metadata"; the file name still describes the session."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _from_name(name: str) -> tuple[datetime | None, str]:
    """`2026-08-15_143200_meeting` -> the metadata a corrupt JSON cannot take away."""
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


def _wav_seconds(path: Path) -> float:
    """Physical size, not the declared one: armadilhas 1.4 — the RIFF header under-reports."""
    size = _size(path)
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


def _size(path: Path) -> int:
    """Symlinks are measured as links — armadilhas 6.3: that disk is not ours to report."""
    try:
        return path.lstat().st_size
    except OSError:
        return 0


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


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_float(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
