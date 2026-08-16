"""The floating pill shown while you speak. See docs/armadilhas.md 7.2 and 7.9."""

from __future__ import annotations

import math
import time
from enum import StrEnum

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .dot import StatusDot
from .spring import Spring, SpringDriver
from .surface import paint_floating_surface, shadow_margin
from .theme import Motion, Palette, Radius, Size, Space, Type
from .waveform import Waveform

ENTER_OFFSET = 24        # px below the resting spot; the spring covers this on the way in
SHAKE_PX = 7
MARGIN = Space.XXXL


class HudState(StrEnum):
    HIDDEN = "hidden"
    RECORDING = "recording"
    QUIET = "quiet"
    DEAD = "dead"
    WORKING = "working"
    TOAST = "toast"


def _clock(seconds: float) -> str:
    """mm:ss growing to h:mm:ss: a meeting has no time limit, so it must not wrap at 60 min."""
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


class Overlay(QWidget):
    fix_requested = Signal()
    stop_requested = Signal()

    def __init__(self, palette: Palette) -> None:
        super().__init__(None)
        self._palette = palette
        self._state = HudState.HIDDEN
        self._started_at = 0.0
        self._pulse_t0 = time.monotonic()
        self._shake_until = 0.0
        self._shake_phase = 0.0

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._build(palette)

        # One spring per axis: a single spring on a combined distance desynchronises the two.
        self._driver = SpringDriver(self)
        self._offset = self._driver.add(Spring(ENTER_OFFSET))
        self._alarm_grow = self._driver.add(
            Spring(0.0, response=Motion.MOMENTUM_RESPONSE, damping=Motion.MOMENTUM_DAMPING)
        )
        self._driver.frame.connect(self._reposition)

        self._ticker = QTimer(self)
        self._ticker.setInterval(50)
        self._ticker.timeout.connect(self._tick)

        self.hide()

    # ---- construction ----------------------------------------------------------------

    def _build(self, p: Palette) -> None:
        pad = shadow_margin()
        outer = QVBoxLayout(self)
        # Room for the hand-painted shadow (docs/armadilhas.md 7.1); clipped, it reads as an edge.
        outer.setContentsMargins(Space.LG + pad, Space.MD + pad, Space.LG + pad, Space.MD + pad)
        outer.setSpacing(Space.XS)

        row = QHBoxLayout()
        row.setSpacing(Space.MD)
        row.setContentsMargins(0, 0, 0, 0)

        self._dot = StatusDot(p.hud_recording)
        row.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._title = QLabel("Gravando")
        self._title.setStyleSheet(
            f"color: {p.hud_text}; font-size: {Type.BODY}px; font-weight: {Type.SEMIBOLD};"
        )
        row.addWidget(self._title, 0, Qt.AlignmentFlag.AlignVCenter)

        self._wave = Waveform(p)
        row.addWidget(self._wave, 0, Qt.AlignmentFlag.AlignVCenter)

        self._clock_label = QLabel("00:00")
        self._clock_label.setStyleSheet(
            f"color: {p.hud_muted}; font-family: {Type.MONO}; font-size: {Type.BODY}px;"
        )
        row.addWidget(self._clock_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._action = QPushButton("Corrigir")
        self._action.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action.setStyleSheet(
            f"QPushButton {{ background: rgba(255,255,255,0.16); color: {p.hud_text};"
            f" border: none; border-radius: {Radius.CONTROL}px; padding: {Space.XS}px"
            f" {Space.MD}px; font-weight: {Type.MEDIUM}; min-height: 0px; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.26); }}"
            f"QPushButton:pressed {{ background: rgba(255,255,255,0.34); }}"
        )
        self._action.clicked.connect(self.fix_requested.emit)
        self._action.hide()
        row.addWidget(self._action, 0, Qt.AlignmentFlag.AlignVCenter)

        outer.addLayout(row)

        self._detail = QLabel("")
        self._detail.setStyleSheet(
            f"color: {p.hud_muted}; font-size: {Type.CAPTION}px;"
        )
        self._detail.hide()
        outer.addWidget(self._detail)

        self.setFixedWidth(Size.HUD_W + 2 * shadow_margin())

    # ---- painting --------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        # hud_danger, never the theme's danger — see docs/armadilhas.md 7.3.
        if self._state is HudState.DEAD:
            fill = QColor(self._palette.hud_danger)
        else:
            fill = QColor(self._palette.hud_surface)
        # Near-opaque plus shadow: no reliable backdrop blur here, and fake frost reads as dirty.
        fill.setAlphaF(0.96)

        pad = shadow_margin()
        card = self.rect().adjusted(pad, pad, -pad, -pad).toRectF()
        border = QColor(self._palette.hud_alert) if self._state is HudState.QUIET else None
        paint_floating_surface(QPainter(self), card, Radius.OVERLAY, fill, border)

    # ---- placement and motion --------------------------------------------------------

    def _resting_geometry(self) -> tuple[int, int]:
        screen = self.screen() or self.window().screen()
        area = screen.availableGeometry()
        x = area.center().x() - self.width() // 2
        y = area.bottom() - self.height() - MARGIN
        return x, y

    def _reposition(self) -> None:
        x, y = self._resting_geometry()
        shake = 0.0
        if time.monotonic() < self._shake_until:
            # Decaying wobble: long enough for peripheral vision, short enough not to distract.
            remaining = self._shake_until - time.monotonic()
            shake = SHAKE_PX * remaining / (Motion.SHAKE_MS / 1000) * math.sin(self._shake_phase)
            self._shake_phase += 0.9
        self.move(int(x + shake), int(y + self._offset.value))

    def _tick(self) -> None:
        if self._state in (HudState.RECORDING, HudState.QUIET, HudState.DEAD):
            self._clock_label.setText(_clock(time.monotonic() - self._started_at))
        self._wave.tick()
        self._dot.tick()
        if time.monotonic() < self._shake_until:
            self._reposition()


    def _apply_colors(self, pulsing: bool = False) -> None:
        """Every colour of the pill, per state, in one place — see docs/armadilhas.md 7.3."""
        p = self._palette
        on_red = self._state is HudState.DEAD

        # Fixed white on the alarm, not `text_inverse`: that token flips and turns the dot black.
        dot = {
            HudState.RECORDING: p.hud_recording,
            HudState.QUIET: p.hud_alert,
            HudState.DEAD: p.hud_text,
            HudState.WORKING: p.hud_alert,
            HudState.TOAST: p.hud_ok,
        }.get(self._state, p.hud_muted)

        self._dot.configure(dot, pulsing)

        title_color = p.hud_text
        # White at reduced opacity on the red fill: the muted grey has no contrast there.
        detail_color = "rgba(255, 255, 255, 0.88)" if on_red else p.hud_muted
        clock_color = "rgba(255, 255, 255, 0.75)" if on_red else p.hud_muted

        self._title.setStyleSheet(
            f"color: {title_color}; font-size: {Type.BODY}px; font-weight: {Type.SEMIBOLD};"
        )
        self._detail.setStyleSheet(f"color: {detail_color}; font-size: {Type.CAPTION}px;")
        self._clock_label.setStyleSheet(
            f"color: {clock_color}; font-family: {Type.MONO}; font-size: {Type.BODY}px;"
        )

    # ---- public API ------------------------------------------------------------------

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._wave.set_palette(palette)
        self.update()

    def show_recording(self, meeting: bool = False) -> None:
        first = self._state is HudState.HIDDEN
        self._state = HudState.RECORDING
        self._title.setText("Reunião" if meeting else "Gravando")
        self._detail.hide()
        self._action.hide()
        self._wave.set_flat(False)
        self._wave.set_color(self._palette.hud_text)
        if first:
            self._started_at = time.monotonic()
            self._offset.jump_to(ENTER_OFFSET)
            self._appear()
        self._apply_colors(pulsing=True)
        self.update()

    def show_quiet(self, reason: str) -> None:
        self._state = HudState.QUIET
        self._title.setText("Áudio muito baixo")
        self._detail.setText(reason)
        self._detail.show()
        self._wave.set_color(self._palette.hud_alert)
        self._apply_colors()
        self._nudge()

    def show_dead(self, reason: str | None, fix_label: str | None = None) -> None:
        self._state = HudState.DEAD
        self._title.setText("SEM ÁUDIO")
        self._detail.setText(reason or "o microfone não está captando nada")
        self._detail.show()
        # Shape first: a flat line reads as "nothing is arriving" without relying on colour.
        self._wave.set_flat(True)
        self._wave.set_color(self._palette.text_inverse)
        self._action.setVisible(bool(fix_label))
        if fix_label:
            self._action.setText(fix_label)
        self._apply_colors()
        self._shake()
        self._nudge()

    def show_working(self, detail: str = "") -> None:
        self._state = HudState.WORKING
        self._title.setText("Transcrevendo…")
        self._wave.set_flat(False)
        self._action.hide()
        if detail:
            self._detail.setText(detail)
            self._detail.show()
        else:
            self._detail.hide()
        self._apply_colors()
        self._nudge()

    def show_toast(self, title: str, detail: str = "", ms: int = Motion.TOAST_MS) -> None:
        self._state = HudState.TOAST
        self._title.setText(title)
        self._clock_label.setText("")
        self._wave.hide()
        self._action.hide()
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        self._apply_colors()
        self._nudge()
        QTimer.singleShot(ms, lambda: self.dismiss() if self._state is HudState.TOAST else None)

    def push_level(self, rms: float) -> None:
        self._wave.push(rms)

    def dismiss(self) -> None:
        if self._state is HudState.HIDDEN:
            return
        self._state = HudState.HIDDEN
        # Leaves along the path it arrived by.
        self._offset.retarget(ENTER_OFFSET)
        self._driver.start()
        QTimer.singleShot(int(Motion.STANDARD_RESPONSE * 1000) + 60, self._finish_hide)

    def _finish_hide(self) -> None:
        if self._state is HudState.HIDDEN:
            self._ticker.stop()
            self.hide()
            self._wave.show()

    # ---- internals -------------------------------------------------------------------

    def _appear(self) -> None:
        self.adjustSize()
        self.setFixedWidth(Size.HUD_W + 2 * shadow_margin())
        self._reposition()
        self.show()
        self.raise_()
        self._offset.retarget(0.0)
        self._driver.start()
        self._ticker.start()

    def _nudge(self) -> None:
        """Re-measure and re-target instead of restarting: the pill grows from where it is."""
        if self._state is not HudState.HIDDEN and not self.isVisible():
            self._started_at = time.monotonic()
            self._offset.jump_to(ENTER_OFFSET)
            self._appear()
        self.adjustSize()
        self.setFixedWidth(Size.HUD_W + 2 * shadow_margin())
        self._offset.retarget(0.0)
        self._driver.start()
        self.update()

    def _shake(self) -> None:
        self._shake_until = time.monotonic() + Motion.SHAKE_MS / 1000
        self._shake_phase = 0.0
