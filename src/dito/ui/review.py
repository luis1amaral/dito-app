"""Read what came out, fix it, send. Takes focus and gives it back — docs/armadilhas.md 7.2."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import _
from .components import Button, ControlSize, HudLabel, Switch, Variant
from .surface import paint_floating_surface, shadow_margin
from .theme import Alpha, Palette, Radius, Size, Space, hud_stylesheet

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
    send = Signal(str, bool)
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
        self.setStyleSheet(hud_stylesheet(p))

        pad = shadow_margin()
        outer = QVBoxLayout(self)
        # Room for the hand-painted shadow (docs/armadilhas.md 7.1).
        outer.setContentsMargins(Space.XL + pad, Space.LG + pad, Space.XL + pad, Space.LG + pad)
        outer.setSpacing(Space.MD)

        head = QHBoxLayout()
        head.setSpacing(Space.SM)
        self._title = HudLabel(role="hud-title")
        head.addWidget(self._title)
        head.addStretch(1)
        self._hint = HudLabel(role="hud-hint")
        head.addWidget(self._hint)
        outer.addLayout(head)

        self.editor = Editor()
        self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.editor.textChanged.connect(self._grow)
        self.editor.submit.connect(self._do_send)
        self.editor.cancel.connect(self._do_discard)
        outer.addWidget(self.editor)

        row = QHBoxLayout()
        row.setSpacing(Space.SM)

        # Off for every recording, on purpose: the vault is for the ones worth keeping, and a
        # switch that remembers "on" fills it with everything.
        self._vault = Switch(False, palette=p)
        row.addWidget(self._vault)
        self._vault_label = HudLabel(role="hud-hint")
        row.addWidget(self._vault_label)
        row.addStretch(1)

        # Primary rightmost, the order the platform's own dialogs use.
        self._discard_btn = Button(
            variant=Variant.HUD_OUTLINE, size=ControlSize.MD, palette=p, on_click=self._do_discard
        )
        row.addWidget(self._discard_btn)

        self._send_btn = Button(
            variant=Variant.HUD_SOLID, size=ControlSize.MD, palette=p, on_click=self._do_send
        )
        row.addWidget(self._send_btn)
        outer.addLayout(row)

        self.retranslate()

    # ---- text and palette --------------------------------------------------------------

    def retranslate(self) -> None:
        self._title.setText(_("Ready — edit it or send it"))
        self._hint.setText(_("⏎ sends · Tab discards"))
        self._vault_label.setText(_("Keep in Obsidian"))
        self._discard_btn.set_text(_("Discard"))
        self._send_btn.set_text(_("Send"))

    def set_palette(self, palette: Palette) -> None:
        """The card is dark in both themes (7.3), so this only ever repaints the same values."""
        self._palette = palette
        self.setStyleSheet(hud_stylesheet(palette))
        self.update()

    # ---- painting --------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        fill = QColor(self._palette.hud_surface)
        fill.setAlphaF(Alpha.REVIEW_SURFACE)
        pad = shadow_margin()
        card = self.rect().adjusted(pad, pad, -pad, -pad).toRectF()
        paint_floating_surface(QPainter(self), card, Radius.OVERLAY, fill)

    # ---- behaviour -------------------------------------------------------------------

    # Computed, not read from the widget, because sizing happens before layout — armadilhas 7.5.
    _TEXT_WIDTH = WIDTH - 2 * Space.XL - 2 * Space.MD - 2 * Size.HAIRLINE

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
        # scrollbar is exactly what the owner asked never to see. Only bites once shown, which is
        # why present() grows a second time.
        for _attempt in range(3):
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
        self._vault.setChecked(False)
        self.editor.setPlainText(text)
        cursor = self.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        self._grow()
        self.show()
        # Again, with geometry to read: hidden, the viewport lies and the document is still one
        # line, so _grow() cannot correct itself. See docs/armadilhas.md 7.16.
        self._grow()
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
        to_vault = self._vault.isChecked()
        self._finish()
        if text:
            self.send.emit(text, to_vault)
        else:
            self.discard.emit()

    def _do_discard(self) -> None:
        self._finish()
        self.discard.emit()
