"""The meeting note has to come out in the exact shape the `reuniao` skill defines, and it has to
respect that skill's one hard rule: a vault that does not exist is not created.

Every test writes inside `tmp_path`. Nothing here may touch the real `~/notas` — the note the
owner takes to a client meeting is not test output.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from dito.config import Config
from dito.output.notes import MeetingNote, hms, slugify, subject_from, write_meeting_note

STARTED = datetime(2026, 8, 15, 14, 32, 0)
TRANSCRIPT = "Então a gente decidiu adiar o orçamento para a semana que vem."


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    folder = tmp_path / "notas"
    folder.mkdir()
    return folder


@pytest.fixture
def session(tmp_path: Path) -> Path:
    folder = tmp_path / "sessions" / "2026-08-15_143200_meeting"
    folder.mkdir(parents=True)
    (folder / "audio.wav").write_bytes(b"RIFF" + b"\0" * 4000)
    return folder


def make_cfg(vault_path: Path) -> Config:
    cfg = Config()
    cfg.meeting.obsidian.vault = str(vault_path)
    return cfg


def make_note(session: Path, **kwargs) -> MeetingNote:
    base = {
        "folder": session,
        "text": TRANSCRIPT,
        "seconds": 4353.0,
        "started": STARTED,
        "subject": "Orçamento do projeto X",
    }
    return MeetingNote(**{**base, **kwargs})


def section(body: str, title: str) -> str:
    """Everything between one `##` heading and the next."""
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    assert match, f"a seção «{title}» não existe na nota"
    return match.group(1)


# ---- where the note lands ---------------------------------------------------------------------


def test_note_lands_in_the_configured_vault_folder(vault: Path, session: Path):
    result = write_meeting_note(make_note(session), make_cfg(vault))

    assert result.in_vault
    assert result.reason is None
    assert result.path == vault / "trabalho" / "2026-08-15-orcamento-do-projeto-x.md"


def test_a_missing_vault_is_never_created(tmp_path: Path, session: Path):
    """The skill's hard rule: `~/notas` comes from its own bootstrap, and a folder invented here
    would be a second vault that never syncs."""
    absent = tmp_path / "notas"
    result = write_meeting_note(make_note(session), make_cfg(absent))

    assert not absent.exists(), "criou o cofre — é exatamente o que não pode"
    assert result.in_vault is False
    assert result.path.parent == session
    assert result.reason and str(absent) in result.reason


def test_the_note_is_never_lost_when_the_vault_is_missing(tmp_path: Path, session: Path):
    result = write_meeting_note(make_note(session), make_cfg(tmp_path / "notas"))
    assert TRANSCRIPT in result.path.read_text(encoding="utf-8")


def test_a_name_collision_never_overwrites(vault: Path, session: Path):
    first = write_meeting_note(make_note(session, text="primeira"), make_cfg(vault))
    second = write_meeting_note(make_note(session, text="segunda"), make_cfg(vault))
    third = write_meeting_note(make_note(session, text="terceira"), make_cfg(vault))

    assert second.path.name == "2026-08-15-orcamento-do-projeto-x-2.md"
    assert third.path.name == "2026-08-15-orcamento-do-projeto-x-3.md"
    assert "primeira" in first.path.read_text(encoding="utf-8")
    assert "segunda" in second.path.read_text(encoding="utf-8")


def test_the_subject_cannot_escape_the_folder(vault: Path, session: Path):
    result = write_meeting_note(make_note(session, subject="../../etc/passwd"), make_cfg(vault))
    assert result.path.parent == vault / "trabalho"
    assert result.path.name == "2026-08-15-etc-passwd.md"


# ---- the format ---------------------------------------------------------------------------------


def test_front_matter_matches_the_skill(vault: Path, session: Path):
    body = write_meeting_note(make_note(session), make_cfg(vault)).path.read_text(encoding="utf-8")
    head = body.split("---")[1]

    assert "data: 2026-08-15" in head
    assert "tipo: reuniao" in head
    assert "participantes: []" in head
    assert "tags: [dito]" in head
    assert "duracao: 01:12:33" in head


def test_participants_and_tags_reach_the_front_matter(vault: Path, session: Path):
    note = make_note(session, participants=("fulano", "ciclano"), tags=("projeto-x",))
    body = write_meeting_note(note, make_cfg(vault)).path.read_text(encoding="utf-8")
    head = body.split("---")[1]

    assert "participantes: [fulano, ciclano]" in head
    assert "tags: [dito, projeto-x]" in head


def test_the_skill_sections_are_all_present(vault: Path, session: Path):
    body = write_meeting_note(make_note(session), make_cfg(vault)).path.read_text(encoding="utf-8")

    assert body.count("# Reunião — Orçamento do projeto X") == 1
    for title in ("Decidido", "Pendências", "Discutido, sem decisão", "Ligações"):
        assert f"\n## {title}\n" in body


def test_the_decision_sections_come_out_empty(vault: Path, session: Path):
    """Dito heard the meeting; it was not in it. Inventing a decision in the affirmative is worse
    than leaving the section blank, because the two read identically six months later."""
    body = write_meeting_note(make_note(session), make_cfg(vault)).path.read_text(encoding="utf-8")

    for title in ("Decidido", "Pendências", "Discutido, sem decisão"):
        assert section(body, title).strip() == "", f"a seção «{title}» veio preenchida"


def test_the_raw_transcript_goes_inside_the_details(vault: Path, session: Path):
    body = write_meeting_note(make_note(session), make_cfg(vault)).path.read_text(encoding="utf-8")

    folded = body.split("<details>")[1].split("</details>")[0]
    assert TRANSCRIPT in folded
    assert body.index(TRANSCRIPT) > body.index("## Ligações"), "a transcrição vazou para o corpo"
    assert "<summary>" in folded


def test_an_empty_transcript_still_produces_a_valid_note(vault: Path, session: Path):
    body = write_meeting_note(make_note(session, text=""), make_cfg(vault)).path.read_text(
        encoding="utf-8"
    )
    assert "<details>" in body and "</details>" in body


def test_the_note_links_the_session_folder_as_a_file_uri(vault: Path, session: Path):
    body = write_meeting_note(make_note(session), make_cfg(vault)).path.read_text(encoding="utf-8")
    assert session.resolve().as_uri() in body


def test_links_become_wikilinks(vault: Path, session: Path):
    note = make_note(session, links=("projeto-x", "2026-08-01-kickoff"))
    body = write_meeting_note(note, make_cfg(vault)).path.read_text(encoding="utf-8")

    assert "[[projeto-x]]" in section(body, "Ligações")
    assert "[[2026-08-01-kickoff]]" in section(body, "Ligações")


# ---- audio ---------------------------------------------------------------------------------------


def test_audio_never_reaches_the_vault_by_default(vault: Path, session: Path):
    """The vault is a git repo with auto-commit: audio that lands there is committed before anyone
    notices, and getting tens of MB back out of a shared history is expensive."""
    write_meeting_note(make_note(session), make_cfg(vault))

    assert list((vault / "trabalho").glob("*.wav")) == []
    assert list((vault / "trabalho").glob("*.opus")) == []


def test_audio_is_copied_only_when_asked(vault: Path, session: Path):
    cfg = make_cfg(vault)
    cfg.meeting.obsidian.copy_audio = True

    result = write_meeting_note(make_note(session), cfg)
    copied = result.path.with_suffix(".wav")

    assert copied.is_file()
    assert f"![[{copied.name}]]" in result.path.read_text(encoding="utf-8")


# ---- helpers -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Reunião: Orçamento / 2026", "reuniao-orcamento-2026"),
        ("  espaços   demais  ", "espacos-demais"),
        ("Ação & Coração", "acao-coracao"),
        ("", "reuniao"),
        ("!!!", "reuniao"),
        ("日本語", "reuniao"),
    ],
)
def test_slugify(subject: str, expected: str):
    assert slugify(subject) == expected


def test_slug_stays_short_enough_for_a_filename():
    assert len(slugify("palavra " * 40)) <= 60


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00:00"), (59.9, "00:00:59"), (4353, "01:12:33"), (10800, "03:00:00")],
)
def test_hms(seconds: float, expected: str):
    assert hms(seconds) == expected


def test_the_subject_comes_from_the_first_sentence():
    """The note used to be named by a dialog at the end of an hour. Nobody answers that well, and
    «reuniao-0710» is a file nobody finds again in Obsidian. See docs/armadilhas.md 10.7."""
    assert subject_from(
        "Alinhamento do orçamento de agosto. Depois falamos do resto."
    ) == "Alinhamento do orçamento de agosto"


def test_a_subject_without_punctuation_is_cut_by_words():
    long_text = "primeira segunda terceira quarta quinta sexta setima oitava nona decima"
    assert subject_from(long_text) == "primeira segunda terceira quarta quinta sexta setima oitava"


def test_an_empty_transcript_gives_an_empty_subject():
    """The caller falls back to the clock; inventing a title for nothing would be a lie."""
    assert subject_from("") == ""
    assert subject_from("   \n  ") == ""


def test_the_subject_survives_slugify_for_the_filename():
    subject = subject_from("Reunião: orçamento de agosto. E o resto.")
    assert subject == "Reunião: orçamento de agosto"
    assert slugify(subject) == "reuniao-orcamento-de-agosto"
