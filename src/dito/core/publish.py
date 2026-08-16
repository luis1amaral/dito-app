"""A meeting after the stop: text, then audio, then note — see docs/armadilhas.md 7.1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..audio import encode
from ..output import notes


@dataclass(frozen=True)
class Published:
    folder: Path
    transcript: Path
    note: Path | None
    note_in_vault: bool
    audio: Path | None
    warnings: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        """One line for the pill. Warnings win: silence is what caused this project to exist."""
        return self.warnings[0] if self.warnings else "reunião salva"


def _unique(folder: Path) -> Path:
    if not folder.exists():
        return folder
    for n in range(2, 100):
        candidate = folder.with_name(f"{folder.name}-{n}")
        if not candidate.exists():
            return candidate
    return folder.with_name(f"{folder.name}-{datetime.now():%H%M%S}")


def publish_meeting(
    session_folder: Path,
    text: str,
    seconds: float,
    started: datetime,
    cfg: cfgmod.Config,
    subject: str = "",
) -> Published:
    warnings: list[str] = []
    slug = notes.slugify(subject) if subject else ""
    name = f"{started:%Y-%m-%d_%H%M}" + (f"-{slug}" if slug else "")

    target = _unique(cfg.library_dir() / name)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # The library is the user's folder and may be unwritable; the session folder keeps it.
        warnings.append(f"não consegui criar {target}: {exc}")
        target = session_folder

    transcript = target / "transcricao.md"
    transcript.write_text(_render_transcript(text, seconds, started), encoding="utf-8")

    audio = _move_audio(session_folder, target, cfg, warnings)

    note_path: Path | None = None
    in_vault = False
    try:
        written = notes.write_meeting_note(
            notes.MeetingNote(
                folder=target,
                text=text,
                seconds=seconds,
                started=started,
                subject=subject or f"reuniao-{started:%H%M}",
            ),
            cfg,
        )
        note_path, in_vault = written.path, written.in_vault
        if written.reason:
            warnings.append(written.reason)
    except OSError as exc:
        warnings.append(f"não consegui escrever a nota: {exc}")

    return Published(
        folder=target,
        transcript=transcript,
        note=note_path,
        note_in_vault=in_vault,
        audio=audio,
        warnings=tuple(warnings),
    )


def _move_audio(
    session_folder: Path, target: Path, cfg: cfgmod.Config, warnings: list[str]
) -> Path | None:
    if not cfg.meeting.save_audio:
        return None
    wav = session_folder / "audio.wav"
    if not wav.exists():
        return None

    source = wav
    if cfg.meeting.compress_audio:
        result = encode.to_opus(wav)
        if result.ok and result.path is not None:
            source = result.path
        elif result.reason:
            # Not a failure worth shouting about: the WAV is intact and the meeting is saved.
            warnings.append(f"não comprimi o áudio ({result.reason}) — o WAV foi mantido")

    destination = target / source.name
    if destination.resolve() == source.resolve():
        return destination
    try:
        source.replace(destination)
    except OSError as exc:
        warnings.append(f"o áudio ficou em {source} ({exc})")
        return source
    return destination


def _render_transcript(text: str, seconds: float, started: datetime) -> str:
    return (
        f"# Reunião de {started:%d/%m/%Y %H:%M}\n\n"
        f"Duração: {notes.hms(seconds)}\n\n"
        f"{text.strip()}\n"
    )
