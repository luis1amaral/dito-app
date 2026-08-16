"""The listing has to survive folders that a crash left half-written, and garbage collection has
to be the most conservative code in the project: it is the only thing here that deletes audio.

Every test builds its sessions under `tmp_path` and passes that root explicitly. Nothing may read
or write the real `~/.local/share/dito` — the owner records real meetings on this machine.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from dito.config import Config
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
    audio_bytes: int = 5_000,
    meta: bool = True,
) -> Path:
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


def cfg_with(*, dictation_hours: float = 48.0, meeting_days: float | None = None) -> Config:
    cfg = Config()
    cfg.retention.dictation_audio_hours = dictation_hours
    if meeting_days is not None:
        cfg.retention.meeting_audio_days = meeting_days
    return cfg


# ---- listing ------------------------------------------------------------------------------------


def test_lists_what_is_on_disk(tmp_path: Path):
    make_session(tmp_path, when=NOW - timedelta(hours=1))
    make_session(tmp_path, when=NOW - timedelta(hours=2), mode="meeting")

    sessions = library.list_sessions(tmp_path)

    assert [s.mode for s in sessions] == ["dictation", "meeting"], "não veio do mais novo primeiro"
    assert all(s.has_audio for s in sessions)
    assert all(s.size_bytes > 5_000 for s in sessions)
    assert sessions[0].preview == "um ditado qualquer"
    assert sessions[0].seconds == 12.5


def test_a_corrupt_session_json_does_not_take_the_listing_down(tmp_path: Path):
    """The folder with the broken metadata is the one the user came looking for. Raising on it
    would hide the other two as well."""
    make_session(tmp_path, when=NOW - timedelta(hours=1))
    broken = make_session(tmp_path, when=NOW - timedelta(hours=2), mode="meeting")
    (broken / "session.json").write_text("{isto não é json", encoding="utf-8")
    make_session(tmp_path, when=NOW - timedelta(hours=3), meta=False)

    sessions = library.list_sessions(tmp_path)

    assert len(sessions) == 3
    unknown = [s for s in sessions if s.state == library.UNKNOWN]
    assert len(unknown) == 2
    assert {s.mode for s in unknown} == {"meeting", "dictation"}, "o nome da pasta dá o modo"
    assert all(s.started is not None for s in sessions), "o nome da pasta dá a data"


def test_a_missing_root_is_an_empty_listing(tmp_path: Path):
    assert library.list_sessions(tmp_path / "nunca-existiu") == []


def test_duration_falls_back_to_the_size_of_the_wav(tmp_path: Path):
    """A session killed mid-recording has `seconds: 0` in its metadata. Showing 0:00 for forty
    minutes of audio would hide exactly what the user is trying to recover."""
    folder = make_session(tmp_path, state="recording", seconds=0.0, audio_bytes=0, text="")
    (folder / "audio.wav").write_bytes(b"RIFF" + b"\0" * (16_000 * 2 * 30 + 40))

    session = library.list_sessions(tmp_path)[0]
    assert session.seconds == pytest.approx(30.0, abs=0.01)


def test_a_crashed_meeting_previews_from_the_transcript(tmp_path: Path):
    folder = make_session(tmp_path, mode="meeting", state="recording", text="")
    (folder / "transcript.jsonl").write_text(
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


# ---- recovery -----------------------------------------------------------------------------------


def test_recoverable_is_everything_that_did_not_finish(tmp_path: Path):
    make_session(tmp_path, when=NOW - timedelta(minutes=1), state="done")
    make_session(tmp_path, when=NOW - timedelta(minutes=2), state="recording")
    make_session(tmp_path, when=NOW - timedelta(minutes=3), state="transcribe_failed")
    make_session(tmp_path, when=NOW - timedelta(minutes=4), state="failed")
    make_session(tmp_path, when=NOW - timedelta(minutes=5), meta=False)

    states = {s.state for s in library.recoverable(tmp_path)}
    assert states == {"recording", "transcribe_failed", "failed", library.UNKNOWN}


# ---- garbage collection --------------------------------------------------------------------------


def test_deletes_old_dictation_audio_and_reports_the_bytes(tmp_path: Path):
    old = make_session(tmp_path, when=NOW - timedelta(hours=72), audio_bytes=9_000)

    freed = library.collect_garbage(cfg_with(), tmp_path, now=NOW)

    assert freed == 9_000
    assert not (old / "audio.wav").exists()


def test_keeps_dictation_audio_inside_the_window(tmp_path: Path):
    recent = make_session(tmp_path, when=NOW - timedelta(hours=47))

    assert library.collect_garbage(cfg_with(), tmp_path, now=NOW) == 0
    assert (recent / "audio.wav").is_file()


def test_never_deletes_the_audio_of_a_session_that_failed(tmp_path: Path):
    """The failed session is precisely the one whose audio the user will want back."""
    kept = [
        make_session(tmp_path, when=NOW - timedelta(hours=72 + i), state=state)
        for i, state in enumerate(("failed", "transcribe_failed", "recording"))
    ]
    unknown = make_session(tmp_path, when=NOW - timedelta(days=30), meta=False)

    assert library.collect_garbage(cfg_with(), tmp_path, now=NOW) == 0
    assert all((folder / "audio.wav").is_file() for folder in [*kept, unknown])


def test_never_deletes_the_audio_of_a_session_that_recognized_nothing(tmp_path: Path):
    """`done` with no text is armadilhas 1.1: the microphone delivered zeros and the WAV is the
    only remaining evidence of what was said."""
    silent = make_session(tmp_path, when=NOW - timedelta(days=10), text="")

    assert library.collect_garbage(cfg_with(), tmp_path, now=NOW) == 0
    assert (silent / "audio.wav").is_file()


def test_meeting_audio_is_kept_forever_by_default(tmp_path: Path):
    old = make_session(tmp_path, when=NOW - timedelta(days=365), mode="meeting")

    assert Config().retention.meeting_audio_days == 0, "o padrão mudou — o teste abaixo mente"
    assert library.collect_garbage(Config(), tmp_path, now=NOW) == 0
    assert (old / "audio.wav").is_file()


def test_meeting_audio_goes_when_the_window_is_turned_on(tmp_path: Path):
    old = make_session(tmp_path, when=NOW - timedelta(days=40), mode="meeting")
    young = make_session(tmp_path, when=NOW - timedelta(days=20), mode="meeting")

    library.collect_garbage(cfg_with(meeting_days=30), tmp_path, now=NOW)

    assert not (old / "audio.wav").exists()
    assert (young / "audio.wav").is_file()


def test_zero_hours_means_keep_forever_for_dictation_too(tmp_path: Path):
    old = make_session(tmp_path, when=NOW - timedelta(days=365))

    assert library.collect_garbage(cfg_with(dictation_hours=0), tmp_path, now=NOW) == 0
    assert (old / "audio.wav").is_file()


def test_garbage_collection_never_touches_the_text(tmp_path: Path):
    """Audio is regenerable disk; the transcript is not. Only the audio may go."""
    old = make_session(tmp_path, when=NOW - timedelta(days=10), mode="meeting")
    (old / "transcript.jsonl").write_text('{"index": 0, "text": "o que foi dito"}\n', "utf-8")
    meta_before = (old / "session.json").read_text(encoding="utf-8")

    library.collect_garbage(cfg_with(meeting_days=1), tmp_path, now=NOW)

    assert not (old / "audio.wav").exists()
    assert (old / "session.json").read_text(encoding="utf-8") == meta_before
    assert "o que foi dito" in (old / "transcript.jsonl").read_text(encoding="utf-8")


def test_collects_the_compressed_audio_too(tmp_path: Path):
    old = make_session(tmp_path, when=NOW - timedelta(days=10), audio_bytes=0)
    (old / "audio.opus").write_bytes(b"\0" * 700)

    assert library.collect_garbage(cfg_with(), tmp_path, now=NOW) == 700
    assert not (old / "audio.opus").exists()


# ---- disk ---------------------------------------------------------------------------------------


def test_total_size_sums_every_session(tmp_path: Path):
    make_session(tmp_path, when=NOW - timedelta(hours=1), audio_bytes=1_000)
    make_session(tmp_path, when=NOW - timedelta(hours=2), audio_bytes=2_000)

    assert library.total_size(tmp_path) >= 3_000
    assert library.total_size(tmp_path) == sum(
        s.size_bytes for s in library.list_sessions(tmp_path)
    )


def test_a_symlink_is_not_counted_twice(tmp_path: Path):
    """A linked file lives somewhere else; counting it here reports disk that deleting the folder
    would not give back (armadilhas 6.3)."""
    folder = make_session(tmp_path, audio_bytes=4_000)
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


def test_nothing_here_reads_the_real_sessions_dir(tmp_path: Path, monkeypatch):
    """The default root is the owner's own recordings. Every entry point must accept a root, and
    these tests must never fall back to it."""
    monkeypatch.setattr(library.paths, "sessions_dir", lambda: tmp_path / "vazio")

    assert library.list_sessions() == []
    assert library.recoverable() == []
    assert library.total_size() == 0
    assert library.collect_garbage(Config()) == 0


def test_folder_size_survives_an_unreadable_directory(tmp_path: Path):
    folder = make_session(tmp_path)
    locked = folder / "sem-permissao"
    locked.mkdir()
    os.chmod(locked, 0o000)
    try:
        assert library.list_sessions(tmp_path)[0].size_bytes > 0
    finally:
        os.chmod(locked, 0o755)
