"""The live waveform inside the recording pill.

This is not decoration. The bars ARE the "it is hearing you" signal — a static icon cannot say
that, and the whole reason this project was rewritten is that the old badge looked identical
whether audio was arriving or not. Flat bars must be immediately readable as "nothing is coming
in", which is why the flat state is drawn as a deliberate line rather than as bars of height zero
that could pass for a rendering glitch.

Each bar eases toward its target rather than jumping, because a bar that snaps reads as noise;
the eye follows continuous movement and ignores flicker.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from .theme import Palette, Space

BARS = 13
EASE = 0.45          # per frame: fast enough to feel live, slow enough not to strobe
BAR_W = 3
BAR_GAP = 3
MIN_H = 3


class Waveform(QWidget):
    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._targets = [0.0] * BARS
        self._values = [0.0] * BARS
        self._color = QColor(palette.hud_text)
        self._flat = False
        self.setFixedSize(BARS * (BAR_W + BAR_GAP) - BAR_GAP, Space.XXL)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def set_flat(self, flat: bool) -> None:
        """Flat is the alarm's shape: no signal, drawn as a line, not as tiny bars."""
        self._flat = flat
        if flat:
            self._targets = [0.0] * BARS
        self.update()

    def push(self, rms: float) -> None:
        """One new sample, scrolling right to left.

        The mapping is log-ish because speech RMS lives around 0.02-0.10 and a linear bar would
        barely leave the floor for normal talking."""
        level = min(1.0, math.sqrt(max(0.0, rms) * 18))
        self._targets = self._targets[1:] + [level]

    def tick(self) -> None:
        for i, target in enumerate(self._targets):
            self._values[i] += (target - self._values[i]) * EASE
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        height = self.height()
        mid = height / 2

        if self._flat:
            painter.setBrush(self._color)
            path = QPainterPath()
            path.addRoundedRect(
                QRectF(0, mid - 1, float(self.width()), 2.0), 1.0, 1.0
            )
            painter.drawPath(path)
            return

        painter.setBrush(self._color)
        for i, value in enumerate(self._values):
            bar_h = max(MIN_H, value * (height - 4))
            x = i * (BAR_W + BAR_GAP)
            rect = QRectF(x, mid - bar_h / 2, BAR_W, bar_h)
            path = QPainterPath()
            path.addRoundedRect(rect, BAR_W / 2, BAR_W / 2)
            painter.drawPath(path)
