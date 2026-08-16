"""What a recording session tells the outside world.

Typed events rather than the old `("preview", str)` tuples: the previous version dispatched on a
string in a queue, and adding a case meant remembering to touch a chain of `elif`s in a function
far away. A dataclass per event makes the compiler-ish tooling do that job, and makes it obvious
what data each state carries.

Everything here crosses a thread boundary, so every event is frozen.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..audio.level import State as AudioState


class Phase(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class Started:
    session_id: str
    mode: str
    device: str


@dataclass(frozen=True)
class Level:
    """Emitted continuously while recording: feeds the waveform and the elapsed counter."""
    peak: float
    rms: float
    seconds: float


@dataclass(frozen=True)
class AudioAlarm:
    """The event this whole project exists for."""
    state: AudioState
    reason: str | None
    fix_hint: str | None = None

    @property
    def critical(self) -> bool:
        return self.state is AudioState.DEAD


@dataclass(frozen=True)
class Partial:
    """A chunk of a long recording, transcribed while the recording continues."""
    index: int
    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True)
class PhaseChanged:
    phase: Phase
    detail: str | None = None


@dataclass(frozen=True)
class Finished:
    session_id: str
    mode: str
    text: str
    seconds: float
    folder: str
    ever_heard_audio: bool


@dataclass(frozen=True)
class Published:
    """A meeting that reached the library: text written, audio compressed, note attempted."""
    folder: str
    note: str | None
    note_in_vault: bool
    minutes: int
    words: int
    warning: str | None = None


@dataclass(frozen=True)
class Failed:
    session_id: str
    reason: str
    folder: str | None = None
    recoverable: bool = True


Event = (
    Started | Level | AudioAlarm | Partial | PhaseChanged | Finished | Published | Failed
)
