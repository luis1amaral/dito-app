"""WAV -> Opus via PyAV; the WAV goes only after a full decode — docs/armadilhas.md 1.10."""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

# bits/s; measured 23.1 kbps out on speech, i.e. 31 MB for three hours against 345 MB of WAV.
BITRATE = 24_000

# See docs/armadilhas.md 1.10: plain VBR overshot the target by 43% on a tonal signal.
ENCODER_OPTIONS = {"vbr": "constrained"}

# What libopus accepts: the 16 kHz recording is on the list, so the usual path resamples nothing.
OPUS_RATES = (8000, 12000, 16000, 24000, 48000)
FALLBACK_RATE = 48000

# 30x the measured 13 ms drift over 60 s, still tight enough to catch a truncated encode.
DURATION_TOLERANCE_S = 0.5

_WAV_HEADER = 44
_DATA_SIZE_OFFSET = 40


@dataclass(frozen=True)
class EncodeResult:
    # The Opus file when it worked, the untouched WAV when it did not.
    path: Path
    saved_bytes: int
    # Why the WAV was kept, in pt-BR ready to show; None when the conversion worked.
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None


def to_opus(
    wav_path: Path | str, *, bitrate: int = BITRATE, keep_wav: bool = False
) -> EncodeResult:
    """Convert `audio.wav` to `audio.opus` beside it; on any failure the WAV is left untouched."""
    wav = Path(wav_path)
    if not wav.is_file():
        return EncodeResult(wav, 0, f"{wav.name} não existe")

    tail = _undeclared_tail(wav)
    if tail:
        # See docs/armadilhas.md 1.4: bytes past the declared size mean the last patch never ran.
        return EncodeResult(
            wav, 0, f"o WAV tem {tail} bytes de áudio além do que o cabeçalho declara"
        )

    opus = wav.with_suffix(".opus")
    # Temporary name so an interrupted encode never leaves a plausible-looking `audio.opus`.
    tmp = wav.with_name(wav.stem + ".opus.part")

    try:
        source_seconds = _encode(wav, tmp, bitrate)
        encoded_seconds = _decode_seconds(tmp)
    except Exception as exc:
        # Broad on purpose: PyAV errors and OSError must all end the same way — WAV intact.
        tmp.unlink(missing_ok=True)
        return EncodeResult(wav, 0, f"a compressão falhou: {type(exc).__name__}: {exc}")

    drift = abs(encoded_seconds - source_seconds)
    if drift > DURATION_TOLERANCE_S:
        tmp.unlink(missing_ok=True)
        return EncodeResult(
            wav,
            0,
            f"o Opus ficou com {encoded_seconds:.1f}s contra {source_seconds:.1f}s do WAV",
        )

    wav_bytes = wav.stat().st_size
    os.replace(tmp, opus)

    if keep_wav:
        return EncodeResult(opus, 0)

    try:
        wav.unlink()
    except OSError as exc:
        return EncodeResult(opus, 0, f"o Opus foi gravado, mas o WAV continua aí: {exc}")

    return EncodeResult(opus, wav_bytes - opus.stat().st_size)


def _encode(wav: Path, target: Path, bitrate: int) -> float:
    """Returns the source duration from the samples decoded, not from what the header claims."""
    # Imported late: PyAV drags in the ffmpeg libraries, and this runs only after a meeting.
    import av

    samples = 0
    with av.open(str(wav)) as src:
        istream = src.streams.audio[0]
        rate = istream.rate if istream.rate in OPUS_RATES else FALLBACK_RATE

        with av.open(str(target), "w", format="ogg") as dst:   # .part needs an explicit muxer
            ostream = dst.add_stream("libopus", rate=rate, layout="mono",
                                     options=dict(ENCODER_OPTIONS))
            ostream.bit_rate = bitrate
            resampler = av.AudioResampler(
                format=ostream.format.name, layout=ostream.layout.name, rate=ostream.rate
            )

            for frame in src.decode(istream):
                samples += frame.samples
                _mux(dst, ostream, resampler.resample(frame))
            _mux(dst, ostream, resampler.resample(None))    # whatever the resampler still holds
            for packet in ostream.encode(None):             # and whatever the encoder still holds
                dst.mux(packet)

        return samples / istream.rate if istream.rate else 0.0


def _mux(dst, ostream, frames) -> None:
    for frame in frames:
        # Drop the resampler's carried-over pts: the encoder's own clock is the consistent one.
        frame.pts = None
        for packet in ostream.encode(frame):
            dst.mux(packet)


def _decode_seconds(path: Path) -> float:
    """Decode everything and count samples; the header would pass on a file with corrupt packets."""
    import av

    samples = 0
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        for frame in container.decode(stream):
            samples += frame.samples
        return samples / stream.rate if stream.rate else 0.0


def _undeclared_tail(wav: Path) -> int:
    """Audio bytes past the RIFF `data` size; 0 for any layout but the 44-byte one we write."""
    try:
        with wav.open("rb") as fh:
            head = fh.read(_WAV_HEADER)
        physical = wav.stat().st_size
    except OSError:
        return 0

    if len(head) < _WAV_HEADER or head[:4] != b"RIFF" or head[36:40] != b"data":
        return 0

    declared = struct.unpack_from("<I", head, _DATA_SIZE_OFFSET)[0]
    return max(0, physical - _WAV_HEADER - declared)
