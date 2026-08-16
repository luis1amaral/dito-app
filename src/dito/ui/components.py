"""The component set. Every screen is built from these, and every value in them comes from theme.

Anatomy is variant × size × state, and the six states are all present: `default`, `hover`,
`active`, `disabled`, `focus`, `loading`. Colour, geometry and duration live in the stylesheet
`theme.stylesheet` generates; what the stylesheet cannot do — a ring that must not move the layout,
a knob that must slide, a spinner that must turn — is painted here, from the same tokens.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import live
from .spring import Spring, SpringDriver
from .surface import paint_focus_ring
from .theme import Alpha, Motion, Palette, Radius, Size, Space, Type


class Variant(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    GHOST = "ghost"
    DANGER = "danger"
    HUD_SOLID = "hud-solid"
    HUD_OUTLINE = "hud-outline"


class ControlSize(StrEnum):
    SM = "sm"
    MD = "md"
    LG = "lg"


class Tone(StrEnum):
    NEUTRAL = "neutral"
    PRIMARY = "primary"
    SUCCESS = "success"
    ALERT = "alert"
    DANGER = "danger"


_HUD_VARIANTS = (Variant.HUD_SOLID, Variant.HUD_OUTLINE)


def repolish(widget: QWidget) -> None:
    """Qt only re-reads the stylesheet for a widget when its style is unpolished and polished."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_prop(widget: QWidget, name: str, value: object) -> None:
    widget.setProperty(name, value)
    repolish(widget)


def paint_spinner(painter: QPainter, box: QRectF, color: QColor, turn: float) -> None:
    """A faint full ring plus a quarter arc that turns — the shape everyone reads as "working"."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    track = QColor(color)
    track.setAlphaF(Alpha.SPINNER_TRACK)
    pen = QPen(track, Size.FOCUS_RING)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(box)

    pen.setColor(color)
    painter.setPen(pen)
    # Qt counts arcs in sixteenths of a degree, counter-clockwise from three o'clock.
    painter.drawArc(box, int(-turn * 16), -90 * 16)


def _spin_to(turning: _Turning, loading: bool) -> None:
    if loading:
        turning.start()
    else:
        turning.stop()


class _Turning:
    """The spinner's clock, shared by every component that can be in the loading state."""

    def __init__(self, owner: QWidget) -> None:
        self.turn = 0.0
        self._owner = owner
        self._timer = QTimer(owner)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)

    def _step(self) -> None:
        self.turn = (self.turn + 360 * self._timer.interval() / Motion.SPINNER_MS) % 360
        self._owner.update()

    def start(self) -> None:
        if not self._timer.isActive():
            self.turn = 0.0
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    @property
    def running(self) -> bool:
        return self._timer.isActive()


class Button(QPushButton):
    """Variant × size × the six states. Loading swaps the label for a spinner and eats the click."""

    def __init__(
        self,
        text: str = "",
        variant: Variant = Variant.SECONDARY,
        size: ControlSize = ControlSize.MD,
        palette: Palette | None = None,
        on_click: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._palette = palette or live.palette()
        self._resting_text = text
        self._spin = _Turning(self)

        self.setProperty("variant", str(variant))
        self.setProperty("size", str(size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if on_click is not None:
            self.clicked.connect(on_click)

    # ---- state -------------------------------------------------------------------------

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_text(self, text: str) -> None:
        """Goes through here so a finished load restores the CURRENT label, not a stale one."""
        self._resting_text = text
        if not self._spin.running:
            self.setText(text)

    def set_loading(self, loading: bool) -> None:
        if loading == self._spin.running:
            return
        if loading:
            # Frozen width: a button that shrinks to spinner size drags the whole row with it.
            self.setMinimumWidth(max(self.width(), self.sizeHint().width()))
            self.setText("")
            self._spin.start()
        else:
            self._spin.stop()
            self.setText(self._resting_text)
            self.setMinimumWidth(0)
        set_prop(self, "loading", "true" if loading else "false")

    @property
    def loading(self) -> bool:
        return self._spin.running

    # ---- behaviour ---------------------------------------------------------------------

    def hitButton(self, pos) -> bool:  # noqa: N802 - Qt override
        """Busy is not disabled: it still reads as the live action, it just refuses a second one."""
        return not self._spin.running and super().hitButton(pos)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        if self._spin.running and event.key() in (
            Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter
        ):
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        if self._spin.running:
            side = Size.SPINNER
            box = QRectF(
                (self.width() - side) / 2, (self.height() - side) / 2, side, side
            ).adjusted(1, 1, -1, -1)
            paint_spinner(painter, box, QColor(self._ink()), self._spin.turn)
        if self.hasFocus():
            paint_focus_ring(
                painter, QRectF(self.rect()), Radius.CONTROL, QColor(self._ring())
            )

    def _hud(self) -> bool:
        return self.property("variant") in _HUD_VARIANTS

    def _ink(self) -> str:
        p = self._palette
        if self.property("variant") == Variant.HUD_SOLID:
            return p.hud_surface
        if self._hud():
            return p.hud_text
        if self.property("variant") in (Variant.PRIMARY, Variant.DANGER):
            return p.text_inverse
        return p.text_primary

    def _ring(self) -> str:
        return self._palette.hud_text if self._hud() else self._palette.focus_ring


class Field(QLineEdit):
    """One line of text, with the invalid and loading states the plain QLineEdit does not have."""

    def __init__(
        self,
        text: str = "",
        placeholder: str = "",
        palette: Palette | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._palette = palette or live.palette()
        self._spin = _Turning(self)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(Size.CONTROL_H)

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_invalid(self, invalid: bool) -> None:
        set_prop(self, "invalid", "true" if invalid else "false")

    def set_loading(self, loading: bool) -> None:
        if loading == self._spin.running:
            return
        self.setReadOnly(loading)
        _spin_to(self._spin, loading)
        set_prop(self, "loading", "true" if loading else "false")

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        if self._spin.running:
            side = Size.SPINNER
            box = QRectF(
                self.width() - side - Space.MD, (self.height() - side) / 2, side, side
            ).adjusted(1, 1, -1, -1)
            paint_spinner(painter, box, QColor(self._palette.text_muted), self._spin.turn)
        if self.hasFocus():
            paint_focus_ring(
                painter, QRectF(self.rect()), Radius.CONTROL, QColor(self._palette.focus_ring)
            )


class Spin(QDoubleSpinBox):
    """The numeric half of Field. Same anatomy, same ring — a stepper is still a form control."""

    def __init__(
        self,
        suffix: str = "",
        minimum: float = 0.0,
        maximum: float = 100.0,
        palette: Palette | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette or live.palette()
        self.setRange(minimum, maximum)
        self.setSuffix(suffix)
        self.setMinimumHeight(Size.CONTROL_H)
        self.setFixedWidth(Size.FIELD_W_SM)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_invalid(self, invalid: bool) -> None:
        set_prop(self, "invalid", "true" if invalid else "false")

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        # See docs/armadilhas.md 7.12: the wheel edits the value of whatever it passes over.
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        if self.hasFocus():
            paint_focus_ring(
                QPainter(self),
                QRectF(self.rect()),
                Radius.CONTROL,
                QColor(self._palette.focus_ring),
            )


class Select(QComboBox):
    """A picker with a drawn chevron: Qt's own arrow is a bitmap that ignores the theme."""

    def __init__(
        self,
        options: list[tuple[str, str]] | None = None,
        palette: Palette | None = None,
        on_change: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette or live.palette()
        self._spin = _Turning(self)
        self.setMinimumHeight(Size.CONTROL_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if options:
            self.set_options(options)
        if on_change is not None:
            self.currentIndexChanged.connect(lambda: on_change(self.value()))

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_options(self, options: list[tuple[str, str]]) -> None:
        """Rebuilds the list keeping the chosen VALUE, so relabelling never changes the setting."""
        chosen = self.value()
        blocked = self.blockSignals(True)
        self.clear()
        for value, label in options:
            self.addItem(label, value)
        self.set_value(chosen)
        self.blockSignals(blocked)
        # See docs/armadilhas.md 7.13: restoring outside the block made retranslating write config.
        if self.value() != chosen:
            self.currentIndexChanged.emit(self.currentIndex())

    def value(self) -> str:
        data = self.currentData()
        return "" if data is None else str(data)

    def set_value(self, value: str) -> None:
        index = self.findData(value)
        self.setCurrentIndex(index if index >= 0 else 0)

    def set_loading(self, loading: bool) -> None:
        if loading == self._spin.running:
            return
        _spin_to(self._spin, loading)
        set_prop(self, "loading", "true" if loading else "false")

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        # See docs/armadilhas.md 7.12: a combo keeps focus after choosing, so "only when focused"
        # still lets the wheel rewrite the setting on the way past. It never takes the wheel.
        event.ignore()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        side = Size.SPINNER
        right = self.width() - Space.MD
        if self._spin.running:
            box = QRectF(right - side, (self.height() - side) / 2, side, side).adjusted(
                1, 1, -1, -1
            )
            paint_spinner(painter, box, QColor(self._palette.text_muted), self._spin.turn)
        elif self.isEnabled():
            # Hidden while disabled: nothing will drop down, so nothing should invite the click.
            self._paint_chevron(painter, right)
        if self.hasFocus():
            paint_focus_ring(
                painter, QRectF(self.rect()), Radius.CONTROL, QColor(self._palette.focus_ring)
            )

    def _paint_chevron(self, painter: QPainter, right: float) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._palette.text_muted), Size.HAIRLINE + 0.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        width = Size.CHEVRON
        drop = width / 2
        left = right - width
        top = (self.height() - drop) / 2
        painter.drawPolyline(
            [QPointF(left, top), QPointF(left + drop, top + drop), QPointF(right, top)]
        )


class Switch(QAbstractButton):
    """Painted, and the knob is on a spring: QSS neither animates nor draws a rounded knob."""

    def __init__(
        self,
        checked: bool = False,
        palette: Palette | None = None,
        on_toggle: Callable[[bool], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette or live.palette()
        self._spin = _Turning(self)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Tall enough to be a real target; the track is drawn centred inside it.
        self.setFixedSize(Size.SWITCH_W, Size.TOUCH_TARGET)

        self._driver = SpringDriver(self)
        self._slide = self._driver.add(
            Spring(1.0 if checked else 0.0, response=Motion.CONTROL_RESPONSE)
        )
        self._knob = self._driver.add(
            Spring(float(Size.SWITCH_KNOB), response=Motion.CONTROL_RESPONSE)
        )
        self._driver.frame.connect(self.update)

        self.setChecked(checked)
        self.toggled.connect(self._on_toggled)
        if on_toggle is not None:
            self.toggled.connect(on_toggle)

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_loading(self, loading: bool) -> None:
        if loading == self._spin.running:
            return
        _spin_to(self._spin, loading)
        self.setEnabled(not loading)

    def _on_toggled(self, checked: bool) -> None:
        self._slide.retarget(1.0 if checked else 0.0)
        self._driver.start()

    # Pressed stretches the knob, the way a physical switch resists before it goes over.
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._knob.retarget(float(Size.SWITCH_KNOB_PRESSED))
        self._driver.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._knob.retarget(float(Size.SWITCH_KNOB))
        self._driver.start()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        top = (self.height() - Size.SWITCH_H) / 2
        track = QRectF(0, top, Size.SWITCH_W, Size.SWITCH_H)
        radius = Size.SWITCH_H / 2

        if not self.isEnabled():
            fill, knob_ink = p.border, p.text_muted
        elif self.isChecked():
            fill = p.primary_hover if self.underMouse() else p.primary
            knob_ink = p.surface
        else:
            fill = p.text_secondary if self.underMouse() else p.text_muted
            knob_ink = p.surface

        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(track, radius, radius)

        margin = (Size.SWITCH_H - Size.SWITCH_KNOB) / 2
        diameter = self._knob.value
        travel = Size.SWITCH_W - 2 * margin - diameter
        x = margin + travel * self._slide.value
        y = top + (Size.SWITCH_H - diameter) / 2
        knob = QRectF(x, y, diameter, diameter)

        if self._spin.running:
            paint_spinner(painter, knob.adjusted(2, 2, -2, -2), QColor(knob_ink), self._spin.turn)
        else:
            painter.setBrush(QColor(knob_ink))
            painter.drawEllipse(knob)

        if self.hasFocus():
            paint_focus_ring(painter, track, radius, QColor(p.focus_ring))


class Badge(QLabel):
    """A status word, not a control: filled in its role colour, or a grey step when neutral."""

    def __init__(self, text: str = "", tone: Tone = Tone.NEUTRAL, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setProperty("role", "badge")
        self.setProperty("tone", str(tone))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_tone(self, tone: Tone) -> None:
        set_prop(self, "tone", str(tone))


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "divider")
        self.setFixedHeight(Size.HAIRLINE)


def text(content: str, role: str = "", wrap: bool = False) -> QLabel:
    """Every piece of prose on screen goes through a role, never through a local stylesheet."""
    label = QLabel(content)
    if role:
        label.setProperty("role", role)
    label.setWordWrap(wrap)
    return label


class Card(QFrame):
    """A titled plane. Rows go in the body, so the header's spacing is decided exactly once."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(Space.XL, Space.LG, Space.XL, Space.LG)
        outer.setSpacing(Space.MD)

        self._title = text(title, "title")
        self._title.setVisible(bool(title))
        outer.addWidget(self._title)

        self._subtitle = text(subtitle, "hint", wrap=True)
        self._subtitle.setVisible(bool(subtitle))
        outer.addWidget(self._subtitle)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(Space.MD)
        outer.addLayout(self.body)

    def set_heading(self, title: str, subtitle: str = "") -> None:
        self._title.setText(title)
        self._title.setVisible(bool(title))
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))

    def add(self, *widgets: QWidget) -> None:
        for widget in widgets:
            self.body.addWidget(widget)

    def add_divider(self) -> None:
        self.body.addWidget(Divider())


class FormRow(QWidget):
    """Label, control, hint, error — in that order, with the error's line reserved up front.

    `inline` puts the control on the right of its label instead of under it, which is what a
    switch wants: stacked, a 44 px control under a 13 px label reads as two unrelated things.
    """

    def __init__(
        self,
        label: str,
        control: QWidget,
        hint: str = "",
        inline: bool = False,
        errorable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.control = control

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(Space.XS)

        self._label = text(label, "label", wrap=True)
        self._hint = text(hint, "hint", wrap=True)
        self._hint.setVisible(bool(hint))

        if inline:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(Space.LG)
            stack = QVBoxLayout()
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(Space.XS)
            stack.addWidget(self._label)
            stack.addWidget(self._hint)
            row.addLayout(stack, 1)
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
            outer.addLayout(row)
        else:
            outer.addWidget(self._label)
            outer.addWidget(control)
            outer.addWidget(self._hint)

        # A blank keeps the line: an error that appears by pushing the layout moves the click
        # target the user was already aiming at.
        self._error = text(" ", "danger", wrap=True)
        self._error.setVisible(errorable)
        outer.addWidget(self._error)

    def set_texts(self, label: str, hint: str = "") -> None:
        self._label.setText(label)
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))

    def set_error(self, message: str) -> None:
        self._error.setText(message or " ")
        self._error.setVisible(True)
        invalid = getattr(self.control, "set_invalid", None)
        if invalid is not None:
            invalid(bool(message))


class Row(QWidget):
    """Two controls side by side that must share the width evenly — nothing more than that."""

    def __init__(self, *widgets: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(Space.LG)
        for widget in widgets:
            box.addWidget(widget, 1)


class HudLabel(QLabel):
    """Text on the pill. Its colour changes with the pill's STATE, so it is set, never hardcoded."""

    def __init__(self, content: str = "", role: str = "hud-title", mono: bool = False) -> None:
        super().__init__(content)
        self.setProperty("role", role)
        self._mono = mono
        self._size = Type.CAPTION if role == "hud-hint" else Type.BODY

    def set_tone(self, color: str, weight: int = Type.MEDIUM) -> None:
        family = Type.MONO if self._mono else Type.FAMILY
        self.setStyleSheet(
            f"color: {color}; font-family: {family};"
            f" font-size: {self._size}px; font-weight: {weight};"
        )
