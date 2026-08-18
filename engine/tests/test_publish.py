"""Sending an approved recording to the vault.

Publishing writes **one** thing: the note. It used to also copy the transcript into a folder of
its own inside the library, which duplicated text the session JSON already held and — worse —
left a folder the retention sweep could never reach, because it is not shaped like a date. See
docs/armadilhas.md 10.8.

Audio never gets here: the session deletes the WAV the moment the transcription is on disk.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from dito import config as cfgmod
from dito.core import publish

STARTED = datetime(2026, 8, 15, 14, 30)
TEXT = "Ficou combinado que o Luis manda a proposta na sexta."


@pytest.fixture
def cfg(tmp_path: Path) -> cfgmod.Config:
    c = cfgmod.Config()
    c.library.folder = str(tmp_path / "Documentos" / "Dito")
    c.meeting.obsidian.vault = str(tmp_path / "notas")
    return c


def session_day(cfg: cfgmod.Config) -> Path:
    """Where a session lives now: `<biblioteca>/2026/08/15`, filed by date."""
    folder = cfg.library_dir() / "2026" / "08" / "15"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "14-30-00.json").write_text("{}", encoding="utf-8")
    return folder


def test_publishing_writes_the_note_and_nothing_else(tmp_path, cfg):
    """The library gains no folder: the session is already in it, and a second copy of the text
    is one more thing to keep in sync and one the sweep cannot clean."""
    day = session_day(cfg)
    before = sorted(p.name for p in cfg.library_dir().iterdir())

    result = publish.publish_meeting(day, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert sorted(p.name for p in cfg.library_dir().iterdir()) == before
    assert result.folder == day
    assert result.note is not None and result.note.exists()


def test_the_note_points_at_the_session_on_disk(tmp_path, cfg):
    (tmp_path / "notas" / "trabalho").mkdir(parents=True)
    day = session_day(cfg)

    result = publish.publish_meeting(day, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    body = result.note.read_text(encoding="utf-8")
    assert TEXT in body, "a transcrição tem que estar na nota, é o único lugar agora"
    assert day.name in body


def test_publishing_never_touches_the_audio(tmp_path, cfg):
    """Deleting the WAV is the session's decision, taken the moment the text reached disk. If one
    is still here it is because there was nothing to replace it, and publishing must not take it."""
    day = session_day(cfg)
    wav = day / "14-30-00.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 4000)

    publish.publish_meeting(day, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert wav.is_file(), "publicar mexeu no áudio da sessão"


def test_note_goes_to_the_vault_when_it_exists(tmp_path, cfg):
    (tmp_path / "notas" / "trabalho").mkdir(parents=True)
    day = session_day(cfg)

    result = publish.publish_meeting(day, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert result.note_in_vault
    assert result.note is not None
    assert result.note.parent == tmp_path / "notas" / "trabalho"
    assert not result.warnings


def test_a_missing_vault_is_not_created_and_the_note_still_lands(tmp_path, cfg):
    """The `reuniao` skill's rule: do not create the vault. Losing the note over it would be a far
    worse answer than putting it beside the recording and saying so."""
    day = session_day(cfg)

    result = publish.publish_meeting(day, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert not (tmp_path / "notas").exists()
    assert not result.note_in_vault
    assert result.note is not None and result.note.exists()
    assert result.note.parent == day, "a nota fica junto da sessão que ela descreve"
    assert result.warnings and "vault" in result.warnings[0]


def test_two_recordings_with_the_same_subject_do_not_collide(tmp_path, cfg):
    (tmp_path / "notas" / "trabalho").mkdir(parents=True)
    day = session_day(cfg)

    first = publish.publish_meeting(day, TEXT, 60.0, STARTED, cfg, "Diária")
    second = publish.publish_meeting(day, TEXT, 60.0, STARTED, cfg, "Diária")

    assert first.note != second.note
    assert first.note.exists() and second.note.exists()


def test_the_note_beside_the_session_is_not_mistaken_for_a_recording(tmp_path, cfg):
    """It lands in the date folder, so the listing has to tell a note from a session — otherwise
    the app offers to «recuperar» something that was already saved."""
    from dito.core import library

    day = session_day(cfg)
    (day / "14-30-00.json").unlink()

    publish.publish_meeting(day, TEXT, 60.0, STARTED, cfg, "Orçamento")

    assert library.list_sessions(cfg.library_dir()) == []


def test_a_subject_cannot_escape_the_vault_folder(tmp_path, cfg):
    (tmp_path / "notas" / "trabalho").mkdir(parents=True)
    day = session_day(cfg)

    result = publish.publish_meeting(day, TEXT, 60.0, STARTED, cfg, "../../etc/passwd")

    assert result.note.parent == tmp_path / "notas" / "trabalho"


def test_message_prefers_the_warning_over_the_happy_path():
    """Silence about a problem is what this whole project exists to prevent."""
    quiet = publish.Published(Path("/tmp"), Path("/tmp/n.md"), False, ())
    loud = publish.Published(Path("/tmp"), Path("/tmp/n.md"), False, ("deu ruim",))
    assert quiet.message == "recording saved"
    assert loud.message == "deu ruim"
