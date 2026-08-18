"""Cuts a live recording into 20-45 s chunks at silence — see docs/armadilhas.md 3.5."""

from __future__ import annotations

from dataclasses import dataclass, field

# Room tone 0.0038 < this < speech 0.036 (docs/armadilhas.md 1.6); deliberately not the alarm's.
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
        """No pause in sight: cut at the quietest recent window, where a word breaks softest."""
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
