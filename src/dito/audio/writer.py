"""Streaming WAV writer — the safety net that makes "I spoke and nothing was saved" impossible.

The previous version kept the whole recording in a Python list and only ever touched disk after
transcription succeeded. When transcription produced nothing, the audio went out of scope and
99 seconds of speech were gone. Here the file exists from the first block onward.

Why not the `wave` module: it only writes the RIFF/data sizes when you call `close()`. Kill the
process mid-recording and the header on disk still claims **zero frames**, so every player
refuses the file — the audio bytes are there and nothing can read them. That defeats the entire
point of writing early. So the 44-byte canonical header is written by hand and its two size
fields are patched on every flush, which keeps the file valid and playable at any instant,
including after `kill -9`.

int16 rather than float32: half the size (32 kB/s => 115 MB/h) and it is what every player and
editor opens without conversion. Whisper is fed from the in-memory float32 blocks anyway.
"""

from __future__ import annotations

import os
import struct
import time
from pathlib import Path

_HEADER_SIZE = 44
_RIFF_SIZE_OFFSET = 4
_DATA_SIZE_OFFSET = 40


def _header(sample_rate: int, channels: int, bits: int = 16) -> bytes:
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        0,                 # patched on every flush
        b"WAVE",
        b"fmt ",
        16,                # PCM fmt chunk size
        1,                 # PCM
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        0,                 # patched on every flush
    )


class WavWriter:
    def __init__(
        self,
        path: Path,
        sample_rate: int,
        channels: int = 1,
        fsync_every_s: float = 5.0,
    ) -> None:
        self.path = Path(path)
        self.sample_rate = sample_rate
        self.channels = channels
        self.fsync_every_s = fsync_every_s
        self._bytes = 0
        self._last_fsync = 0.0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("wb")
        self._fh.write(_header(sample_rate, channels))
        self._fh.flush()
        self._last_fsync = time.monotonic()

    @property
    def frames(self) -> int:
        return self._bytes // (2 * self.channels)

    @property
    def seconds(self) -> float:
        return self.frames / self.sample_rate if self.sample_rate else 0.0

    def write(self, block) -> None:
        """`block` is a float32 numpy array in [-1, 1]."""
        import numpy as np

        if block is None or len(block) == 0:
            return
        flat = np.asarray(block, dtype="float32").reshape(-1)
        # Clip before scaling: a sample above 1.0 wraps around on the int16 cast and turns a loud
        # moment into a burst of noise at the opposite polarity.
        pcm = (np.clip(flat, -1.0, 1.0) * 32767.0).astype("<i2")
        data = pcm.tobytes()
        self._fh.write(data)
        self._bytes += len(data)

        now = time.monotonic()
        if now - self._last_fsync >= self.fsync_every_s:
            self.flush(fsync=True)
            self._last_fsync = now

    def _patch_sizes(self) -> None:
        pos = self._fh.tell()
        self._fh.seek(_RIFF_SIZE_OFFSET)
        self._fh.write(struct.pack("<I", _HEADER_SIZE - 8 + self._bytes))
        self._fh.seek(_DATA_SIZE_OFFSET)
        self._fh.write(struct.pack("<I", self._bytes))
        self._fh.seek(pos)

    def flush(self, fsync: bool = False) -> None:
        if self._fh.closed:
            return
        self._patch_sizes()
        self._fh.flush()
        if fsync:
            os.fsync(self._fh.fileno())

    def close(self) -> Path:
        if not self._fh.closed:
            self.flush(fsync=True)
            self._fh.close()
        return self.path

    def __enter__(self) -> WavWriter:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
