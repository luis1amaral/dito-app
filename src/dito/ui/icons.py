"""Loading the app's icons, with a drawn fallback.

A missing asset must never take the app down. Dictation working without its icon is a cosmetic
problem; refusing to start because an SVG is absent is a real one — and the tray icon is also the
alarm's last line of defence, so it has to exist even when nothing else does.
"""

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


def _svg(name: str) -> Path:
    return ASSETS / f"{name}.svg"


@lru_cache(maxsize=16)
def app_icon() -> QIcon:
    path = _svg("icon")
    if path.exists():
        return QIcon(str(path))
    return _drawn(TrayState.IDLE, LIGHT, 256)


@lru_cache(maxsize=16)
def tray_icon(state: TrayState) -> QIcon:
    path = _svg(f"tray-{state.value}")
    if path.exists():
        return QIcon(str(path))
    return _drawn(state, LIGHT, Size.TRAY_ICON * 4)


def _drawn(state: TrayState, palette: Palette, size: int) -> QIcon:
    """The fallback. Three shapes, not three colours: a tray icon has to be readable at 22 px on
    a panel that may be light or dark, and colour alone survives neither."""
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
        painter.setBrush(QColor("#ffffff"))
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


def assets_present() -> bool:
    return _svg("icon").exists()
