"""Sending an approved recording to the vault: only the note — docs/armadilhas.md 10.8."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod
from ..i18n import _
from ..output import notes


@dataclass(frozen=True)
class Published:
    folder: Path
    note: Path | None
    note_in_vault: bool
    warnings: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        """One line for the pill. Warnings win: silence is what caused this project to exist."""
        return self.warnings[0] if self.warnings else _("recording saved")


def publish_meeting(
    session_folder: Path,
    text: str,
    seconds: float,
    started: datetime,
    cfg: cfgmod.Config,
    subject: str = "",
) -> Published:
    """Writes the note and points it at the session already on disk; copies nothing."""
    warnings: list[str] = []
    note_path: Path | None = None
    in_vault = False

    try:
        written = notes.write_meeting_note(
            notes.MeetingNote(
                folder=session_folder,
                text=text,
                seconds=seconds,
                started=started,
                subject=subject or f"{started:%H%M}",
            ),
            cfg,
        )
        note_path, in_vault = written.path, written.in_vault
        if written.reason:
            warnings.append(written.reason)
    except OSError as exc:
        warnings.append(_("could not write the note: {error}").format(error=exc))

    return Published(
        folder=session_folder,
        note=note_path,
        note_in_vault=in_vault,
        warnings=tuple(warnings),
    )
