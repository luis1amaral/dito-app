"""The floating pill: the only thing that appears on screen while you speak.

Hard constraint, and the reason for most of the flags below: **this window must never take
focus.** The transcribed text is pasted into whatever the user was typing in, so stealing focus
would paste Dito's own window. On X11 a `Qt.Tool` window with `WA_ShowWithoutActivating` and
`WindowDoesNotAcceptFocus` stays unfocusable; the review dialog, which does need the keyboard, is
a separate window that hands focus back.

The alarm state is the point of the whole product. It is deliberately loud in three independent
ways, because each can be missed on its own:
  * **shape** — the waveform collapses to a flat line, which reads even at a glance and even for
    someone who cannot distinguish the colours;
  * **colour** — the pill fills red rather than tinting an edge;
  * **movement** — a short shake, once, because motion catches peripheral vision that a colour
    change does not.
Sound and the system notification are fired by the app layer, not from here.

Entrance and exit follow the same path (up from below, back down), because something that
disappears in a different direction from the one it arrived by reads as two unrelated events.
"""

from __future__ import annotations

import math
import time
from enum import StrEnum

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .spring import Spring, SpringDriver
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
    """mm:ss, growing to h:mm:ss. A meeting has no time limit, so the field has to grow rather
    than wrap around at 60 minutes."""
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

        # Two independent springs: the vertical slide and the width change on alarm. One spring on
        # a combined distance desynchronises the moment the two have different velocities.
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(Space.LG, Space.MD, Space.LG, Space.MD)
        outer.setSpacing(Space.XS)

        row = QHBoxLayout()
        row.setSpacing(Space.MD)
        row.setContentsMargins(0, 0, 0, 0)

        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
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

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(shadow)

        self.setFixedWidth(Size.HUD_W)

    # ---- painting --------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # hud_danger, not the theme's danger: the pill has its own surface in both themes, and the
        # dark theme's danger is a light red that white text fails against (measured 2.77).
        if self._state is HudState.DEAD:
            fill = QColor(self._palette.hud_danger)
        else:
            fill = QColor(self._palette.hud_surface)
        # Not fully opaque: the pill floats over the user's work and should read as a layer above
        # it. Real backdrop blur is not reliably available on this compositor, so a near-opaque
        # surface plus a shadow is the honest version — a fake frosted look just reads as dirty.
        fill.setAlphaF(0.96)

        path = QPainterPath()
        path.addRoundedRect(self.rect().toRectF(), Radius.OVERLAY, Radius.OVERLAY)
        painter.fillPath(path, fill)

        if self._state is HudState.QUIET:
            painter.setPen(QColor(self._palette.hud_alert))
            painter.drawPath(path)

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
            # A short, decaying wobble. Long enough to catch the eye in peripheral vision, short
            # enough that it never becomes the thing you are looking at.
            remaining = self._shake_until - time.monotonic()
            shake = SHAKE_PX * remaining / (Motion.SHAKE_MS / 1000) * math.sin(self._shake_phase)
            self._shake_phase += 0.9
        self.move(int(x + shake), int(y + self._offset.value))

    def _tick(self) -> None:
        if self._state in (HudState.RECORDING, HudState.QUIET, HudState.DEAD):
            self._clock_label.setText(_clock(time.monotonic() - self._started_at))
        self._wave.tick()
        if time.monotonic() < self._shake_until:
            self._reposition()
        if self._state is HudState.RECORDING:
            self._apply_colors(pulsing=True)

    def _apply_colors(self, pulsing: bool = False) -> None:
        """Every colour in the pill is decided here, in one place, per state.

        It has to be one place because the pill's own background changes: in the alarm state the
        surface goes red, so the muted grey that reads correctly on the dark surface becomes
        unreadable, and a red status dot becomes invisible against it. Scattering these choices
        across the show_* methods is exactly how that bug got in.
        """
        p = self._palette
        on_red = self._state is HudState.DEAD

        # On the alarm the foreground is fixed white, not `text_inverse`: that token flips with
        # the theme, so in dark mode the dot came out near-black on the red fill.
        dot = {
            HudState.RECORDING: p.hud_recording,
            HudState.QUIET: p.hud_alert,
            HudState.DEAD: p.hud_text,
            HudState.WORKING: p.hud_alert,
            HudState.TOAST: p.hud_ok,
        }.get(self._state, p.hud_muted)

        size = 10
        if pulsing:
            phase = (time.monotonic() - self._pulse_t0) % 1.2 / 1.2
            size = 8 + int(4 * (0.5 - 0.5 * math.cos(phase * 2 * math.pi)))
        self._dot.setStyleSheet(f"background: {dot}; border-radius: {size // 2}px;")
        self._dot.setFixedSize(size, size)

        title_color = p.hud_text
        # On the red surface the muted grey drops below any usable contrast, so the secondary
        # text becomes white at reduced opacity — same hierarchy, legible ground.
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
        self.setFixedWidth(Size.HUD_W)
        self._reposition()
        self.show()
        self.raise_()
        self._offset.retarget(0.0)
        self._driver.start()
        self._ticker.start()

    def _nudge(self) -> None:
        """Any state change re-measures and re-targets rather than restarting: the pill grows or
        shrinks from where it currently is."""
        if self._state is not HudState.HIDDEN and not self.isVisible():
            self._started_at = time.monotonic()
            self._offset.jump_to(ENTER_OFFSET)
            self._appear()
        self.adjustSize()
        self.setFixedWidth(Size.HUD_W)
        self._offset.retarget(0.0)
        self._driver.start()
        self.update()

    def _shake(self) -> None:
        self._shake_until = time.monotonic() + Motion.SHAKE_MS / 1000
        self._shake_phase = 0.0
