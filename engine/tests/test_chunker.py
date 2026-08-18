"""The chunker decides where a meeting gets sliced. Bad seams cost words, and unbounded holding
costs memory — a meeting has no time limit, so "it fits in RAM" is not something to assume."""

from __future__ import annotations

import numpy as np
import pytest

from dito.stt.chunker import Chunker

RATE = 16000
BLOCK = 800          # 50 ms, same as capture
SPEECH = 0.05
SILENCE = 0.001      # below the seam threshold, above digital zero


def block(peak: float):
    return np.full(BLOCK, peak, dtype="float32")


def push(ch: Chunker, peak: float, seconds: float) -> list:
    out = []
    for _ in range(int(seconds * RATE / BLOCK)):
        chunk = ch.feed(block(peak), peak)
        if chunk is not None:
            out.append(chunk)
    return out


def test_does_not_cut_before_the_minimum():
    ch = Chunker(RATE, min_s=20, max_s=45)
    assert push(ch, SPEECH, 10) == []
    assert push(ch, SILENCE, 5) == [], "a pause before min_s is not a seam"


def test_cuts_at_a_pause_once_past_the_minimum():
    ch = Chunker(RATE, min_s=20, max_s=45, silence_ms=600)
    push(ch, SPEECH, 21)
    cut = push(ch, SILENCE, 1.0)
    assert len(cut) == 1
    assert 21 <= cut[0].end_s <= 22.5


def test_ceiling_forces_a_cut_even_with_no_pause():
    """Continuous speech must not grow the buffer forever."""
    ch = Chunker(RATE, min_s=20, max_s=45)
    cuts = push(ch, SPEECH, 50)
    assert len(cuts) == 1
    assert cuts[0].end_s <= 45.1


def test_memory_stays_flat_over_a_long_meeting():
    """Three hours at 45s per chunk must never hold more than one chunk's worth of audio."""
    ch = Chunker(RATE, min_s=20, max_s=45)
    worst = 0.0
    for _ in range(int(3 * 3600 / 5)):
        push(ch, SPEECH, 5)
        worst = max(worst, ch.pending_seconds)
    assert worst <= 45.1, f"held {worst:.1f}s of audio at once"


def test_forced_cut_lands_on_the_quietest_moment():
    """When the ceiling hits with no real pause, the seam should still avoid the loudest audio."""
    ch = Chunker(RATE, min_s=20, max_s=45, tail_window_s=5.0, seam_width_s=0.1)
    push(ch, SPEECH, 41)
    push(ch, 0.02, 0.2)      # a dip 2 seconds before the ceiling
    cuts = push(ch, SPEECH, 4)
    assert len(cuts) == 1
    # The seam is inside the dip, not at the very end of the buffer.
    assert 41.0 <= cuts[0].end_s <= 41.5


def test_chunks_are_contiguous_and_numbered():
    ch = Chunker(RATE, min_s=5, max_s=10)
    cuts = push(ch, SPEECH, 32)
    assert [c.index for c in cuts] == list(range(len(cuts)))
    for earlier, later in zip(cuts, cuts[1:], strict=False):
        assert later.start_s == pytest.approx(earlier.end_s, abs=1e-6)


def test_flush_returns_the_tail_and_then_nothing():
    ch = Chunker(RATE, min_s=20, max_s=45)
    push(ch, SPEECH, 7)
    tail = ch.flush()
    assert tail is not None
    assert tail.end_s == pytest.approx(7.0, abs=0.1)
    assert ch.flush() is None


def test_no_audio_is_lost_across_the_cuts():
    """Every sample fed in comes back out exactly once — the point of the whole exercise."""
    ch = Chunker(RATE, min_s=5, max_s=10)
    fed = 0
    got = 0
    for _ in range(int(60 * RATE / BLOCK)):
        fed += BLOCK
        chunk = ch.feed(block(SPEECH), SPEECH)
        if chunk is not None:
            got += len(chunk.audio)
    tail = ch.flush()
    if tail is not None:
        got += len(tail.audio)
    assert got == fed
