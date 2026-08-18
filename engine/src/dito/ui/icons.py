"""Loading the app's icons, with a drawn fallback: a missing asset never takes the app down."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap

from .theme import LIGHT, Palette, Size

ASSETS = Path(__file__).resolve().parent / "assets"


class TrayState(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    ALERT = "alert"


TRAY_PNG_SIZES = (22, 44)


def _svg(name: str) -> Path:
    return ASSETS / f"{name}.svg"


def _png(name: str) -> Path:
    return ASSETS / "png" / f"{name}.png"


def _loaded(path: Path) -> QIcon | None:
    """See docs/armadilhas.md 6.5: `exists()` is not `renders`; an SVG with no plugin loads null."""
    if not path.exists():
        return None
    icon = QIcon(str(path))
    return None if icon.isNull() else icon


def _tray_png(state: TrayState) -> QIcon | None:
    """Both sizes in one icon: the panel picks, instead of upscaling 22 into a blurry 44."""
    icon = QIcon()
    for size in TRAY_PNG_SIZES:
        pixmap = QPixmap(str(_png(f"tray-{state.value}-{size}")))
        if not pixmap.isNull():
            icon.addPixmap(pixmap)
    return None if icon.isNull() else icon


@lru_cache(maxsize=16)
def app_icon() -> QIcon:
    return (
        _loaded(_svg("icon"))
        or _loaded(_png("icon-256"))
        or _drawn(TrayState.IDLE, LIGHT, 256)
    )


@lru_cache(maxsize=16)
def tray_icon(state: TrayState) -> QIcon:
    return (
        _loaded(_svg(f"tray-{state.value}"))
        or _tray_png(state)
        or _drawn(state, LIGHT, Size.TRAY_ICON * 4)
    )


def _drawn(state: TrayState, palette: Palette, size: int) -> QIcon:
    """The fallback: three SHAPES, not three colours, to survive 22 px on any panel."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    unit = size / 24
    color = {
        TrayState.IDLE: QColor(palette.text_secondary),
        TrayState.RECORDING: QColor(palette.danger),
        TrayState.ALERT: QColor(palette.danger),
    }[state]

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)

    if state is TrayState.RECORDING:
        painter.drawEllipse(QRectF(6 * unit, 6 * unit, 12 * unit, 12 * unit))
    elif state is TrayState.ALERT:
        # A triangle, so it differs from the recording dot by SHAPE and not only by hue.
        path = QPainterPath()
        path.moveTo(12 * unit, 3 * unit)
        path.lineTo(22 * unit, 20 * unit)
        path.lineTo(2 * unit, 20 * unit)
        path.closeSubpath()
        painter.drawPath(path)
        # hud_text, not `text_inverse`: the mark sits on the red fill and must not flip (7.3).
        painter.setBrush(QColor(palette.hud_text))
        painter.drawRect(QRectF(11 * unit, 9 * unit, 2 * unit, 6 * unit))
        painter.drawRect(QRectF(11 * unit, 16 * unit, 2 * unit, 2 * unit))
    else:
        ring = QPainterPath()
        ring.addEllipse(QRectF(4 * unit, 4 * unit, 16 * unit, 16 * unit))
        ring.addEllipse(QRectF(7 * unit, 7 * unit, 10 * unit, 10 * unit))
        painter.drawPath(ring)

    painter.end()
    icon = QIcon(pixmap)
    icon.addPixmap(pixmap.scaled(QSize(Size.TRAY_ICON, Size.TRAY_ICON),
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation))
    return icon


