"""Publishing a meeting: text and note reaching the user's own folder.

Audio is not part of this any more — the session deletes the WAV as soon as the transcription is
on disk, so what publishing owes the user is the text, the note, and never losing either.
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


def make_sessions(tmp_path: Path) -> Path:
    """Where the session's files live: one folder for all of them, one file per session."""
    folder = tmp_path / "sessions"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def test_transcript_lands_in_the_library_folder(tmp_path, cfg):
    sessions = make_sessions(tmp_path)
    result = publish.publish_meeting(sessions, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert result.folder.parent == cfg.library_dir()
    assert "orcamento" in result.folder.name
    assert result.transcript.exists()
    body = result.transcript.read_text(encoding="utf-8")
    assert TEXT in body
    assert "15/08/2026" in body


def test_publishing_never_touches_the_audio(tmp_path, cfg):
    """Deleting the WAV is the session's decision, taken the moment the text reached disk. If one
    is still here it is because there was nothing to replace it, and publishing must not take it."""
    sessions = make_sessions(tmp_path)
    wav = sessions / "2026-08-15_143000_meeting.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 4000)

    result = publish.publish_meeting(sessions, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert wav.is_file(), "publicar mexeu no áudio da sessão"
    assert list(result.folder.glob("*.wav")) == [], "só o texto vai para a biblioteca"
    assert list(result.folder.glob("*.opus")) == []


def test_note_goes_to_the_vault_when_it_exists(tmp_path, cfg):
    (tmp_path / "notas" / "trabalho").mkdir(parents=True)
    sessions = make_sessions(tmp_path)
    result = publish.publish_meeting(sessions, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert result.note_in_vault
    assert result.note is not None
    assert result.note.parent == tmp_path / "notas" / "trabalho"
    assert not result.warnings


def test_a_missing_vault_is_not_created_and_the_meeting_still_lands(tmp_path, cfg):
    """The `reuniao` skill's rule: do not create the vault. Losing the meeting over it would be
    a far worse answer than putting the note beside the transcript and saying so."""
    sessions = make_sessions(tmp_path)
    result = publish.publish_meeting(sessions, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert not (tmp_path / "notas").exists()
    assert not result.note_in_vault
    assert result.note is not None and result.note.exists()
    assert result.warnings and "vault" in result.warnings[0]
    assert result.transcript.exists(), "a ressalva na nota não pode custar a transcrição"


def test_two_meetings_with_the_same_subject_do_not_collide(tmp_path, cfg):
    sessions = make_sessions(tmp_path)
    first = publish.publish_meeting(sessions, TEXT, 60.0, STARTED, cfg, "Diária")
    second = publish.publish_meeting(sessions, TEXT, 60.0, STARTED, cfg, "Diária")

    assert first.folder != second.folder
    assert first.transcript.exists() and second.transcript.exists()


def test_an_unwritable_library_falls_back_to_the_session_space(tmp_path, cfg, monkeypatch):
    """The library is the user's own path and can be anywhere, including somewhere unwritable.
    A meeting is not thrown away over a bad setting."""
    sessions = make_sessions(tmp_path)
    real_mkdir = Path.mkdir

    def refuse(self: Path, *args, **kwargs):
        if self == cfg.library_dir() or cfg.library_dir() in self.parents:
            raise OSError("permissão negada")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", refuse)
    result = publish.publish_meeting(sessions, TEXT, 60.0, STARTED, cfg, "Orçamento")

    assert result.folder.parent == sessions
    assert result.transcript.exists()
    assert TEXT in result.transcript.read_text(encoding="utf-8")
    assert result.warnings


def test_the_fallback_folder_is_not_mistaken_for_a_session(tmp_path, cfg, monkeypatch):
    """It sits among the session files, so the listing has to tell a published meeting from a
    recording — otherwise the app offers to «recuperar» a meeting that was already saved."""
    from dito.core import library

    sessions = make_sessions(tmp_path)
    real_mkdir = Path.mkdir

    def refuse(self: Path, *args, **kwargs):
        if self == cfg.library_dir() or cfg.library_dir() in self.parents:
            raise OSError("permissão negada")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", refuse)
    publish.publish_meeting(sessions, TEXT, 60.0, STARTED, cfg, "Orçamento")

    assert library.list_sessions(sessions) == []


def test_subject_cannot_escape_the_library_folder(tmp_path, cfg):
    sessions = make_sessions(tmp_path)
    result = publish.publish_meeting(sessions, TEXT, 60.0, STARTED, cfg, "../../etc/passwd")

    assert cfg.library_dir() in result.folder.parents or result.folder.parent == cfg.library_dir()


def test_message_prefers_the_warning_over_the_happy_path():
    """Silence about a problem is what this whole project exists to prevent."""
    quiet = publish.Published(Path("/tmp"), Path("/tmp/t.md"), None, False, ())
    loud = publish.Published(Path("/tmp"), Path("/tmp/t.md"), None, False, ("deu ruim",))
    assert quiet.message == "meeting saved"
    assert loud.message == "deu ruim"
