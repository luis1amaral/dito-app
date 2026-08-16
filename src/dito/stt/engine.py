"""Whisper, running locally. Nothing leaves the machine.

Three behaviours here are not obvious and were paid for in debugging:

1. **The GPU fallback needs a forced encode.** Constructing `WhisperModel(device="cuda")` does not
   touch cuBLAS/cuDNN, so a missing library sails past the constructor and only explodes on the
   first real transcription — by which point the fallback path is long gone and the user just
   sees a crash. One second of zeros inside the `try` is what makes the fallback actually fire.

2. **The model is unloaded when idle, and glibc has to be told.** Freeing is not returning:
   without `malloc_trim(0)` the measured RSS *grew* from 378 MB to 606 MB after an unload,
   because the allocator keeps the arena.

3. **One thread at a time.** faster-whisper is not safe to call concurrently; a live preview and
   a final pass overlapping on the same model corrupts both. The lock is the whole protection.
"""

from __future__ import annotations

import gc
import sys
import threading
import time
from dataclasses import dataclass

from ..audio.devices import SAMPLE_RATE


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
        """Real-time factor. Below 1.0 means transcription keeps up with speech, which is what
        makes transcribing a meeting *while* it records possible instead of a 25-minute wait."""
        return self.seconds_spent / self.seconds_of_audio if self.seconds_of_audio else 0.0


def register_cuda_dlls() -> None:
    """Delegates to the Windows adapter, which owns the explanation and the fix. Kept as a name
    here so `engine.py` reads the same on both platforms."""
    from ..platform.windows.cuda_dlls import register

    register()


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
        self._backend = "não carregado"
        self._lock = threading.RLock()
        self._last_use = time.monotonic()
        self._pinned = 0

    @property
    def backend(self) -> str:
        """"cuda (float16)" / "cpu (int8)" / "não carregado" — shown in doctor and settings."""
        return self._backend

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def pin(self) -> None:
        """Hold the model in memory regardless of idle time. A meeting can have long silences;
        unloading mid-meeting would stall the first chunk after every pause."""
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
                register_cuda_dlls()
                try:
                    import numpy as np

                    model = WhisperModel(self.model_name, device="cuda", compute_type="float16")
                    # Forced encode: see the module docstring. Without it the fallback never runs.
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
            self._backend = "não carregado"
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
        now = now if now is not None else time.monotonic()
        with self._lock:
            if self._model is None or self._pinned or self.idle_unload_min <= 0:
                return False
            if now - self._last_use < self.idle_unload_min * 60:
                return False
        self.unload()
        return True

    def transcribe(self, audio, beam: int = 5, language: str | None = None) -> Transcription:
        """`audio` is a float32 numpy array at 16 kHz.

        beam=1 (greedy) exists for provisional passes: on CPU it is 2-3x faster than beam search,
        and a partial result can afford to be provisional. The final pass keeps beam=5.
        """
        seconds = len(audio) / SAMPLE_RATE if audio is not None else 0.0
        started = time.monotonic()
        with self._lock:
            model = self.load()
            raw, _info = model.transcribe(
                audio,
                language=language or self.language,
                vad_filter=True,
                beam_size=beam,
                # Each chunk is transcribed independently: carrying context across chunks lets one
                # bad decode poison every chunk after it, and the chunks are cut at silence anyway.
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
