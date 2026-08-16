"""One recording, end to end, with the hardware faked so the failures can be forced.

Every test here was written against a defect an adversarial pass found by reproducing it. This
module had no tests at all, and it is where the product's central guarantee lives — so it is
exactly where the holes were:

  * a microphone that VANISHES delivers nothing, and the watchdog was only fed by arriving blocks,
    so the pill stayed green while nothing was recorded — the original 99-second failure again;
  * a non-OSError from the writer killed the audio thread outright, taking the alarm with it;
  * `stop()`'s `finally` could raise and destroy text that had already been transcribed;
  * back-pressure blocked the thread that writes the WAV, so a dead transcriber stopped the
    recording from reaching disk while the user kept talking.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from dito import config as cfgmod
from dito.audio.capture import Block
from dito.audio.level import Reading
from dito.audio.level import State as AudioState
from dito.core import events as ev
from dito.core import session as sessionmod
from dito.core.session import Mode, Session

RATE = 16000
BLOCK = 800


class FakeCapture:
    """A microphone we can starve, break or silence on demand."""

    def __init__(self, device=None, sample_rate=RATE, blocksize=BLOCK) -> None:
        self.blocks: queue.Queue = queue.Queue()
        self.error: str | None = None
        self.overflows = 0
        self.started = False
        self.stopped = False

    def start(self, on_error=None) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True
        self.blocks.put(None)

    # -- test helpers ------------------------------------------------------------------

    def deliver(self, peak: float, count: int = 1) -> None:
        for _ in range(count):
            audio = np.full(BLOCK, peak, dtype="float32")
            self.blocks.put(
                Block(audio=audio, reading=Reading(peak, peak), monotonic=time.monotonic())
            )
            time.sleep(0.005)


class FakeEngine:
    def __init__(self, text: str = "texto transcrito") -> None:
        self.text = text
        self.pinned = 0
        self.calls = 0

    def pin(self) -> None:
        self.pinned += 1

    def unpin(self) -> None:
        self.pinned -= 1

    def transcribe(self, audio, beam=5, language=None):
        self.calls += 1
        return SimpleNamespace(text=self.text, segments=(), seconds_of_audio=1.0, seconds_spent=0.1)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(sessionmod.paths, "sessions_dir", lambda: tmp_path / "sessions")
    # Preflight talks to pactl and the device list; the tests are about what happens after.
    monkeypatch.setattr(sessionmod, "preflight", lambda _d: sessionmod.Preflight(True))
    monkeypatch.setattr(sessionmod, "Capture", FakeCapture)
    c = cfgmod.Config()
    c.audio.alerts.dead_ms = 200
    c.audio.alerts.quiet_ms = 400
    return c


def make(cfg, mode=Mode.DICTATION, engine=None):
    events: list = []
    session = Session(
        cfg, mode, engine or FakeEngine(), emit=events.append, on_log=lambda _m: None
    )
    return session, events


def alarms(events) -> list[AudioState]:
    return [e.state for e in events if isinstance(e, ev.AudioAlarm)]


def wait_for(predicate, timeout=4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def talk_until_heard(session, timeout=4.0) -> bool:
    """Sustained speech, because `ever_heard` needs 200 ms of it — see armadilhas 1.9."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session._capture.deliver(0.06, count=10)
        if session._watchdog.ever_heard:
            return True
    return False


# ---------------------------------------------------------------------------------------


def test_a_microphone_that_vanishes_raises_the_alarm(cfg):
    """No blocks at all — PortAudio simply stops calling back, which is what happens when the
    PipeWire node drops out or the USB headset is unplugged. The watchdog used to be fed only by
    arriving blocks, so this case recorded nothing and said nothing."""
    session, events = make(cfg)
    assert session.start().ok
    try:
        assert wait_for(lambda: AudioState.DEAD in alarms(events)), (
            "microfone sumiu e nenhum alarme disparou"
        )
        reason = next(e.reason for e in events if isinstance(e, ev.AudioAlarm))
        assert "parou de responder" in reason
    finally:
        session.stop()


def test_a_microphone_delivering_silence_also_raises_the_alarm(cfg):
    session, events = make(cfg)
    assert session.start().ok
    try:
        session._capture.deliver(0.0, count=30)
        assert wait_for(lambda: AudioState.DEAD in alarms(events))
    finally:
        session.stop()


def test_real_audio_raises_nothing(cfg):
    session, events = make(cfg)
    assert session.start().ok
    try:
        for _ in range(10):
            session._capture.deliver(0.06, count=3)
        time.sleep(0.2)
        assert AudioState.DEAD not in alarms(events)
    finally:
        session.stop()


def test_a_writer_that_raises_does_not_kill_the_audio_thread(cfg):
    """A ValueError from a closed file used to end the consumer, and a dead consumer means no
    writing AND no alarm — silently, which is the one outcome this project does not allow."""
    session, events = make(cfg)
    assert session.start().ok
    try:
        session._writer.write = lambda _b: (_ for _ in ()).throw(ValueError("write to closed file"))
        session._capture.deliver(0.0, count=30)

        assert wait_for(lambda: AudioState.DEAD in alarms(events)), (
            "a thread de áudio morreu e levou o alarme junto"
        )
        assert any(isinstance(e, ev.Failed) for e in events), "a falha de disco não foi reportada"
    finally:
        session.stop()


def test_a_device_error_reaches_the_user(cfg):
    """`capture.error` was written by the audio callback and read by nobody."""
    session, events = make(cfg)
    assert session.start().ok
    try:
        session._capture.error = "PortAudio: input overflowed"
        session._capture.deliver(0.05, count=3)
        assert wait_for(
            lambda: any(
                isinstance(e, ev.AudioAlarm) and e.reason and "reportou um erro" in e.reason
                for e in events
            )
        )
    finally:
        session.stop()


def test_a_failure_closing_the_audio_does_not_destroy_the_transcription(cfg):
    """Closing flushes and fsyncs, which fails on a full disk. That exception came out of the
    `finally` and took with it text that had already been transcribed successfully — plus every
    event, leaving the pill stuck on "transcribing" forever."""
    session, events = make(cfg)
    assert session.start().ok
    session._capture.deliver(0.06, count=10)
    time.sleep(0.1)

    def explode() -> None:
        raise OSError(27, "File too large")

    session._writer.close = explode
    result = session.stop()

    assert isinstance(result, ev.Finished), "stop() não devolveu um resultado"
    assert result.text == "texto transcrito"
    assert any(isinstance(e, ev.Finished) for e in events)


def test_the_model_is_unpinned_even_when_closing_fails(cfg):
    """Skipping the unpin stranded ~500 MB and disabled the idle unload for the rest of the run."""
    engine = FakeEngine()
    session, _ = make(cfg, mode=Mode.MEETING, engine=engine)
    assert session.start().ok
    assert engine.pinned == 1

    session._writer.close = lambda: (_ for _ in ()).throw(OSError("disk full"))
    session.stop()
    assert engine.pinned == 0


def test_a_dead_transcriber_never_stops_the_recording(cfg):
    """The defect this replaces: back-pressure was applied by blocking inside the thread that
    writes the WAV, so with the transcriber gone the recording froze while the user kept talking.
    Measured at the time: the WAV stopped growing at 2s across the next 18s of speech."""
    session, _events = make(cfg, mode=Mode.MEETING)
    assert session.start().ok
    try:
        # Kill the transcriber and jam the queue, exactly as a crashed worker would leave it.
        session._stt_alive = False
        for _ in range(session._jobs.maxsize):
            session._jobs.put_nowait(object())

        before = session._writer.seconds
        for _ in range(30):
            session._capture.deliver(0.06, count=4)
        assert wait_for(lambda: session._writer.seconds > before + 1.0, timeout=6.0), (
            "o áudio parou de chegar no disco quando a transcrição travou"
        )
    finally:
        session._jobs.queue.clear()
        session.stop()


def test_submit_never_blocks_even_with_the_queue_jammed(cfg):
    """The defect in isolation. `_submit` ran on the thread that writes the WAV and called `put`
    with a 30 s timeout followed by an unbounded `put`; with the transcriber gone that thread
    stopped writing entirely. It must hand over or step aside — never wait."""
    session, _ = make(cfg, mode=Mode.MEETING)
    session._jobs = queue.Queue(maxsize=2)
    for _ in range(2):
        session._jobs.put_nowait(object())

    started = time.monotonic()
    for i in range(50):
        session._submit(SimpleNamespace(index=i, audio=np.zeros(8, dtype="float32"),
                                        start_s=0.0, end_s=1.0))
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, f"_submit bloqueou por {elapsed:.1f}s com a fila cheia"
    assert len(session._backlog) == 50, "os trechos precisam ir para o backlog, não sumir"


def test_backlogged_chunks_are_transcribed_at_the_end(cfg):
    """Late is acceptable. Lost is not."""
    engine = FakeEngine()
    session, _ = make(cfg, mode=Mode.MEETING, engine=engine)
    assert session.start().ok
    fake_chunk = SimpleNamespace(audio=np.zeros(RATE, dtype="float32"), index=0,
                                 start_s=0.0, end_s=1.0)
    session._backlog.append(fake_chunk)

    result = session.stop()
    assert isinstance(result, ev.Finished)
    assert engine.calls >= 1
    assert "texto transcrito" in result.text


def test_the_wav_is_readable_while_the_session_is_still_running(cfg):
    session, _ = make(cfg)
    assert session.start().ok
    try:
        session._capture.deliver(0.06, count=10)
        assert wait_for(lambda: session.wav_path.exists() and session.wav_path.stat().st_size > 44)
        time.sleep(0.1)
        with wave.open(str(session.wav_path)) as w:
            assert w.getnframes() > 0
    finally:
        session.stop()


def test_session_json_records_the_outcome(cfg):
    session, _ = make(cfg)
    assert session.start().ok
    session._capture.deliver(0.06, count=20)   # > 0.3s: abaixo disso é ignorado de propósito
    time.sleep(0.2)
    session.stop()

    meta = json.loads(session.meta_path.read_text(encoding="utf-8"))
    assert meta["state"] == "done"
    assert meta["mode"] == "dictation"
    assert meta["text"] == "texto transcrito"


def test_a_start_that_fails_reports_instead_of_raising(cfg, monkeypatch):
    """A raising start() left a ghost entry in the app's session map, after which the hotkey was
    dead for the rest of the process with nothing on screen."""
    class Refuses(FakeCapture):
        def start(self, on_error=None):
            from dito.audio.capture import CaptureError

            raise CaptureError("dispositivo ocupado")

    monkeypatch.setattr(sessionmod, "Capture", Refuses)
    session, events = make(cfg)
    result = session.start()

    assert not result.ok
    assert "indisponível" in (result.reason or "")
    assert any(isinstance(e, ev.Failed) for e in events)


# ---- one file per session, and the audio that goes with the text ------------------------


def test_a_session_is_one_file_beside_its_audio(cfg, tmp_path):
    """115 MB/h was the complaint; a folder per recording was the other half of the mess."""
    session, _ = make(cfg)
    assert session.start().ok
    try:
        root = tmp_path / "sessions"
        assert session.meta_path == root / f"{session.session_id}.json"
        assert session.wav_path == root / f"{session.session_id}.wav"
        assert session.meta_path.is_file() and session.wav_path.is_file()
        assert [p for p in root.iterdir() if p.is_dir()] == [], "criou pasta para a sessão"
    finally:
        session.stop()


def test_the_audio_goes_the_moment_the_dictation_is_transcribed(cfg):
    session, _ = make(cfg)
    assert session.start().ok
    assert talk_until_heard(session)

    result = session.stop()

    assert isinstance(result, ev.Finished) and result.text == "texto transcrito"
    assert not session.wav_path.exists(), "o WAV sobreviveu à transcrição"
    assert session.meta_path.is_file(), "o JSON da sessão nunca é apagado"


def test_the_audio_and_the_partials_go_when_the_meeting_is_transcribed(cfg):
    session, _ = make(cfg, mode=Mode.MEETING)
    assert session.start().ok
    assert talk_until_heard(session)
    session._submit(SimpleNamespace(index=0, audio=np.zeros(RATE, dtype="float32"),
                                    start_s=0.0, end_s=1.0))
    assert wait_for(lambda: session.transcript_path.is_file())

    result = session.stop()

    assert isinstance(result, ev.Finished) and result.text
    assert not session.wav_path.exists()
    assert not session.transcript_path.exists(), "os parciais ficaram duplicando o JSON"
    assert "texto transcrito" in json.loads(
        session.meta_path.read_text(encoding="utf-8")
    )["text"]


def test_the_partials_reach_disk_while_the_meeting_is_still_running(cfg):
    """Dying at minute 50 has to preserve 0-49. The jsonl is the only thing that guarantees it."""
    session, _ = make(cfg, mode=Mode.MEETING)
    assert session.start().ok
    try:
        session._submit(SimpleNamespace(index=0, audio=np.zeros(RATE, dtype="float32"),
                                        start_s=0.0, end_s=1.0))
        assert wait_for(lambda: session.transcript_path.is_file())
        assert "texto transcrito" in session.transcript_path.read_text(encoding="utf-8")
    finally:
        session.stop()


def test_the_audio_stays_when_the_transcription_fails(cfg):
    """The failed session is precisely the one whose audio the user will want back."""
    class Broken(FakeEngine):
        def transcribe(self, audio, beam=5, language=None):
            raise RuntimeError("o modelo não carregou")

    session, _ = make(cfg, engine=Broken())
    assert session.start().ok
    assert talk_until_heard(session)

    result = session.stop()

    assert isinstance(result, ev.Failed)
    assert session.wav_path.is_file(), "apagou o áudio da sessão que falhou"
    meta = json.loads(session.meta_path.read_text(encoding="utf-8"))
    assert meta["state"] == "transcribe_failed"


def test_the_audio_stays_when_nothing_was_captured(cfg):
    """armadilhas 1.1: the microphone delivered zeros and Whisper still produced a sentence. With
    no sound ever heard there is nothing to trust in that text, and the WAV is all the evidence."""
    session, _ = make(cfg)
    assert session.start().ok
    session._capture.deliver(0.0, count=30)
    time.sleep(0.1)

    result = session.stop()

    assert isinstance(result, ev.Finished) and not result.ever_heard_audio
    assert session.wav_path.is_file(), "apagou o áudio de uma gravação que não captou nada"


def test_the_audio_stays_when_the_text_could_not_be_written(cfg, monkeypatch):
    """CLAUDE.md, garantia 1: nothing deletes audio before reading back what replaces it."""
    session, _ = make(cfg)
    assert session.start().ok
    assert talk_until_heard(session)

    monkeypatch.setattr(
        type(session.meta_path), "replace",
        lambda _self, _target: (_ for _ in ()).throw(OSError("disco cheio")),
    )
    result = session.stop()

    assert isinstance(result, ev.Finished) and result.text == "texto transcrito"
    assert session.wav_path.is_file(), "o texto não chegou ao disco e o áudio foi apagado"


def test_consumer_thread_ends_when_the_session_stops(cfg):
    session, _ = make(cfg)
    assert session.start().ok
    session._capture.deliver(0.05, count=3)
    session.stop()
    assert wait_for(lambda: not session._consumer.is_alive(), timeout=3.0)
    assert threading.active_count() < 40
