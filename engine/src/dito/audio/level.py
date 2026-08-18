"""Input-level watchdog, the only detector of a dead mic — see docs/armadilhas.md 1.1 and 1.6."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

DEAD_THRESHOLD = 1e-4
QUIET_THRESHOLD = 8e-3


class State(StrEnum):
    OK = "ok"
    QUIET = "quiet"
    DEAD = "dead"


@dataclass(frozen=True)
class Reading:
    peak: float
    rms: float


class Watchdog:
    """Pure: `now` is passed in, so the alarm is testable without a microphone."""

    def __init__(
        self,
        dead_ms: int = 700,
        quiet_ms: int = 2500,
        grace_ms: int = 300,
        clear_ms: int = 200,
        dead_threshold: float = DEAD_THRESHOLD,
        quiet_threshold: float = QUIET_THRESHOLD,
    ) -> None:
        self.dead_s = dead_ms / 1000
        self.quiet_s = quiet_ms / 1000
        # PipeWire wakes a SUSPENDED source lazily, so the first blocks are legitimately silent.
        self.grace_s = grace_ms / 1000
        self.clear_s = clear_ms / 1000
        self.dead_threshold = dead_threshold
        self.quiet_threshold = quiet_threshold
        self.restart(0.0)

    def restart(self, now: float) -> None:
        self._t0 = now
        self._state = State.OK
        self._silent_since: float | None = None
        self._dead_since: float | None = None
        self._sound_since: float | None = None
        self._overflows = 0
        self._ever_heard = False

    @property
    def state(self) -> State:
        return self._state

    @property
    def choppy(self) -> bool:
        """Three dropped buffers is no longer bad luck; the stream is not keeping up."""
        return self._overflows >= 3

    @property
    def ever_heard(self) -> bool:
        """True once real audio arrived; a recording that ends False is the one worth retrying."""
        return self._ever_heard

    def record_overflow(self) -> None:
        self._overflows += 1

    def feed(self, peak: float, now: float) -> State:
        if now - self._t0 < self.grace_s:
            return self._state

        if peak >= self.quiet_threshold:
            self._silent_since = None
            self._dead_since = None
            if self._sound_since is None:
                self._sound_since = now
            # See docs/armadilhas.md 1.9: clearing needs sustained sound, transient must not latch.
            if now - self._sound_since >= self.clear_s:
                self._ever_heard = True
                self._state = State.OK
            return self._state

        self._sound_since = None
        if self._silent_since is None:
            self._silent_since = now
        if peak < self.dead_threshold:
            if self._dead_since is None:
                self._dead_since = now
        else:
            self._dead_since = None

        if self._dead_since is not None and now - self._dead_since >= self.dead_s:
            self._state = State.DEAD
        elif self._state is State.DEAD:
            # Signal is back but not yet usable: amber, not red — the device is alive again.
            self._state = State.QUIET
        elif not self._ever_heard and now - self._silent_since >= self.quiet_s:
            # See docs/armadilhas.md 1.6: gated on never having heard, or a pause reads as low gain.
            self._state = State.QUIET
        # Otherwise keep the current state: after real speech, silence is just a pause.
        return self._state


def measure(block) -> Reading:
    """peak and RMS of one block. `block` is a float32 numpy array in [-1, 1]."""
    import numpy as np

    if block is None or len(block) == 0:
        return Reading(0.0, 0.0)
    flat = block.reshape(-1)
    peak = float(np.abs(flat).max())
    rms = float(np.sqrt(np.mean(flat.astype("float64") ** 2)))
    return Reading(peak, rms)
