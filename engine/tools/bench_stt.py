"""Measures the real-time factor of the transcription engine on THIS machine.

RTF is the number that decides whether a meeting can be transcribed while it is being recorded.
Below ~0.8 there is room to keep up; above 1.0 the queue grows without bound and the transcript
finishes long after the meeting does.

    python tools/bench_stt.py                 # synthetic audio, encoder throughput
    python tools/bench_stt.py fala.wav        # a real recording, the honest number

With synthetic audio the VAD is turned off on purpose: it would skip the whole buffer as
non-speech and report an RTF near zero, which measures nothing. A real recording is always the
better measurement — this mode exists so the number can be taken with no sample at hand.
"""

from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dito.audio.devices import SAMPLE_RATE  # noqa: E402
from dito.stt.engine import WhisperEngine  # noqa: E402


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        if w.getframerate() != SAMPLE_RATE:
            raise SystemExit(f"esperado {SAMPLE_RATE} Hz, veio {w.getframerate()} Hz")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0


def synthetic(seconds: float) -> np.ndarray:
    """Band-limited noise shaped into syllable-length bursts: not speech, but it exercises the
    encoder over a realistic amount of signal instead of over silence."""
    rng = np.random.default_rng(7)
    n = int(seconds * SAMPLE_RATE)
    noise = rng.normal(0, 0.08, n).astype("float32")
    envelope = (np.sin(np.linspace(0, seconds * 2 * np.pi * 3, n)) > -0.3).astype("float32")
    return noise * envelope


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg:
        audio = load_wav(Path(arg))
        vad = True
        origem = arg
    else:
        audio = synthetic(60.0)
        vad = False
        origem = "sintético 60s (VAD desligado)"

    seconds = len(audio) / SAMPLE_RATE
    engine = WhisperEngine(model="small", language="pt", on_log=print)

    t0 = time.monotonic()
    engine.load()
    print(f"[carga] {time.monotonic() - t0:.2f}s  backend={engine.backend}")
    print(f"[áudio] {origem} — {seconds:.1f}s\n")

    for beam in (1, 5):
        t0 = time.monotonic()
        with engine._lock:
            model = engine.load()
            segs, _ = model.transcribe(
                audio, language="pt", vad_filter=vad, beam_size=beam,
                condition_on_previous_text=False,
            )
            texto = " ".join(s.text.strip() for s in segs)
        spent = time.monotonic() - t0
        rtf = spent / seconds
        veredito = "cabe em tempo real" if rtf < 0.8 else "NAO cabe em tempo real"
        print(f"  beam={beam}  {spent:6.2f}s  RTF={rtf:.2f}  {veredito}")
        if arg:
            print(f"           → {texto[:160]}")

    engine.unload()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
