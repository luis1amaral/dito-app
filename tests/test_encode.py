"""WAV → Opus, and the one rule that matters: audio is never deleted before its replacement is
proven readable.

Every test here asks the same question from a different angle — after this call, is the audio
still on disk somewhere? A compressor that saves 94% of the space and loses one meeting in fifty
is worthless for this app.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest

from dito.audio import encode

RATE = 16000


def write_wav(path: Path, seconds: float, tone: bool = True) -> Path:
    """Speech-shaped enough to be worth compressing. Pure silence encodes to almost nothing and
    would make the ratio assertions meaningless."""
    frames = int(seconds * RATE)
    samples = bytearray()
    for i in range(frames):
        value = 0.0
        if tone:
            envelope = 0.5 + 0.5 * math.sin(2 * math.pi * 3 * i / RATE)
            value = 0.4 * envelope * math.sin(2 * math.pi * 180 * i / RATE)
        samples += struct.pack("<h", int(value * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(samples))
    return path


def test_a_good_wav_becomes_a_much_smaller_opus(tmp_path):
    wav = write_wav(tmp_path / "audio.wav", 3.0)
    before = wav.stat().st_size

    result = encode.to_opus(wav)

    assert result.ok, result.reason
    assert result.path.suffix == ".opus"
    assert result.path.exists()
    assert result.path.stat().st_size < before / 4
    assert result.saved_bytes > 0
    assert not wav.exists(), "o WAV só some depois de o Opus ser verificado"


def test_keep_wav_leaves_both(tmp_path):
    wav = write_wav(tmp_path / "audio.wav", 2.0)
    result = encode.to_opus(wav, keep_wav=True)

    assert result.ok, result.reason
    assert wav.exists()
    assert result.path.exists()


def test_a_missing_file_is_reported_not_raised(tmp_path):
    """This runs at the end of a meeting. An exception here would take the publish step down with
    it, after the recording already happened."""
    result = encode.to_opus(tmp_path / "nao-existe.wav")
    assert not result.ok
    assert "não existe" in result.reason


def test_garbage_input_leaves_the_file_untouched(tmp_path):
    junk = tmp_path / "audio.wav"
    junk.write_bytes(b"isto nao e um wav" * 100)
    before = junk.read_bytes()

    result = encode.to_opus(junk)

    assert not result.ok
    assert junk.exists()
    assert junk.read_bytes() == before
    assert not (tmp_path / "audio.opus").exists()
    assert not (tmp_path / "audio.opus.part").exists(), "sobrou temporário"


def test_a_wav_with_an_undeclared_tail_is_refused(tmp_path):
    """The writer patches the RIFF sizes on every flush so the file is playable at any instant.
    Bytes past the declared size mean the last patch never happened — a decoder would stop short,
    and compressing that would trade the end of a meeting for disk space."""
    wav = write_wav(tmp_path / "audio.wav", 2.0)
    with wav.open("ab") as fh:
        fh.write(b"\x01\x02" * 8000)      # a second of audio the header does not know about

    result = encode.to_opus(wav)

    assert not result.ok
    assert "além do que o cabeçalho declara" in result.reason
    assert wav.exists()


def test_a_failed_verification_keeps_the_wav(tmp_path, monkeypatch):
    """The core guarantee, forced: if the decode-back says the Opus is the wrong length, the WAV
    stays and the Opus goes — never the other way around."""
    wav = write_wav(tmp_path / "audio.wav", 2.0)
    monkeypatch.setattr(encode, "_decode_seconds", lambda _p: 0.1)

    result = encode.to_opus(wav)

    assert not result.ok
    assert wav.exists()
    assert not (tmp_path / "audio.opus").exists()
    assert not (tmp_path / "audio.opus.part").exists()


def test_the_encoder_never_leaves_a_partial_file_behind(tmp_path, monkeypatch):
    wav = write_wav(tmp_path / "audio.wav", 2.0)

    def explode(*_args, **_kwargs):
        raise RuntimeError("codec sumiu no meio")

    monkeypatch.setattr(encode, "_encode", explode)
    result = encode.to_opus(wav)

    assert not result.ok
    assert wav.exists()
    assert list(tmp_path.glob("*.part")) == []


@pytest.mark.parametrize("seconds", [0.05, 1.0])
def test_very_short_recordings_do_not_crash(tmp_path, seconds):
    wav = write_wav(tmp_path / "audio.wav", seconds)
    result = encode.to_opus(wav)
    # Either outcome is acceptable for a fragment this small; losing the audio is not.
    assert result.ok or wav.exists()


def test_the_measured_bitrate_matches_the_promise(tmp_path):
    """The README promises 3 h ≈ 32 MB. That is 24 kbps, and a promise about disk usage should be
    checked rather than assumed."""
    seconds = 5.0
    wav = write_wav(tmp_path / "audio.wav", seconds)
    result = encode.to_opus(wav)
    assert result.ok, result.reason

    kbps = result.path.stat().st_size * 8 / seconds / 1000
    assert kbps < 40, f"{kbps:.1f} kbps — 3 h passariam de 54 MB"
