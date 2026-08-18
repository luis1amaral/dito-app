"""What the system knows about the mic. `None` is a real answer: nobody could tell."""

from __future__ import annotations

from dataclasses import dataclass

from ..i18n import _


@dataclass(frozen=True)
class SourceHealth:
    muted: bool | None
    volume: int | None
    name: str | None

    @property
    def blocks_recording(self) -> bool:
        """Only CERTAIN trouble blocks; `None` records anyway, since the watchdog covers it."""
        if self.muted is True:
            return True
        return self.volume is not None and self.volume < 5

    @property
    def reason(self) -> str | None:
        if self.muted is True:
            return _("the microphone is muted in the system")
        if self.volume is not None and self.volume < 5:
            return _("the input volume is at {pct}%").format(pct=self.volume)
        return None
