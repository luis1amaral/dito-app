"""Read what came out, fix it, send. Takes focus and gives it back — docs/armadilhas.md 7.2."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .surface import paint_floating_surface, shadow_margin
from .theme import Palette, Radius, Size, Space, Type

MARGIN = Space.XXXL
WIDTH = 560
MIN_LINES = 3
# Header, buttons, paddings and shadow, before the widget has been laid out even once.
_CHROME_GUESS = 200


class Editor(QPlainTextEdit):
    """Intercepts the keys before the text box eats them — armadilhas 7.11."""

    submit = Signal()
    cancel = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)     # Shift+Enter is the newline
            else:
                self.submit.emit()
            return
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Escape):
            self.cancel.emit()
            return
        super().keyPressEvent(event)


class ReviewCard(QWidget):
    send = Signal(str)
    discard = Signal()

    def __init__(self, palette: Palette, focus_broker=None) -> None:
        super().__init__(None)
        self._palette = palette
        self._focus = focus_broker

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH + 2 * shadow_margin())
        self._build(palette)
        self.hide()

    # ---- construction ----------------------------------------------------------------

    def _build(self, p: Palette) -> None:
        pad = shadow_margin()
        outer = QVBoxLayout(self)
        # Room for the hand-painted shadow (docs/armadilhas.md 7.1).
        outer.setContentsMargins(Space.XL + pad, Space.LG + pad, Space.XL + pad, Space.LG + pad)
        outer.setSpacing(Space.MD)

        head = QHBoxLayout()
        head.setSpacing(Space.SM)
        title = QLabel("Pronto — edite ou envie")
        title.setStyleSheet(
            f"color: {p.hud_text}; font-size: {Type.BODY}px; font-weight: {Type.SEMIBOLD};"
        )
        head.addWidget(title)
        head.addStretch(1)
        hint = QLabel("⏎ envia · Tab descarta")
        hint.setStyleSheet(f"color: {p.hud_muted}; font-size: {Type.CAPTION}px;")
        head.addWidget(hint)
        outer.addLayout(head)

        self.editor = Editor()
        self.editor.setStyleSheet(
            f"QPlainTextEdit {{ background: rgba(255,255,255,0.06); color: {p.hud_text};"
            f" border: 1px solid rgba(255,255,255,0.14); border-radius: {Radius.CONTROL}px;"
            f" padding: {Space.SM}px {Space.MD}px; font-size: {Type.BODY}px;"
            f" selection-background-color: {p.hud_recording}; }}"
            f"QPlainTextEdit:focus {{ border: 1px solid {p.hud_text}; }}"
            # Restyled here too: this stylesheet overrides the app's and Qt would draw its arrows.
            f"QScrollBar:vertical {{ background: transparent; width: {Space.SM}px; margin: 0; }}"
            f"QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.28);"
            f" border-radius: {Space.XS}px; min-height: {Space.XXL}px; }}"
            f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}"
            f"QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}"
        )
        self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.editor.textChanged.connect(self._grow)
        self.editor.submit.connect(self._do_send)
        self.editor.cancel.connect(self._do_discard)
        outer.addWidget(self.editor)

        row = QHBoxLayout()
        row.setSpacing(Space.SM)
        row.addStretch(1)

        self._discard_btn = self._chip("Descartar", primary=False)
        self._discard_btn.clicked.connect(self._do_discard)
        row.addWidget(self._discard_btn)

        self._send_btn = self._chip("Enviar", primary=True)
        self._send_btn.clicked.connect(self._do_send)
        row.addWidget(self._send_btn)
        outer.addLayout(row)


    def _chip(self, label: str, primary: bool) -> QPushButton:
        p = self._palette
        button = QPushButton(label)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        # Primary rightmost, the order the platform's own dialogs use.
        if primary:
            style = (
                f"QPushButton {{ background: {p.hud_text}; color: {p.hud_surface};"
                f" border: none; font-weight: {Type.SEMIBOLD};"
            )
            hover = "rgba(255,255,255,0.86)"
            pressed = "rgba(255,255,255,0.74)"
        else:
            # Outlined, not filled: WCAG 1.4.11 applies to the outline, and a light fill vanishes.
            style = (
                f"QPushButton {{ background: transparent; color: {p.hud_text};"
                f" border: 1px solid rgba(255,255,255,0.35); font-weight: {Type.MEDIUM};"
            )
            hover = "rgba(255,255,255,0.10)"
            pressed = "rgba(255,255,255,0.18)"
        button.setStyleSheet(
            style
            + f" border-radius: {Radius.CONTROL}px; padding: {Space.SM}px {Space.LG}px;"
            f" min-height: {Size.CONTROL_H}px; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
        )
        return button

    # ---- painting --------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        fill = QColor(self._palette.hud_surface)
        fill.setAlphaF(0.97)
        pad = shadow_margin()
        card = self.rect().adjusted(pad, pad, -pad, -pad).toRectF()
        paint_floating_surface(QPainter(self), card, Radius.OVERLAY, fill)

    # ---- behaviour -------------------------------------------------------------------

    # Computed, not read from the widget, because sizing happens before layout — armadilhas 7.5.
    _TEXT_WIDTH = WIDTH - 2 * Space.XL - 2 * Space.MD - 2

    def _grow(self) -> None:
        """Grows to fit the whole text; the only ceiling is the screen — armadilhas 7.5."""
        metrics = self.editor.fontMetrics()
        text = self.editor.toPlainText() or " "
        # Font metrics, not the document: QPlainTextEdit lays out against its viewport and would
        # report one line before the widget has ever been shown.
        needed = metrics.boundingRect(
            0, 0, self._TEXT_WIDTH, 1 << 20,
            int(Qt.TextFlag.TextWordWrap) | int(Qt.TextFlag.TextWrapAnywhere),
            text,
        ).height()
        lines = max(1, -(-needed // metrics.lineSpacing()))
        ceiling = self._line_ceiling()
        self._resize_to(min(lines, ceiling), metrics.lineSpacing())

        # Self-correcting: the estimate and the widget's own layout can differ by a line, and a
        # scrollbar is exactly what the owner asked never to see. Ask the realised widget.
        for _ in range(3):
            document = self.editor.document().size().height() * metrics.lineSpacing()
            if document <= self.editor.viewport().height() or lines >= ceiling:
                break
            lines += 1
            self._resize_to(min(lines, ceiling), metrics.lineSpacing())

    def _resize_to(self, lines: int, spacing: int) -> None:
        # Half a line of slack: QPlainTextEdit counts in blocks and clips the last one when the
        # viewport height is not an exact multiple of the line spacing.
        self.editor.setFixedHeight(lines * spacing + spacing // 2 + Space.XL)
        self.adjustSize()
        self.setFixedWidth(WIDTH + 2 * shadow_margin())
        self._place()

    def _line_ceiling(self) -> int:
        """How many lines still fit on screen once the card's own chrome is accounted for."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return 24
        spacing = self.editor.fontMetrics().lineSpacing() or 1
        chrome = max(0, self.height() - self.editor.height()) or _CHROME_GUESS
        room = screen.availableGeometry().height() - 2 * MARGIN - chrome
        return max(MIN_LINES, room // spacing)

    def _place(self) -> None:
        screen = self.screen() or self.window().screen()
        area = screen.availableGeometry()
        x = area.center().x() - self.width() // 2
        y = area.bottom() - self.height() - MARGIN
        self.move(x, y)

    def present(self, text: str) -> None:
        self.editor.setPlainText(text)
        cursor = self.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        self._grow()
        self.show()
        self.raise_()
        self.activateWindow()
        self.editor.setFocus()
        if self._focus is not None:
            self._focus.take(int(self.winId()))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter keeps adding lines; plain Enter is the send.
                super().keyPressEvent(event)
                return
            self._do_send()
            return
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Escape):
            self._do_discard()
            return
        super().keyPressEvent(event)

    def _finish(self) -> None:
        self.hide()
        if self._focus is not None:
            # Focus goes back BEFORE the caller pastes, or the text lands in this card.
            self._focus.give_back()

    def _do_send(self) -> None:
        text = self.editor.toPlainText().strip()
        self._finish()
        if text:
            self.send.emit(text)
        else:
            self.discard.emit()

    def _do_discard(self) -> None:
        self._finish()
        self.discard.emit()
