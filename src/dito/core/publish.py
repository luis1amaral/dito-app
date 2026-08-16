"""What happens to a meeting after the recording stops.

Three steps, in this order, and the order is the point:

  1. **Write the text first.** It is small, it never fails, and it is the thing the user came for.
     Compressing before writing would mean a crash in the encoder costs the transcript too.
  2. **Compress the audio.** Only after the Opus has been decoded back and verified does the WAV
     go — see audio/encode.py. Losing audio is the one thing this project does not do.
  3. **Write the Obsidian note.** Last, because it is the step most likely to be refused (the
     vault may not exist, and the rule is not to create it), and a refusal must not take the
     first two down with it.

The session folder under ~/.local/share stays the working area. The library folder is where the
user's own copy lands, because "abrir a pasta" should open something recognisable and not a
timestamped directory inside a dotfile tree.
"""

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
        # The library is the user's folder and can be anywhere, including somewhere unwritable.
        # Falling back to the session folder keeps the meeting rather than losing it.
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
