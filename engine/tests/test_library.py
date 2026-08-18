"""The listing has to survive a session a crash left half-written, and it has to keep showing the
sessions recorded in the OLD folder layout — the owner has months of those on this machine.

Every test builds its sessions under `tmp_path` and passes that root explicitly. Nothing may read
or write the real `~/.local/share/dito` — the owner records real meetings on this machine.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from dito.core import library

NOW = datetime(2026, 8, 15, 18, 0, 0)


def make_session(
    root: Path,
    *,
    when: datetime = NOW,
    mode: str = "dictation",
    state: str = "done",
    text: str = "um ditado qualquer",
    seconds: float = 12.5,
    audio_bytes: int = 0,
    meta: bool = True,
) -> Path:
    """The current layout: one JSON file, and audio only while there is no text replacing it."""
    root.mkdir(parents=True, exist_ok=True)
    stem = f"{when:%Y-%m-%d_%H%M%S}_{mode}"

    if audio_bytes:
        (root / f"{stem}.wav").write_bytes(b"RIFF" + b"\0" * (audio_bytes - 4))
    if meta:
        (root / f"{stem}.json").write_text(
            json.dumps(
                {
                    "id": stem,
                    "mode": mode,
                    "state": state,
                    "started": when.isoformat(timespec="seconds"),
                    "seconds": seconds,
                    "text": text,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return root / f"{stem}.json"


def make_legacy_session(
    root: Path,
    *,
    when: datetime = NOW,
    mode: str = "dictation",
    state: str = "done",
    text: str = "gravado no formato antigo",
    seconds: float = 12.5,
    audio_bytes: int = 5_000,
    meta: bool = True,
) -> Path:
    """The folder layout used until 2026-08. Nothing writes it any more; everything reads it."""
    folder = root / f"{when:%Y-%m-%d_%H%M%S}_{mode}"
    folder.mkdir(parents=True)

    if audio_bytes:
        (folder / "audio.wav").write_bytes(b"RIFF" + b"\0" * (audio_bytes - 4))
    if meta:
        (folder / "session.json").write_text(
            json.dumps(
                {
                    "id": folder.name,
                    "mode": mode,
                    "state": state,
                    "started": when.isoformat(timespec="seconds"),
                    "seconds": seconds,
                    "text": text,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return folder


# ---- listing ------------------------------------------------------------------------------------


def test_lists_what_is_on_disk(tmp_path: Path):
    make_session(tmp_path, when=NOW - timedelta(hours=1))
    make_session(tmp_path, when=NOW - timedelta(hours=2), mode="meeting")

    sessions = library.list_sessions(tmp_path)

    assert [s.mode for s in sessions] == ["dictation", "meeting"], "não veio do mais novo primeiro"
    assert sessions[0].preview == "um ditado qualquer"
    assert sessions[0].seconds == 12.5


def test_a_session_is_one_file_and_never_a_folder(tmp_path: Path):
    """The whole point of the new layout: no subdirectory per recording."""
    path = make_session(tmp_path, audio_bytes=4_000)

    session = library.list_sessions(tmp_path)[0]

    assert session.path == path
    assert session.path.is_file()
    assert [p for p in tmp_path.iterdir() if p.is_dir()] == []


def test_an_old_folder_session_is_still_listed(tmp_path: Path):
    """Sessions recorded before the change stay on disk. Dropping them from the list is a loss."""
    make_session(tmp_path, when=NOW - timedelta(hours=1))
    folder = make_legacy_session(tmp_path, when=NOW - timedelta(hours=2), mode="meeting")

    sessions = library.list_sessions(tmp_path)

    assert len(sessions) == 2
    old = next(s for s in sessions if s.path == folder)
    assert old.mode == "meeting"
    assert old.preview == "gravado no formato antigo"
    assert old.has_audio, "o áudio antigo continua lá — nada aqui apaga pasta velha"
    assert old.size_bytes > 5_000


def test_a_corrupt_session_file_does_not_take_the_listing_down(tmp_path: Path):
    """The session with the broken metadata is the one the user came looking for. Raising on it
    would hide the other two as well."""
    make_session(tmp_path, when=NOW - timedelta(hours=1))
    broken = make_session(tmp_path, when=NOW - timedelta(hours=2), mode="meeting")
    broken.write_text("{isto não é json", encoding="utf-8")
    make_legacy_session(tmp_path, when=NOW - timedelta(hours=3), meta=False)

    sessions = library.list_sessions(tmp_path)

    assert len(sessions) == 3
    unknown = [s for s in sessions if s.state == library.UNKNOWN]
    assert len(unknown) == 2
    assert {s.mode for s in unknown} == {"meeting", "dictation"}, "o nome do arquivo dá o modo"
    assert all(s.started is not None for s in sessions), "o nome do arquivo dá a data"


def test_audio_without_metadata_is_still_a_session(tmp_path: Path):
    """A crash before the first write leaves only the WAV. Not listing it would hide the very
    thing the WAV exists to rescue."""
    make_session(tmp_path, meta=False, audio_bytes=9_000)

    sessions = library.list_sessions(tmp_path)

    assert len(sessions) == 1
    assert sessions[0].has_audio
    assert sessions[0].state == library.UNKNOWN
    assert sessions[0] in library.recoverable(tmp_path)


def test_a_folder_that_is_not_a_session_is_not_listed_as_one(tmp_path: Path):
    """A meeting whose library folder failed lands here; it is a published meeting, not a
    recording, and offering it for retry would be nonsense."""
    make_session(tmp_path)
    stray = tmp_path / "2026-08-15_1430-orcamento"
    stray.mkdir()
    (stray / "transcricao.md").write_text("# Reunião", encoding="utf-8")

    assert [s.id for s in library.list_sessions(tmp_path)] == ["2026-08-15_180000_dictation"]


def test_a_missing_root_is_an_empty_listing(tmp_path: Path):
    assert library.list_sessions(tmp_path / "nunca-existiu") == []


def test_duration_falls_back_to_the_size_of_the_wav(tmp_path: Path):
    """A session killed mid-recording has `seconds: 0` in its metadata. Showing 0:00 for forty
    minutes of audio would hide exactly what the user is trying to recover."""
    make_session(tmp_path, state="recording", seconds=0.0, text="",
                 audio_bytes=16_000 * 2 * 30 + 44)

    session = library.list_sessions(tmp_path)[0]
    assert session.seconds == pytest.approx(30.0, abs=0.01)


def test_a_crashed_meeting_previews_from_the_partials_beside_it(tmp_path: Path):
    """Dying at minute 50 keeps 0-49: the jsonl is written chunk by chunk, and it is what the
    listing reads when the final JSON never got its text."""
    path = make_session(tmp_path, mode="meeting", state="recording", text="")
    path.with_suffix(".jsonl").write_text(
        '{"index": 0, "start": 0.0, "end": 4.0, "text": "primeiro trecho"}\n'
        '{"index": 1, "start": 4.0, "end": 9.0, "text": "segundo trecho"}\n',
        encoding="utf-8",
    )

    assert library.list_sessions(tmp_path)[0].preview == "primeiro trecho segundo trecho"


def test_preview_is_short(tmp_path: Path):
    make_session(tmp_path, text="palavra " * 60)
    preview = library.list_sessions(tmp_path)[0].preview

    assert len(preview) <= library.PREVIEW_CHARS + 1
    assert preview.endswith("…")


# ---- audio --------------------------------------------------------------------------------------


def test_a_finished_session_has_no_audio_to_report(tmp_path: Path):
    """The audio goes the instant the transcription lands. `has_audio` is what the UI shows."""
    make_session(tmp_path, audio_bytes=0)

    assert library.list_sessions(tmp_path)[0].has_audio is False


def test_audio_kept_beside_the_json_is_reported(tmp_path: Path):
    make_session(tmp_path, state="transcribe_failed", text="", audio_bytes=7_000)

    session = library.list_sessions(tmp_path)[0]
    assert session.has_audio
    assert not session.done


# ---- recovery -----------------------------------------------------------------------------------


def test_recoverable_is_everything_that_did_not_finish(tmp_path: Path):
    make_session(tmp_path, when=NOW - timedelta(minutes=1), state="done")
    make_session(tmp_path, when=NOW - timedelta(minutes=2), state="recording")
    make_session(tmp_path, when=NOW - timedelta(minutes=3), state="transcribe_failed")
    make_session(tmp_path, when=NOW - timedelta(minutes=4), state="failed")
    make_legacy_session(tmp_path, when=NOW - timedelta(minutes=5), meta=False)

    states = {s.state for s in library.recoverable(tmp_path)}
    assert states == {"recording", "transcribe_failed", "failed", library.UNKNOWN}


# ---- disk ---------------------------------------------------------------------------------------


def test_total_size_sums_every_session(tmp_path: Path):
    make_session(tmp_path, when=NOW - timedelta(hours=1), audio_bytes=1_000)
    make_legacy_session(tmp_path, when=NOW - timedelta(hours=2), audio_bytes=2_000)

    assert library.total_size(tmp_path) >= 3_000
    assert library.total_size(tmp_path) == sum(
        s.size_bytes for s in library.list_sessions(tmp_path)
    )


def test_the_size_covers_the_files_that_share_the_name(tmp_path: Path):
    path = make_session(tmp_path, audio_bytes=6_000)
    path.with_suffix(".jsonl").write_text('{"index": 0, "text": "trecho"}\n', encoding="utf-8")

    assert library.list_sessions(tmp_path)[0].size_bytes > 6_000


def test_a_symlink_is_not_counted_twice(tmp_path: Path):
    """A linked file lives somewhere else; counting it here reports disk that deleting the session
    would not give back (armadilhas 6.3)."""
    folder = make_legacy_session(tmp_path, audio_bytes=4_000)
    (folder / "link.wav").symlink_to(folder / "audio.wav")

    only_real = library.list_sessions(tmp_path)[0].size_bytes
    assert only_real < 8_000


# ---- opening the folder --------------------------------------------------------------------------


def test_open_folder_never_raises_when_xdg_open_is_missing(tmp_path: Path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise FileNotFoundError("xdg-open")

    monkeypatch.setattr(library.subprocess, "Popen", boom)
    assert library.open_folder(tmp_path) is False


def test_open_folder_hands_the_path_to_xdg_open(tmp_path: Path, monkeypatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(library.subprocess, "Popen", lambda cmd, **_kw: seen.append(cmd))

    assert library.open_folder(tmp_path) is True
    assert seen == [["xdg-open", str(tmp_path)]]


def test_opening_a_session_file_opens_the_folder_that_holds_it(tmp_path: Path, monkeypatch):
    """`xdg-open` on a .json would launch a text editor, which is not what «Abrir pasta» means."""
    seen: list[list[str]] = []
    monkeypatch.setattr(library.subprocess, "Popen", lambda cmd, **_kw: seen.append(cmd))
    path = make_session(tmp_path)

    assert library.open_folder(path) is True
    assert seen == [["xdg-open", str(tmp_path)]]


def test_nothing_here_reads_the_real_sessions_dir(tmp_path: Path, monkeypatch):
    """The default root is the owner's own recordings. Every entry point must accept a root, and
    these tests must never fall back to it."""
    monkeypatch.setattr(library.paths, "sessions_dir", lambda: tmp_path / "vazio")

    assert library.list_sessions() == []
    assert library.recoverable() == []
    assert library.total_size() == 0


def test_folder_size_survives_an_unreadable_directory(tmp_path: Path):
    folder = make_legacy_session(tmp_path)
    locked = folder / "sem-permissao"
    locked.mkdir()
    os.chmod(locked, 0o000)
    try:
        assert library.list_sessions(tmp_path)[0].size_bytes > 0
    finally:
        os.chmod(locked, 0o755)


# ---- retenção: o disco não pode encher sozinho -------------------------------------------------


def _day(root, y, m, d, stems=("07-42-13",), text="oi"):
    folder = root / f"{y:04d}" / f"{m:02d}" / f"{d:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (folder / f"{stem}.json").write_text(
            json.dumps({"id": stem, "mode": "dictation", "state": "done", "text": text}),
            encoding="utf-8",
        )
        (folder / f"{stem}.wav").write_bytes(b"\0" * 1000)
    return folder


def test_sessions_past_the_horizon_are_swept(tmp_path):
    """Dictation adds up; without this the disk fills and nobody notices until it is full."""
    velha = _day(tmp_path, 2026, 6, 1)
    nova = _day(tmp_path, 2026, 8, 16)

    swept = library.sweep_older_than(tmp_path, 30, now=datetime(2026, 8, 16, 12, 0))

    assert swept.sessions == 1
    assert swept.bytes_freed >= 1000
    assert not velha.exists(), "a pasta do dia vazio ficou para trás"
    assert nova.is_dir() and list(nova.iterdir())


def test_the_sweep_only_removes_what_this_app_writes(tmp_path):
    """A folder in the library is the user's. Deleting a stranger's file there is not our call."""
    velha = _day(tmp_path, 2026, 6, 1)
    intruso = velha / "anotacoes-do-usuario.md"
    intruso.write_text("nao me apague", encoding="utf-8")

    library.sweep_older_than(tmp_path, 30, now=datetime(2026, 8, 16, 12, 0))

    assert intruso.is_file(), "apagou arquivo que não é nosso"
    assert not (velha / "07-42-13.json").exists()


def test_zero_days_keeps_everything(tmp_path):
    """`0` is the escape hatch, and it has to be the one that never deletes."""
    velha = _day(tmp_path, 2020, 1, 1)

    assert library.sweep_older_than(tmp_path, 0).sessions == 0
    assert (velha / "07-42-13.json").is_file()


def test_the_sweep_ignores_folders_that_are_not_dates(tmp_path):
    outra = tmp_path / "projeto-importante"
    outra.mkdir()
    (outra / "07-42-13.json").write_text("{}", encoding="utf-8")

    library.sweep_older_than(tmp_path, 1, now=datetime(2030, 1, 1))

    assert (outra / "07-42-13.json").is_file()
