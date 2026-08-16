"""The pulsing status dot, painted and not styled — see docs/armadilhas.md 7.4."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

BOX = 14
MIN_D = 8.0
MAX_D = 12.0
PERIOD_S = 1.2


class StatusDot(QWidget):
    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._pulsing = False
        self._t0 = time.monotonic()
        self.setFixedSize(BOX, BOX)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def configure(self, color: str, pulsing: bool) -> None:
        changed = self._color.name() != QColor(color).name() or self._pulsing != pulsing
        self._color = QColor(color)
        if pulsing and not self._pulsing:
            self._t0 = time.monotonic()
        self._pulsing = pulsing
        if changed:
            self.update()

    def tick(self) -> None:
        if self._pulsing:
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        diameter = MIN_D
        if self._pulsing:
            phase = (time.monotonic() - self._t0) % PERIOD_S / PERIOD_S
            eased = 0.5 - 0.5 * math.cos(phase * 2 * math.pi)
            diameter = MIN_D + (MAX_D - MIN_D) * eased

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        # Float geometry in a fixed box: stays a circle at the fractional diameters of the pulse.
        offset = (BOX - diameter) / 2
        painter.drawEllipse(QRectF(offset, offset, diameter, diameter))
