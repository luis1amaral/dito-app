"""Painting a floating surface: the rounded card and the soft shadow under it.

Why the shadow is painted by hand instead of with `QGraphicsDropShadowEffect`: on a translucent
top-level window the effect makes Qt render the widget into an offscreen buffer, and the alpha
does not survive the trip — the window shows up as an opaque RECTANGLE behind the rounded card.

That is not a theory. Measured by grabbing the same screen region with the pill shown and hidden
and comparing pixels:

    bypassWM=True  shadow=True  -> corners changed 4/4   SQUARE
    bypassWM=False shadow=True  -> corners changed 4/4   SQUARE
    bypassWM=True  shadow=False -> corners changed 0/4   clean
    bypassWM=False shadow=False -> corners changed 0/4   clean

Stacked translucent rings cost a few draw calls and composite correctly, which is the right trade
for something that sits on top of everything the user is looking at.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

SHADOW_SPREAD = 14      # px of padding the window reserves around the card for the shadow
SHADOW_OFFSET = 5       # px downward: light comes from above
SHADOW_LAYERS = 9
SHADOW_ALPHA = 26       # per ring, at the densest one

NO_PEN = QPen(Qt.PenStyle.NoPen)


def shadow_margin() -> int:
    """Empty space the window has to keep around the card. Layouts add this to their own margins;
    without it the shadow is clipped and reads as a hard edge."""
    return SHADOW_SPREAD + SHADOW_OFFSET


def paint_floating_surface(
    painter: QPainter,
    rect: QRectF,
    radius: float,
    fill: QColor,
    border: QColor | None = None,
) -> None:
    """Shadow first, then the card, inside `rect`."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(NO_PEN)

    for i in range(SHADOW_LAYERS, 0, -1):
        spread = SHADOW_SPREAD * i / SHADOW_LAYERS
        # Quadratic falloff: a linear ramp reads as a stack of visible rings rather than a blur.
        alpha = int(SHADOW_ALPHA * (1 - i / SHADOW_LAYERS) ** 2) + 2
        ring = rect.adjusted(-spread, -spread + SHADOW_OFFSET, spread, spread + SHADOW_OFFSET)
        painter.setBrush(QColor(0, 0, 0, alpha))
        painter.drawRoundedRect(ring, radius + spread, radius + spread)

    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.fillPath(path, fill)

    if border is not None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border, 1))
        painter.drawPath(path)
        painter.setPen(NO_PEN)
