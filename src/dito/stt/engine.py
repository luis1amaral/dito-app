"""Whisper running locally, nothing leaves the machine — see docs/armadilhas.md 3.1, 3.2 and 3.4."""

from __future__ import annotations

import gc
import sys
import threading
import time
from dataclasses import dataclass

from ..audio.devices import SAMPLE_RATE
from ..i18n import _


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcription:
    text: str
    segments: tuple[Segment, ...]
    seconds_of_audio: float
    seconds_spent: float

    @property
    def rtf(self) -> float:
        """Real-time factor: below 1.0 means transcription keeps up with the recording."""
        return self.seconds_spent / self.seconds_of_audio if self.seconds_of_audio else 0.0


def register_cuda_dlls(log=None) -> None:
    """Each platform adapter owns its fix (docs/armadilhas.md 3.3 and 3.8); engine.py stays flat."""
    if sys.platform == "win32":
        from ..platform.windows.cuda_dlls import register

        register()
        return

    from ..platform.linux_x11.cuda_libs import register

    loaded, failed = register()
    if log is not None:
        # Zero loaded is the silent-CPU case: without this line nobody can tell why.
        log(f"[cuda] {len(loaded)} biblioteca(s) carregada(s)"
            + (f", {len(failed)} falhou/falharam: {', '.join(failed)}" if failed else ""))


class WhisperEngine:
    def __init__(
        self,
        model: str = "small",
        language: str = "pt",
        device: str = "auto",
        idle_unload_min: float = 10.0,
        on_log=None,
    ) -> None:
        self.model_name = model
        self.language = language
        self.device_pref = device
        self.idle_unload_min = idle_unload_min
        self._log = on_log or (lambda _msg: None)

        self._model = None
        self._backend: str | None = None
        # faster-whisper is not safe to call concurrently — see docs/armadilhas.md 3.4.
        self._lock = threading.RLock()
        self._last_use = time.monotonic()
        self._pinned = 0

    @property
    def backend(self) -> str:
        """"cuda (float16)", "cpu (int8)", or the translated "not loaded" — doctor and settings."""
        # Stored as state, translated on read: the language changes without a restart.
        return self._backend or _("not loaded")

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def pinned(self) -> bool:
        """A meeting is holding the model: swapping it out costs the chunk being transcribed."""
        return self._pinned > 0

    def pin(self) -> None:
        """Hold the model in memory: unloading mid-meeting stalls the first chunk after a pause."""
        with self._lock:
            self._pinned += 1

    def unpin(self) -> None:
        with self._lock:
            self._pinned = max(0, self._pinned - 1)

    def load(self):
        with self._lock:
            if self._model is not None:
                self._last_use = time.monotonic()
                return self._model

            from faster_whisper import WhisperModel

            if self.device_pref in ("auto", "cuda"):
                register_cuda_dlls(self._log)
                try:
                    import numpy as np

                    model = WhisperModel(self.model_name, device="cuda", compute_type="float16")
                    # See docs/armadilhas.md 3.2: without this forced encode the fallback is dead.
                    list(
                        model.transcribe(
                            np.zeros(SAMPLE_RATE, dtype="float32"), language=self.language
                        )[0]
                    )
                    self._model = model
                    self._backend = "cuda (float16)"
                    self._log(f"[modelo] {self.model_name} na GPU (float16)")
                    self._last_use = time.monotonic()
                    return model
                except Exception as exc:
                    if self.device_pref == "cuda":
                        raise
                    self._log(f"[modelo] GPU indisponível ({type(exc).__name__}), usando CPU")

            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            self._backend = "cpu (int8)"
            self._log(f"[modelo] {self.model_name} na CPU (int8)")
            self._last_use = time.monotonic()
            return self._model

    def unload(self) -> None:
        with self._lock:
            if self._model is None:
                return
            self._model = None
            self._backend = None
            gc.collect()
            # Freeing is not returning. Measured: without this the RSS grew 378 -> 606 MB.
            if sys.platform != "win32":
                try:
                    import ctypes

                    ctypes.CDLL("libc.so.6").malloc_trim(0)
                except Exception:
                    pass
            self._log(f"[modelo] descarregado ({self.idle_unload_min:g} min ocioso)")

    def unload_if_idle(self, now: float | None = None) -> bool:
        """Called from the Qt thread every minute — see docs/armadilhas.md 3.7: never blocks."""
        now = now if now is not None else time.monotonic()
        if self._model is None or self._pinned or self.idle_unload_min <= 0:
            return False
        if now - self._last_use < self.idle_unload_min * 60:
            return False
        # Busy IS not idle, so give up rather than wait: a chunk holds the lock for 16-20 s.
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if self._model is None or self._pinned:
                return False
        finally:
            self._lock.release()
        self.unload()
        return True

    def transcribe(self, audio, beam: int = 5, language: str | None = None) -> Transcription:
        """float32 at 16 kHz; beam=1 is 2-3x faster on CPU, for provisional passes only."""
        seconds = len(audio) / SAMPLE_RATE if audio is not None else 0.0
        started = time.monotonic()
        with self._lock:
            model = self.load()
            raw, _info = model.transcribe(
                audio,
                language=language or self.language,
                vad_filter=True,
                beam_size=beam,
                # Independent chunks: shared context lets one bad decode poison all that follow.
                condition_on_previous_text=False,
            )
            segments = tuple(
                Segment(start=s.start, end=s.end, text=s.text.strip()) for s in raw
            )
            self._last_use = time.monotonic()

        return Transcription(
            text=" ".join(s.text for s in segments if s.text).strip(),
            segments=segments,
            seconds_of_audio=seconds,
            seconds_spent=time.monotonic() - started,
        )
