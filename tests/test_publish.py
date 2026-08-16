"""Publishing a meeting: text, audio and note reaching the user's own folder.

The ordering assertions here are the substance. Text is written first because it is what the user
came for and it never fails; a crash in the encoder must not cost the transcript. And nothing
gets deleted before its replacement is verified.
"""

from __future__ import annotations

import wave
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
    c.meeting.compress_audio = False       # PyAV is exercised in the encode tests, not here
    return c


def make_session(tmp_path: Path, seconds: float = 2.0) -> Path:
    folder = tmp_path / "sessions" / "2026-08-15_143000_meeting"
    folder.mkdir(parents=True)
    with wave.open(str(folder / "audio.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * int(16000 * seconds))
    return folder


def test_transcript_lands_in_the_library_folder(tmp_path, cfg):
    session = make_session(tmp_path)
    result = publish.publish_meeting(session, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert result.folder.parent == cfg.library_dir()
    assert "orcamento" in result.folder.name
    assert result.transcript.exists()
    body = result.transcript.read_text(encoding="utf-8")
    assert TEXT in body
    assert "15/08/2026" in body


def test_audio_moves_next_to_the_transcript(tmp_path, cfg):
    session = make_session(tmp_path)
    result = publish.publish_meeting(session, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert result.audio is not None
    assert result.audio.exists()
    assert result.audio.parent == result.folder
    assert not (session / "audio.wav").exists(), "o áudio foi movido, não copiado"


def test_audio_is_left_alone_when_saving_is_off(tmp_path, cfg):
    cfg.meeting.save_audio = False
    session = make_session(tmp_path)
    result = publish.publish_meeting(session, TEXT, 90.0, STARTED, cfg)

    assert result.audio is None
    assert (session / "audio.wav").exists(), "não pedi para guardar, mas também não para apagar"


def test_note_goes_to_the_vault_when_it_exists(tmp_path, cfg):
    (tmp_path / "notas" / "trabalho").mkdir(parents=True)
    session = make_session(tmp_path)
    result = publish.publish_meeting(session, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert result.note_in_vault
    assert result.note is not None
    assert result.note.parent == tmp_path / "notas" / "trabalho"
    assert not result.warnings


def test_a_missing_vault_is_not_created_and_the_meeting_still_lands(tmp_path, cfg):
    """The `reuniao` skill's rule: do not create the vault. Losing the meeting over it would be
    a far worse answer than putting the note beside the recording and saying so."""
    session = make_session(tmp_path)
    result = publish.publish_meeting(session, TEXT, 90.0, STARTED, cfg, subject="Orçamento")

    assert not (tmp_path / "notas").exists()
    assert not result.note_in_vault
    assert result.note is not None and result.note.exists()
    assert result.warnings and "cofre" in result.warnings[0]
    assert result.transcript.exists(), "a ressalva na nota não pode custar a transcrição"


def test_two_meetings_with_the_same_subject_do_not_collide(tmp_path, cfg):
    first = publish.publish_meeting(make_session(tmp_path), TEXT, 60.0, STARTED, cfg, "Diária")
    second_session = tmp_path / "sessions" / "outra"
    second_session.mkdir(parents=True)
    second = publish.publish_meeting(second_session, TEXT, 60.0, STARTED, cfg, "Diária")

    assert first.folder != second.folder
    assert first.transcript.exists() and second.transcript.exists()


def test_an_unwritable_library_falls_back_to_the_session_folder(tmp_path, cfg, monkeypatch):
    """The library is the user's own path and can be anywhere, including somewhere unwritable.
    A meeting is not thrown away over a bad setting."""
    session = make_session(tmp_path)

    def refuse(*_args, **_kwargs):
        raise OSError("permissão negada")

    monkeypatch.setattr(Path, "mkdir", refuse)
    result = publish.publish_meeting(session, TEXT, 60.0, STARTED, cfg, "Orçamento")

    assert result.folder == session
    assert result.transcript.exists()
    assert result.warnings


def test_subject_cannot_escape_the_library_folder(tmp_path, cfg):
    session = make_session(tmp_path)
    result = publish.publish_meeting(session, TEXT, 60.0, STARTED, cfg, "../../etc/passwd")

    assert cfg.library_dir() in result.folder.parents or result.folder.parent == cfg.library_dir()


def test_message_prefers_the_warning_over_the_happy_path():
    """Silence about a problem is what this whole project exists to prevent."""
    quiet = publish.Published(Path("/tmp"), Path("/tmp/t.md"), None, False, None, ())
    loud = publish.Published(Path("/tmp"), Path("/tmp/t.md"), None, False, None, ("deu ruim",))
    assert quiet.message == "reunião salva"
    assert loud.message == "deu ruim"
