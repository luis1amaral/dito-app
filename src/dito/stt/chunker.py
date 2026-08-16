"""Cuts a long recording into pieces that can be transcribed while it is still being recorded.

A meeting has no time limit here — it records until told to stop. Two consequences follow, and
this module exists for both:

  * **Memory has to stay flat.** The previous version accumulated every block in a list and
    concatenated at the end; a three-hour meeting would be gigabytes of float32 in RAM.
  * **The wait at the end has to disappear.** Measured on this machine, `small` on CPU int8 runs
    at RTF 0.35-0.45. Transcribing only after the meeting ends costs ~25 minutes for a one-hour
    meeting. Transcribing as it goes keeps up with 2.2x of headroom.

Where to cut matters. Whisper's encoder works on 30-second windows, so pieces in the 20-45s band
amortise it well. Cutting mid-word costs a word, so the cut lands in silence: preferably a real
pause, and when the ceiling is hit, at the quietest moment available rather than at an arbitrary
sample boundary.

Pure logic: blocks and peaks in, chunks out. No threads, no model, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Above room tone (measured 0.0038) and well below speech (0.036+): what counts as "not talking"
# for the purpose of finding a seam. Deliberately not the same constant as the alarm's threshold —
# these answer different questions and should be free to move apart.
SEAM_THRESHOLD = 0.01


@dataclass
class Chunk:
    audio: object            # float32 numpy array
    index: int
    start_s: float           # offset from the beginning of the recording
    end_s: float


@dataclass
class Chunker:
    sample_rate: int
    min_s: float = 20.0
    max_s: float = 45.0
    silence_ms: int = 600
    seam_threshold: float = SEAM_THRESHOLD
    tail_window_s: float = 5.0
    seam_width_s: float = 0.1

    _blocks: list = field(default_factory=list, init=False)
    _peaks: list[float] = field(default_factory=list, init=False)
    _emitted: int = field(default=0, init=False)
    _consumed_s: float = field(default=0.0, init=False)

    @property
    def pending_seconds(self) -> float:
        return sum(len(b) for b in self._blocks) / self.sample_rate

    def feed(self, block, peak: float) -> Chunk | None:
        """Add one captured block; return a closed chunk when it is time to cut."""
        self._blocks.append(block)
        self._peaks.append(peak)
        held = self.pending_seconds

        if held >= self.max_s:
            return self._cut(self._quietest_seam())
        if held >= self.min_s and self._trailing_silence_s() >= self.silence_ms / 1000:
            return self._cut(len(self._blocks))
        return None

    def flush(self) -> Chunk | None:
        """Close whatever is left. Called when the recording stops."""
        if not self._blocks:
            return None
        return self._cut(len(self._blocks))

    def _trailing_silence_s(self) -> float:
        quiet = 0
        for peak in reversed(self._peaks):
            if peak >= self.seam_threshold:
                break
            quiet += 1
        return quiet * self._block_s()

    def _block_s(self) -> float:
        return (len(self._blocks[0]) / self.sample_rate) if self._blocks else 0.0

    def _quietest_seam(self) -> int:
        """Ceiling reached with no pause in sight: cut at the quietest window in the recent tail
        instead of at an arbitrary boundary, so at worst a word breaks where it is softest."""
        block_s = self._block_s()
        if block_s <= 0:
            return len(self._blocks)
        width = max(1, int(self.seam_width_s / block_s))
        tail = max(width, int(self.tail_window_s / block_s))
        first = max(width, len(self._peaks) - tail)

        best_at = len(self._blocks)
        best_level = float("inf")
        for end in range(first, len(self._peaks) + 1):
            level = max(self._peaks[end - width:end])
            if level < best_level:
                best_level, best_at = level, end
        return best_at

    def _cut(self, upto: int):
        import numpy as np

        upto = max(1, min(upto, len(self._blocks)))
        head, self._blocks = self._blocks[:upto], self._blocks[upto:]
        self._peaks = self._peaks[upto:]

        audio = np.concatenate(head).astype("float32")
        duration = len(audio) / self.sample_rate
        chunk = Chunk(
            audio=audio,
            index=self._emitted,
            start_s=self._consumed_s,
            end_s=self._consumed_s + duration,
        )
        self._emitted += 1
        self._consumed_s += duration
        return chunk
