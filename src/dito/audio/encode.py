"""WAV -> Opus, for meeting audio that is otherwise kept forever.

The numbers that decide this file, all measured here on 3 min of speech-shaped audio: recording is
16 kHz mono int16, which is 115 MB per hour — 345 MB for a three-hour meeting. The same three
hours of Opus at 24 kbps are 31 MB. That is an 11x reduction on the one file the user is asked to
keep indefinitely, and speech at that bitrate is still perfectly intelligible.

**PyAV, never the `ffmpeg` binary.** There is no ffmpeg on this machine (checked); PyAV already
comes in through faster-whisper, so the codec is right there in-process. Shelling out would add a
dependency the `.deb` does not install and would fail at the worst possible moment — right after
a three-hour meeting.

**The WAV is deleted only after the Opus has been decoded end to end.** Not "the file exists", not
"the header parses": every packet is decoded and the sample count is compared against the source.
Measured cost is 0.2 s per 3 min of audio — about 12 s for a three-hour meeting, on top of the
~97 s the encode itself takes. Cheap insurance, given that losing audio is the one thing this
project does not do.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

# bits/s. Measured on 3 min of speech-shaped audio: 23.1 kbps out, i.e. 31 MB for three hours
# against 345 MB of WAV.
BITRATE = 24_000

# Constrained VBR, not the default one. On speech the two are indistinguishable in size (23.1 kbps
# either way, measured), but plain VBR overshot the target by 43% — 34.3 kbps — on a tonal signal.
# Constrained keeps the "3 h fits in ~32 MB" promise true for whatever the microphone happens to
# pick up, and costs nothing when the content is what it is supposed to be.
ENCODER_OPTIONS = {"vbr": "constrained"}

# What ffmpeg's libopus encoder accepts. Recording is 16 kHz, which is on the list, so the usual
# path resamples nothing; anything else goes to 48 kHz, Opus's native rate.
OPUS_RATES = (8000, 12000, 16000, 24000, 48000)
FALLBACK_RATE = 48000

# Opus pads the last packet to a 20 ms frame and carries a pre-skip, so the encoded duration is
# never bit-exact. Measured drift: 13 ms over 60 s. Half a second is 30x that and still catches a
# truncated encode, which is what this tolerance is really for.
DURATION_TOLERANCE_S = 0.5

_WAV_HEADER = 44
_DATA_SIZE_OFFSET = 40


@dataclass(frozen=True)
class EncodeResult:
    # The Opus file when it worked, the untouched WAV when it did not.
    path: Path
    saved_bytes: int
    # Why the WAV was kept, in pt-BR and ready to show. `None` when the conversion worked.
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None


def to_opus(
    wav_path: Path | str, *, bitrate: int = BITRATE, keep_wav: bool = False
) -> EncodeResult:
    """Convert `audio.wav` to `audio.opus` beside it.

    On success the WAV is gone (unless `keep_wav`) and `saved_bytes` says how much came back. On
    any failure the WAV is exactly as it was and `reason` says what happened — there is no path
    through this function that removes audio it has not proved it can read back.
    """
    wav = Path(wav_path)
    if not wav.is_file():
        return EncodeResult(wav, 0, f"{wav.name} não existe")

    tail = _undeclared_tail(wav)
    if tail:
        # The RIFF sizes are patched on every flush precisely so the file is playable at any
        # instant (armadilhas 1.4). Bytes past the declared size mean the last patch never
        # happened, so a decoder — including the one below — would stop short of the end.
        # Compressing that would quietly trade the tail of a meeting for disk space.
        return EncodeResult(
            wav, 0, f"o WAV tem {tail} bytes de áudio além do que o cabeçalho declara"
        )

    opus = wav.with_suffix(".opus")
    # Written under a temporary name so an interrupted encode can never leave something that
    # looks like a finished `audio.opus`. The muxer comes from `format=`, not the extension.
    tmp = wav.with_name(wav.stem + ".opus.part")

    try:
        source_seconds = _encode(wav, tmp, bitrate)
        encoded_seconds = _decode_seconds(tmp)
    except Exception as exc:
        # Deliberately broad: PyAV raises its own error hierarchy plus OSError, and a codec that
        # is missing or a file that is malformed must both end the same way — WAV intact.
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
    """Returns the source duration measured from the samples actually decoded — the honest number
    to compare against, rather than whatever the container header claims."""
    # Imported here rather than at module load: PyAV drags in the ffmpeg shared libraries, and
    # compression only ever happens after a meeting ends.
    import av

    samples = 0
    with av.open(str(wav)) as src:
        istream = src.streams.audio[0]
        rate = istream.rate if istream.rate in OPUS_RATES else FALLBACK_RATE

        with av.open(str(target), "w", format="ogg") as dst:
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
        # The resampler carries the input timestamps forward; letting the encoder assign its own
        # keeps the two clocks from disagreeing when the rate changes.
        frame.pts = None
        for packet in ostream.encode(frame):
            dst.mux(packet)


def _decode_seconds(path: Path) -> float:
    """Decode the whole file and count samples. Reading the duration out of the header would pass
    on a file whose packets are corrupt, which is the case this check exists to catch."""
    import av

    samples = 0
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        for frame in container.decode(stream):
            samples += frame.samples
        return samples / stream.rate if stream.rate else 0.0


def _undeclared_tail(wav: Path) -> int:
    """Audio bytes present in the file but not counted by the RIFF `data` size.

    Only meaningful for the canonical 44-byte layout `audio/writer.py` produces; a WAV with extra
    chunks is not recognized here and reports 0, which is the right answer for a file this project
    did not write."""
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
