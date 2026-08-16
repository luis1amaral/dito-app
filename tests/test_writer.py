"""The safety net itself: a WAV that is readable at every instant, including after kill -9.

This is the file the whole product rests on. If the recording on disk is not playable, every
other guarantee is decoration — and an adversarial pass found exactly that: sizes were patched
only on the fsync interval, so any recording shorter than five seconds still had RIFF=0/data=0
in its header. A dictation is typically two to five seconds. The common case was broken.

The `kill -9` tests spawn a real subprocess and SIGKILL it, because the failure only exists when
nothing gets a chance to run — an atexit hook, a `finally`, or a mocked close would all hide it.
"""

from __future__ import annotations

import struct
import subprocess
import sys
import textwrap
import wave
from pathlib import Path

import numpy as np
import pytest

from dito.audio.writer import WavWriter

RATE = 16000
BLOCK = 800          # 50 ms, same as capture


def tone(seconds: float) -> np.ndarray:
    n = int(seconds * RATE)
    return (0.3 * np.sin(np.linspace(0, seconds * 440 * 2 * np.pi, n))).astype("float32")


def read_header(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()[:44]
    riff = struct.unpack("<I", raw[4:8])[0]
    data = struct.unpack("<I", raw[40:44])[0]
    return riff, data


def test_the_file_is_readable_after_every_single_block(tmp_path):
    """Not 'eventually consistent': valid after block one, and after every block after that."""
    path = tmp_path / "audio.wav"
    writer = WavWriter(path, RATE)
    try:
        for i in range(1, 11):
            writer.write(tone(0.05))
            with wave.open(str(path)) as w:
                assert w.getnframes() == i * BLOCK, f"bloco {i}"
    finally:
        writer.close()


def test_a_short_recording_survives_kill_nine(tmp_path):
    """The reported failure. Four seconds of speech, process killed, and the file has to open.

    Runs in a real subprocess killed with SIGKILL: nothing in the process gets to finalise, which
    is the entire point."""
    path = tmp_path / "audio.wav"
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / "src")!r})
        import numpy as np
        from dito.audio.writer import WavWriter
        w = WavWriter({str(path)!r}, {RATE})
        block = np.zeros({BLOCK}, dtype="float32") + 0.1
        while True:
            w.write(block)
            time.sleep(0.01)
    """)
    proc = subprocess.Popen([sys.executable, "-c", script])
    try:
        deadline = 0.0
        while deadline < 3.0 and (not path.exists() or path.stat().st_size < 44 + BLOCK * 2 * 40):
            import time as _t

            _t.sleep(0.05)
            deadline += 0.05
    finally:
        proc.kill()
        proc.wait(timeout=5)

    assert path.exists()
    riff, data = read_header(path)
    assert data > 0, "cabeçalho declara zero bytes — nenhum player abre"

    with wave.open(str(path)) as w:
        frames = w.getnframes()
    on_disk = (path.stat().st_size - 44) // 2
    assert frames > 0
    # At most one block may be lost: the kill can land between the write and the patch.
    assert on_disk - frames <= BLOCK, f"{on_disk - frames} amostras no disco fora do cabeçalho"


def test_the_header_never_claims_more_than_exists(tmp_path):
    """Overstating is worse than understating: a decoder reading past the end gets noise."""
    path = tmp_path / "audio.wav"
    with WavWriter(path, RATE) as writer:
        for _ in range(7):
            writer.write(tone(0.05))
            riff, data = read_header(path)
            real = path.stat().st_size - 44
            assert data <= real
            assert riff == data + 36


def test_an_empty_block_changes_nothing(tmp_path):
    path = tmp_path / "audio.wav"
    with WavWriter(path, RATE) as writer:
        writer.write(tone(0.05))
        before = path.stat().st_size
        writer.write(np.zeros(0, dtype="float32"))
        writer.write(None)
        assert path.stat().st_size == before


def test_loud_samples_are_clipped_not_wrapped(tmp_path):
    """Without the clip, a sample above 1.0 wraps on the int16 cast and a loud moment becomes a
    burst of noise at the opposite polarity."""
    path = tmp_path / "audio.wav"
    with WavWriter(path, RATE) as writer:
        writer.write(np.array([2.0, -2.0, 0.5], dtype="float32"))

    with wave.open(str(path)) as w:
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    assert samples[0] == 32767
    assert samples[1] == -32767
    assert samples[2] > 0


def test_seconds_reports_what_is_actually_in_the_file(tmp_path):
    path = tmp_path / "audio.wav"
    with WavWriter(path, RATE) as writer:
        for _ in range(20):
            writer.write(tone(0.05))
        assert writer.seconds == pytest.approx(1.0, abs=0.01)
        with wave.open(str(path)) as w:
            assert w.getnframes() / RATE == pytest.approx(writer.seconds, abs=1e-6)


def test_close_is_idempotent(tmp_path):
    path = tmp_path / "audio.wav"
    writer = WavWriter(path, RATE)
    writer.write(tone(0.05))
    assert writer.close() == path
    assert writer.close() == path      # must not raise
