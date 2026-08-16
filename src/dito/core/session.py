"""One recording, from key-down to text.

The shape of this file is dictated by one rule: **the audio must reach the disk before anything
can go wrong with it.** Capture feeds a consumer thread; the consumer's first act on every block
is to write it. Only then does it measure the level, and only then does it hand anything to the
transcriber. If the model fails to load, if the paste fails, if the process is killed — the WAV
is on disk, valid, and the session can be retried.

Dictation and meeting differ in exactly one way: a dictation is transcribed once at the end,
because it is short and accuracy matters more (beam 5); a meeting is cut into chunks and
transcribed as it goes, because it has no time limit and waiting until the end would cost about
25 minutes for a one-hour recording.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .. import paths
from ..audio import devices
from ..audio.capture import Capture, CaptureError
from ..audio.level import State as AudioState
from ..audio.level import Watchdog
from ..audio.writer import WavWriter
from ..platform.linux_x11 import alsa_mixer, audio_system
from ..stt.chunker import Chunker
from . import events as ev


class Mode(StrEnum):
    DICTATION = "dictation"
    MEETING = "meeting"


@dataclass
class Preflight:
    ok: bool
    reason: str | None = None
    fix_hint: str | None = None


def preflight(device_setting: str) -> Preflight:
    """Checked before opening the stream, so a known-bad microphone is reported instead of
    recorded. Kept under a few tens of milliseconds: this runs on the keypress path.

    Only refuses on certainty. "Don't know" always proceeds — the level watchdog covers the rest,
    and refusing to record for lack of information is worse than recording."""
    if devices.missing(device_setting):
        return Preflight(False, f"o microfone «{device_setting}» não está conectado")

    health = audio_system.health()
    if health.blocks_recording:
        return Preflight(False, health.reason, "desmutar")

    gain = alsa_mixer.capture_gain(alsa_mixer.card_of_source(health.name))
    if gain.silent:
        return Preflight(False, gain.reason, gain.fix_command)

    return Preflight(True)


class Session:
    def __init__(
        self,
        cfg,
        mode: Mode,
        engine,
        emit: Callable[[ev.Event], None],
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.mode = mode
        self.engine = engine
        self.emit = emit
        self._log = on_log or (lambda _m: None)

        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.session_id = f"{stamp}_{mode.value}"
        self.folder = paths.sessions_dir() / self.session_id
        self.wav_path = self.folder / "audio.wav"
        self.transcript_path = self.folder / "transcript.jsonl"
        self.meta_path = self.folder / "session.json"

        self._capture: Capture | None = None
        self._writer: WavWriter | None = None
        self._watchdog = Watchdog(
            dead_ms=cfg.audio.alerts.dead_ms, quiet_ms=cfg.audio.alerts.quiet_ms
        )
        self._chunker: Chunker | None = None
        self._consumer: threading.Thread | None = None
        self._stt_thread: threading.Thread | None = None
        self._jobs: queue.Queue = queue.Queue(maxsize=8)
        self._blocks: list = []          # dictation only: short, and also already on disk
        self._parts: list[tuple[int, str]] = []
        self._parts_lock = threading.Lock()
        self._stop = threading.Event()
        self._audio_state = AudioState.OK
        self._started_at = 0.0
        self._error: str | None = None
        self._stalled = False
        self._device_error: str | None = None
        self._overflows_seen = 0
        self._backlog: list = []          # chunks the transcriber could not take in time
        self._late = False
        self._stt_alive = False

    # ---- lifecycle -------------------------------------------------------------------

    def start(self) -> Preflight:
        check = preflight(self.cfg.audio.device)
        if not check.ok:
            self.emit(
                ev.AudioAlarm(state=AudioState.DEAD, reason=check.reason, fix_hint=check.fix_hint)
            )
            return check

        self.folder.mkdir(parents=True, exist_ok=True)
        self._write_meta("recording")

        device = devices.resolve(self.cfg.audio.device)
        self._capture = Capture(device=device, sample_rate=devices.SAMPLE_RATE)
        try:
            self._capture.start()
        except CaptureError as exc:
            self._error = str(exc)
            self._write_meta("failed")
            self.emit(ev.Failed(self.session_id, f"microfone indisponível: {exc}",
                                str(self.folder)))
            return Preflight(False, f"microfone indisponível: {exc}")

        self._writer = WavWriter(self.wav_path, devices.SAMPLE_RATE)
        self._started_at = time.monotonic()
        self._watchdog.restart(self._started_at)

        if self.mode is Mode.MEETING:
            self._chunker = Chunker(devices.SAMPLE_RATE)
            self.engine.pin()        # long silences must not trigger the idle unload
            self._stt_alive = True
            self._stt_thread = threading.Thread(
                target=self._stt_loop, daemon=True, name="dito-stt"
            )
            self._stt_thread.start()

        self._consumer = threading.Thread(target=self._consume, daemon=True, name="dito-audio")
        self._consumer.start()

        self.emit(ev.Started(self.session_id, self.mode.value,
                             devices.describe(self.cfg.audio.device)))
        self.emit(ev.PhaseChanged(ev.Phase.RECORDING))
        return Preflight(True)

    def stop(self) -> ev.Finished | ev.Failed:
        self._stop.set()
        if self._capture is not None:
            self._capture.stop()
        if self._consumer is not None:
            self._consumer.join(timeout=5.0)

        self.emit(ev.PhaseChanged(ev.Phase.TRANSCRIBING))
        try:
            text = self._finish_transcription()
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            self._write_meta("transcribe_failed")
            failed = ev.Failed(self.session_id, f"a transcrição falhou: {exc}", str(self.folder))
            self.emit(ev.PhaseChanged(ev.Phase.FAILED))
            self.emit(failed)
            return failed
        finally:
            # Neither of these may raise out of the finally. Closing the writer flushes and
            # fsyncs, which fails on a full disk — and that exception used to destroy text that
            # had ALREADY been transcribed successfully, emit no event at all (leaving the pill
            # stuck on "transcribing" forever) and skip the unpin, stranding ~500 MB of model.
            try:
                if self._writer is not None:
                    self._writer.close()
            except Exception as exc:
                self._log(f"[erro] não consegui fechar o áudio: {type(exc).__name__}: {exc}")
            try:
                if self.mode is Mode.MEETING:
                    self.engine.unpin()
            except Exception:
                pass

        seconds = self._writer.seconds if self._writer else 0.0
        self._write_meta("done", text=text, seconds=seconds)
        done = ev.Finished(
            session_id=self.session_id,
            mode=self.mode.value,
            text=text,
            seconds=seconds,
            folder=str(self.folder),
            ever_heard_audio=self._watchdog.ever_heard,
        )
        self.emit(done)
        return done

    # ---- audio consumer --------------------------------------------------------------

    # Short enough that a stalled device is noticed on the same schedule as a silent one. The old
    # 1.0s timeout was also the reason a vanished microphone went unreported: the loop simply
    # went round again and the watchdog was never fed.
    _POLL_S = 0.05

    def _consume(self) -> None:
        capture = self._capture
        writer = self._writer
        if capture is None or writer is None:
            return

        last_level = 0.0
        while True:
            try:
                block = capture.blocks.get(timeout=self._POLL_S)
            except queue.Empty:
                if self._stop.is_set():
                    break
                # A microphone that VANISHES delivers nothing at all — PortAudio simply stops
                # calling the callback. Feeding the watchdog zero here is what makes that case
                # alarm: from where the user sits, "arriving as silence" and "not arriving" are
                # the same fact. Without it the pill stayed green and the clock kept counting
                # while a dead headset recorded nothing, which is the original 99-second failure
                # through a second door (armadilhas 1.7: the PipeWire node dropping out).
                self._stalled = True
                self._tick_watchdog(0.0, time.monotonic())
                continue
            if block is None:
                break
            self._stalled = False

            # Disk first, always. Everything below can fail without costing the recording.
            # The except is deliberately broad: OSError alone let a ValueError from a closed file
            # kill this thread outright, and a dead audio thread means no writing AND no alarm —
            # silently, which is the one outcome this project does not allow.
            try:
                writer.write(block.audio)
            except Exception as exc:
                self._note_write_failure(exc)

            self._tick_watchdog(block.reading.peak, block.monotonic)

            now = block.monotonic
            if now - last_level >= 0.05:
                last_level = now
                self.emit(ev.Level(block.reading.peak, block.reading.rms, writer.seconds))

            if capture.error and not self._device_error:
                # capture.error used to be written and never read, so a PortAudio device error
                # went nowhere at all.
                self._device_error = capture.error
                self._log(f"[erro] dispositivo: {self._device_error}")
                self.emit(
                    ev.AudioAlarm(
                        state=AudioState.DEAD,
                        reason=f"o microfone reportou um erro: {self._device_error}",
                    )
                )
            if capture.overflows > self._overflows_seen:
                self._overflows_seen = capture.overflows
                self._watchdog.record_overflow()

            if self._chunker is not None:
                chunk = self._chunker.feed(block.audio, block.reading.peak)
                if chunk is not None:
                    self._submit(chunk)
            else:
                self._blocks.append(block.audio)

    def _tick_watchdog(self, peak: float, now: float) -> None:
        state = self._watchdog.feed(peak, now)
        if state is not self._audio_state:
            self._audio_state = state
            self.emit(ev.AudioAlarm(state=state, reason=self._alarm_reason(state)))

    def _note_write_failure(self, exc: Exception) -> None:
        """Reported once, loudly, and then the loop keeps going: the watchdog still has to run,
        because a disk that stopped accepting writes is exactly when knowing about the microphone
        matters most."""
        if self._error:
            return
        self._error = f"falha ao gravar em disco: {type(exc).__name__}: {exc}"
        self._log(f"[erro] {self._error}")
        self.emit(ev.Failed(self.session_id, self._error, str(self.folder)))

    def _alarm_reason(self, state: AudioState) -> str | None:
        if state is AudioState.DEAD:
            # The two causes need different wording: one is a live device delivering silence, the
            # other is a device that stopped delivering at all.
            if self._stalled:
                return "o microfone parou de responder — o dispositivo pode ter caído"
            return "o microfone não está captando nada"
        if state is AudioState.QUIET:
            return "o áudio está muito baixo"
        return None

    # ---- transcription ---------------------------------------------------------------

    def _submit(self, chunk) -> None:
        """Hand a chunk to the transcriber WITHOUT ever blocking the audio thread.

        The previous version claimed "the capture thread keeps writing to disk" and did the
        opposite: it called `put` with a timeout and then an unbounded `put` — from inside the
        consumer that writes the WAV. With the STT thread dead, the queue filled, the consumer
        blocked forever and **the recording stopped reaching the disk** while the user kept
        talking. Measured: the WAV froze at 2 s across the next 18 s of speech.

        A chunk that cannot be queued goes to a backlog in memory and is transcribed at the end.
        Text arrives late; audio never stops. That is the correct trade in that order.
        """
        try:
            self._jobs.put_nowait(chunk)
            return
        except queue.Full:
            pass
        self._backlog.append(chunk)
        if not self._late:
            self._late = True
            self._log("[aviso] transcrição atrasada — o áudio continua sendo gravado")

    def _stt_loop(self) -> None:
        """Wrapped whole. A transcription worker that dies takes the meeting's text with it, so
        it must not be possible for any single chunk — or any single failed disk append — to end
        the loop."""
        try:
            while True:
                chunk = self._jobs.get()
                if chunk is None:
                    return
                self._transcribe_chunk(chunk)
        except Exception as exc:
            self._log(f"[erro] a transcrição da reunião parou: {type(exc).__name__}: {exc}")
        finally:
            self._stt_alive = False

    def _transcribe_chunk(self, chunk) -> None:
        try:
            result = self.engine.transcribe(chunk.audio, beam=self.cfg.stt.beam_meeting)
        except Exception as exc:
            self._log(f"[erro] trecho {chunk.index}: {type(exc).__name__}: {exc}")
            return
        if not result.text:
            return
        with self._parts_lock:
            self._parts.append((chunk.index, result.text))
        try:
            self._append_transcript(chunk, result.text)
        except OSError as exc:
            # The text is already in `_parts`, so the meeting is not lost — only the incremental
            # copy on disk. Letting this escape used to kill the whole worker.
            self._log(f"[aviso] não consegui anexar ao transcript.jsonl: {exc}")
            self.emit(ev.Partial(chunk.index, chunk.start_s, chunk.end_s, result.text))

    def _append_transcript(self, chunk, text: str) -> None:
        """Appended as each chunk lands. Dying at minute 50 of a meeting still leaves 0-49 on
        disk, in order, readable."""
        line = json.dumps(
            {"index": chunk.index, "start": chunk.start_s, "end": chunk.end_s, "text": text},
            ensure_ascii=False,
        )
        with self.transcript_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _finish_transcription(self) -> str:
        if self.mode is Mode.MEETING:
            if self._chunker is not None:
                tail = self._chunker.flush()
                if tail is not None:
                    self._submit(tail)
            self._jobs.put(None)
            if self._stt_thread is not None:
                self._stt_thread.join(timeout=600.0)
            # Whatever could not be queued while recording is transcribed now, in order. It was
            # never lost — it just arrived late, which is the trade `_submit` makes on purpose.
            if self._backlog:
                self._log(f"[reunião] {len(self._backlog)} trecho(s) atrasado(s) — transcrevendo")
                for chunk in self._backlog:
                    self._transcribe_chunk(chunk)
                self._backlog.clear()
            with self._parts_lock:
                ordered = sorted(self._parts)
            return " ".join(text for _i, text in ordered).strip()

        if not self._blocks:
            return ""
        import numpy as np

        audio = np.concatenate(self._blocks).astype("float32")
        if len(audio) / devices.SAMPLE_RATE < 0.3:
            return ""
        result = self.engine.transcribe(audio, beam=self.cfg.stt.beam_dictation)
        return result.text

    # ---- persistence -----------------------------------------------------------------

    def _write_meta(self, state: str, text: str = "", seconds: float = 0.0) -> None:
        """`session.json` is what makes a crashed session recoverable: any folder whose state is
        not `done` is offered for retry on the next start."""
        data = {
            "id": self.session_id,
            "mode": self.mode.value,
            "state": state,
            "started": datetime.now().isoformat(timespec="seconds"),
            "seconds": round(seconds, 2),
            "device": self.cfg.audio.device or "default",
            "model": self.cfg.stt.model,
            "text": text,
            "error": self._error,
        }
        try:
            tmp = self.meta_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.meta_path)
        except OSError as exc:
            self._log(f"[aviso] não consegui gravar session.json: {exc}")
