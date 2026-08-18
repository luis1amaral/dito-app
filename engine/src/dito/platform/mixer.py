"""What a hardware capture control looks like, wherever it is read from."""

from __future__ import annotations

from dataclasses import dataclass

from ..i18n import _


@dataclass(frozen=True)
class Control:
    name: str
    pct: int
    on: bool


@dataclass(frozen=True)
class CaptureGain:
    card: int | None
    controls: tuple[Control, ...]

    @property
    def checked(self) -> bool:
        return bool(self.controls)

    @property
    def silent(self) -> bool:
        """Only when ALL controls are off or at zero — armadilhas 9.3: less cries wolf."""
        return self.checked and all((not c.on) or c.pct == 0 for c in self.controls)

    @property
    def reason(self) -> str | None:
        if not self.silent:
            return None
        off = [c for c in self.controls if not c.on]
        if off:
            return _("capture is switched OFF in the hardware (amixer «{control}»)").format(
                control=off[0].name
            )
        return _("the hardware capture gain is at 0%")

    @property
    def fix_command(self) -> str | None:
        if not self.silent or self.card is None or not self.controls:
            return None
        return f"amixer -c {self.card} sset {self.controls[0].name},0 100% cap"
