"""Input-level watchdog: the thing that says the microphone is not listening WHILE you speak.

Why it exists, precisely: PortAudio does not raise when capture dies. It keeps calling the
callback and hands over zeros. The previous version's log has the receipt —
`transcrevendo 99.2s... (pico=0.0000 rms=0.0000)` — 99 seconds of speech lost, with no exception
anywhere to catch. No amount of try/except detects this. Only the signal does.

Two distinct signals, because the causes differ and so does the right message:

  DEAD   exact digital silence (peak < 1e-4). Nothing is arriving: muted in hardware or driver,
         or the stream is attached to a dead node. This is the observed failure. Always armed —
         after real speech it means the device died mid-sentence, which is worth shouting about.
  QUIET  something arrives but far too softly (peak < 8e-3). Gain too low, or speaking far from
         the mic. Only armed until real audio is heard ONCE: after that, quiet is a pause between
         sentences, and warning about it would be a lie.

Both thresholds are measured, not guessed, on the machine this was built for:
  * speech peaks at 0.036-0.272 (from the previous version's logs)
  * the H510 headset's room-tone floor in a silent room is 0.0038 (measured with `dito selftest`)
8e-3 sits above that floor and 4.5x below the weakest speech; 1e-4 is reachable only by a stream
that is mathematically silent, which no live microphone ever is.

This class is pure: no threads, no I/O, no clock of its own. `now` is passed in. That is what
makes the alarm testable without a microphone (see tests/test_watchdog.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DEAD_THRESHOLD = 1e-4
QUIET_THRESHOLD = 8e-3


class State(str, Enum):
    OK = "ok"
    QUIET = "quiet"
    DEAD = "dead"


@dataclass(frozen=True)
class Reading:
    peak: float
    rms: float


class Watchdog:
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
        # Alarming during that window would cry wolf on every single recording.
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
        """True once real audio has arrived in this session. A recording that ends having never
        been True is the one worth offering to retry."""
        return self._ever_heard

    def record_overflow(self) -> None:
        self._overflows += 1

    def feed(self, peak: float, now: float) -> State:
        if now - self._t0 < self.grace_s:
            return self._state

        if peak >= self.quiet_threshold:
            self._ever_heard = True
            self._silent_since = None
            self._dead_since = None
            if self._sound_since is None:
                self._sound_since = now
            # Clearing takes sustained sound, so one loud click does not blink the alarm off and
            # straight back on.
            if now - self._sound_since >= self.clear_s:
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
            # Some signal is back, still too weak to call healthy: downgrade to amber rather
            # than stay red. The device is alive again; the level is not yet usable.
            self._state = State.QUIET
        elif not self._ever_heard and now - self._silent_since >= self.quiet_s:
            # Gated on never having heard anything. Without the gate, pausing between sentences
            # raises "audio too quiet" — measured, this machine's room tone is 0.0038, so every
            # silent gap longer than quiet_s would trip it. A pause is not a gain problem.
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
