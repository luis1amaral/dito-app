"""A meeting after the stop: text, then note — docs/armadilhas.md 10.1. Audio never gets here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..output import notes


@dataclass(frozen=True)
class Published:
    folder: Path
    transcript: Path
    note: Path | None
    note_in_vault: bool
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
        # The library is the user's folder and may be unwritable; Dito's own space keeps it.
        warnings.append(f"não consegui criar {target}: {exc}")
        target = _unique(session_folder / name)
        target.mkdir(parents=True, exist_ok=True)

    transcript = target / "transcricao.md"
    transcript.write_text(_render_transcript(text, seconds, started), encoding="utf-8")

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
        warnings=tuple(warnings),
    )


def _render_transcript(text: str, seconds: float, started: datetime) -> str:
    return (
        f"# Reunião de {started:%d/%m/%Y %H:%M}\n\n"
        f"Duração: {notes.hms(seconds)}\n\n"
        f"{text.strip()}\n"
    )
