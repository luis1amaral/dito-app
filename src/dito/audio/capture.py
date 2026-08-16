"""Microphone capture: reports blocks and overflows, never judges — see docs/armadilhas.md 1.5."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass

from .devices import SAMPLE_RATE
from .level import Reading, measure

BLOCKSIZE = 800   # 50 ms at 16 kHz: fine enough for a 20 Hz watchdog, coarse enough to be cheap


@dataclass
class Block:
    audio: object          # float32 numpy array, shape (n,)
    reading: Reading
    monotonic: float


class CaptureError(RuntimeError):
    """Raised only by `start()`, for a device that is busy or gone — never from the audio thread."""


class Capture:
    def __init__(
        self,
        device: int | str | None = None,
        sample_rate: int = SAMPLE_RATE,
        blocksize: int = BLOCKSIZE,
    ) -> None:
        self.device = device
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.blocks: queue.Queue[Block | None] = queue.Queue()
        self._stream = None
        self._overflows = 0
        self._lock = threading.Lock()
        self._error: str | None = None

    @property
    def overflows(self) -> int:
        with self._lock:
            return self._overflows

    @property
    def error(self) -> str | None:
        """Polled by the owner: raising from the callback would kill the audio thread silently."""
        with self._lock:
            return self._error

    def start(self, on_error: Callable[[str], None] | None = None) -> None:
        import sounddevice as sd

        def callback(indata, frames, time_info, status):  # noqa: ARG001 - PortAudio signature
            # Realtime thread: slow work here drops blocks, and Windows tears the stream down.
            try:
                if status:
                    with self._lock:
                        if status.input_overflow:
                            self._overflows += 1
                        # input_underflow is playback's problem; anything else is a real error.
                        if getattr(status, "input_error", False):
                            self._error = str(status)
                            if on_error:
                                on_error(str(status))
                audio = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
                self.blocks.put(
                    Block(audio=audio, reading=measure(audio), monotonic=_now())
                )
            except Exception as exc:  # never let an exception escape the audio thread
                with self._lock:
                    self._error = f"{type(exc).__name__}: {exc}"

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self.blocksize,
                device=self.device,
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise CaptureError(str(exc)) from exc

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        # Sentinel so a consumer blocked on get() wakes up instead of hanging at shutdown.
        self.blocks.put(None)

    @property
    def running(self) -> bool:
        return self._stream is not None


def _now() -> float:
    import time

    return time.monotonic()
