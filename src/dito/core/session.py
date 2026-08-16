"""One recording, key-down to text: audio hits disk first and only goes once text replaced it."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from .. import paths
from ..audio import devices
from ..audio.capture import Capture, CaptureError
from ..audio.level import State as AudioState
from ..audio.level import Watchdog
from ..audio.writer import WavWriter
from ..i18n import _
from ..platform.linux_x11 import alsa_mixer, audio_system
from ..stt.chunker import Chunker
from . import events as ev


class Mode(StrEnum):
    # See docs/armadilhas.md 3.5: a meeting is chunked as it goes, a dictation waits for the end.
    DICTATION = "dictation"
    MEETING = "meeting"


@dataclass
class Preflight:
    ok: bool
    reason: str | None = None
    fix_hint: str | None = None


# Runs on the keypress path: every check added here must stay in the tens of milliseconds.
def preflight(device_setting: str) -> Preflight:
    """Refuses only on certainty — armadilhas 1.1: only the signal level knows a mic is dead."""
    if devices.missing(device_setting):
        return Preflight(
            False, _("the microphone «{device}» is not connected").format(device=device_setting)
        )

    # Only for a pinned device: probing the default costs 18 ms on every keypress, and buys nothing.
    pinned = (device_setting or "").strip()
    if pinned and not devices.supports_rate(devices.resolve(pinned)):
        return Preflight(
            False,
            _("the microphone «{device}» does not record at {rate} Hz").format(
                device=device_setting, rate=devices.SAMPLE_RATE
            ),
            _("choose «System default» under Settings › Audio"),
        )

    health = audio_system.health()
    if health.blocks_recording:
        return Preflight(False, health.reason, _("unmute"))

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
        # One file per session: `folder` is only the directory those files share.
        self.folder = paths.sessions_dir()
        self.wav_path = paths.session_audio(self.session_id)
        self.transcript_path = paths.session_partials(self.session_id)
        self.meta_path = paths.session_file(self.session_id)

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
            # Nothing was captured and the writer does not exist yet: this session has no content.
            self.meta_path.unlink(missing_ok=True)
            unavailable = _("microphone unavailable: {error}").format(error=exc)
            self.emit(ev.Failed(self.session_id, unavailable, str(self.folder)))
            return Preflight(False, unavailable)

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
            failed = ev.Failed(
                self.session_id,
                _("the transcription failed: {error}").format(error=exc),
                str(self.folder),
            )
            self.emit(ev.PhaseChanged(ev.Phase.FAILED))
            self.emit(failed)
            return failed
        finally:
            # See docs/armadilhas.md 9.2: neither of these may raise out of the finally.
            try:
                if self._writer is not None:
                    self._writer.close()
            except Exception as exc:
                self._log(f"[error] could not close the audio: {type(exc).__name__}: {exc}")
            try:
                if self.mode is Mode.MEETING:
                    self.engine.unpin()
            except Exception:
                pass

        seconds = self._writer.seconds if self._writer else 0.0
        if self._write_meta("done", text=text, seconds=seconds):
            self._discard_scratch(text)
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

    # See docs/armadilhas.md 1.11: the old 1 s timeout left a vanished microphone unreported.
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
                # See docs/armadilhas.md 1.11: nothing arriving must alarm like silence arriving.
                self._stalled = True
                self._tick_watchdog(0.0, time.monotonic())
                continue
            if block is None:
                break
            self._stalled = False

            # Disk first — and docs/armadilhas.md 9.1: this except stays broad on purpose.
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
                # A PortAudio device error was recorded here and never surfaced (armadilhas 1.5).
                self._device_error = capture.error
                self._log(f"[error] device: {self._device_error}")
                self.emit(
                    ev.AudioAlarm(
                        state=AudioState.DEAD,
                        reason=_("the microphone reported an error: {error}").format(
                            error=self._device_error
                        ),
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
        """Reported once, loudly; the loop goes on, because the watchdog still has to run."""
        if self._error:
            return
        self._error = _("writing to disk failed: {error}").format(
            error=f"{type(exc).__name__}: {exc}"
        )
        self._log(f"[error] {self._error}")
        self.emit(ev.Failed(self.session_id, self._error, str(self.folder)))

    def _alarm_reason(self, state: AudioState) -> str | None:
        if state is AudioState.DEAD:
            # A live device delivering silence and one that stopped delivering read differently.
            if self._stalled:
                return _("the microphone stopped responding — the device may have dropped")
            return _("the microphone is not picking anything up")
        if state is AudioState.QUIET:
            return _("the audio is too low")
        return None

    # ---- transcription ---------------------------------------------------------------

    def _submit(self, chunk) -> None:
        """Never blocks the audio thread (armadilhas 3.6): late text beats stopped audio."""
        try:
            self._jobs.put_nowait(chunk)
            return
        except queue.Full:
            pass
        self._backlog.append(chunk)
        if not self._late:
            self._late = True
            self._log("[warning] transcription is behind — the audio keeps being recorded")

    def _stt_loop(self) -> None:
        """Wrapped whole: one bad chunk must not end the loop and lose the meeting's text."""
        try:
            while True:
                chunk = self._jobs.get()
                if chunk is None:
                    return
                self._transcribe_chunk(chunk)
        except Exception as exc:
            self._log(f"[error] the meeting transcription stopped: {type(exc).__name__}: {exc}")
        finally:
            self._stt_alive = False

    def _transcribe_chunk(self, chunk) -> None:
        try:
            result = self.engine.transcribe(chunk.audio, beam=self.cfg.stt.beam_meeting)
        except Exception as exc:
            self._log(f"[error] chunk {chunk.index}: {type(exc).__name__}: {exc}")
            return
        if not result.text:
            return
        with self._parts_lock:
            self._parts.append((chunk.index, result.text))
        try:
            self._append_transcript(chunk, result.text)
        except OSError as exc:
            # The text is already in `_parts`; only the incremental copy on disk is lost here.
            self._log(f"[warning] could not append to transcript.jsonl: {exc}")
            self.emit(ev.Partial(chunk.index, chunk.start_s, chunk.end_s, result.text))

    def _append_transcript(self, chunk, text: str) -> None:
        """Appended per chunk: dying at minute 50 leaves 0-49 on disk, in order, readable."""
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
            # The backlog `_submit` deferred, in order: late, never lost (armadilhas 3.6).
            if self._backlog:
                self._log(f"[meeting] {len(self._backlog)} late chunk(s) — transcribing")
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

    def _write_meta(self, state: str, text: str = "", seconds: float = 0.0) -> bool:
        """Any session whose state is not `done` is offered for retry on the next start."""
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
            self._log(f"[warning] could not write {self.meta_path.name}: {exc}")
            return False
        return self._reads_back(text)

    def _reads_back(self, text: str) -> bool:
        """CLAUDE.md, garantia 1: nothing deletes audio before its replacement is read from disk."""
        try:
            saved = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(saved, dict) and saved.get("text") == text

    def _discard_scratch(self, text: str) -> None:
        """Audio only goes when text replaced it; no text means armadilhas 1.1, and it stays."""
        self._unlink(self.transcript_path)
        if text.strip() and self._watchdog.ever_heard:
            self._unlink(self.wav_path)

    def _unlink(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            self._log(f"[warning] could not delete {path.name}: {exc}")
