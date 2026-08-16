"""The review card — read it, fix it, then send.

The rule that matters most here is not visual: **focus has to go back before the paste.** The card
takes the keyboard because you type in it, and the text is destined for the window you were typing
in before. Get the order wrong and the dictation pastes into Dito's own box.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="PySide6 não instalado")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dito.ui import theme  # noqa: E402
from dito.ui.review import MIN_LINES, ReviewCard  # noqa: E402
from dito.ui.surface import shadow_margin  # noqa: E402

FRASE = "Testando, testando, e agora está me ouvindo, não é?"


class SpyBroker:
    """Records the order of focus operations, which is the thing under test."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def take(self, _window_id: int) -> None:
        self.calls.append("take")

    def give_back(self) -> None:
        self.calls.append("give_back")


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def card(app):
    broker = SpyBroker()
    widget = ReviewCard(theme.LIGHT, focus_broker=broker)
    yield widget, broker
    widget.close()


def press(widget, key: Qt.Key, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    """Sends to the EDITOR, which is what has focus in real use.

    The first version of this helper sent the event to the card, which proved the card's handler
    worked and nothing else — the editor eats Return before it ever gets there, so Enter inserted
    a newline instead of sending. The bug shipped and the user found it."""
    widget.editor.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers))


def test_enter_sends_what_is_on_screen(card, app):
    widget, _ = card
    sent: list[str] = []
    widget.send.connect(sent.append)

    widget.present(FRASE)
    press(widget, Qt.Key.Key_Return)

    assert sent == [FRASE]
    assert not widget.isVisible()


def test_edits_are_what_gets_sent(card, app):
    """The whole point of the card: the text can be wrong and you fix it."""
    widget, _ = card
    sent: list[str] = []
    widget.send.connect(sent.append)

    widget.present("testando um dois tres")
    widget.editor.setPlainText("testando 1 2 3")
    press(widget, Qt.Key.Key_Return)

    assert sent == ["testando 1 2 3"]


def test_tab_discards_and_sends_nothing(card, app):
    widget, _ = card
    sent, dropped = [], []
    widget.send.connect(sent.append)
    widget.discard.connect(lambda: dropped.append(True))

    widget.present(FRASE)
    press(widget, Qt.Key.Key_Tab)

    assert sent == []
    assert dropped == [True]


def test_escape_also_discards(card, app):
    widget, _ = card
    dropped = []
    widget.discard.connect(lambda: dropped.append(True))

    widget.present(FRASE)
    press(widget, Qt.Key.Key_Escape)
    assert dropped == [True]


def test_shift_enter_adds_a_line_instead_of_sending(card, app):
    widget, _ = card
    sent = []
    widget.send.connect(sent.append)

    widget.present(FRASE)
    press(widget, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)

    assert sent == [], "Shift+Enter é quebra de linha, não envio"
    assert widget.isVisible()


def test_focus_is_returned_before_the_text_is_released(card, app):
    """The ordering guarantee. If `send` fired before `give_back`, the paste would race the focus
    change and land in this card."""
    widget, broker = card
    order: list[str] = []
    widget.send.connect(lambda _t: order.append("send"))

    widget.present(FRASE)
    assert broker.calls == ["take"]

    press(widget, Qt.Key.Key_Return)
    assert broker.calls == ["take", "give_back"]
    assert order == ["send"]
    # give_back was queued while the card was still hiding, before the send signal went out.
    assert broker.calls.index("give_back") == 1


def test_discarding_also_gives_focus_back(card, app):
    """Forgetting this leaves the keyboard pointing at a hidden window."""
    widget, broker = card
    widget.present(FRASE)
    press(widget, Qt.Key.Key_Tab)
    assert broker.calls == ["take", "give_back"]


def test_sending_an_emptied_box_discards_rather_than_sending_nothing(card, app):
    widget, _ = card
    sent, dropped = [], []
    widget.send.connect(sent.append)
    widget.discard.connect(lambda: dropped.append(True))

    widget.present(FRASE)
    widget.editor.setPlainText("   ")
    press(widget, Qt.Key.Key_Return)

    assert sent == []
    assert dropped == [True]


def test_the_card_opens_at_its_final_height(card, app):
    """It used to open one line tall and then jump, because the height was measured before the
    document had a width to wrap against — a glitch at exactly the moment you start reading."""
    widget, _ = card
    longa = "uma frase bem comprida para forçar a quebra de linha. " * 12

    widget.present(longa)
    opened = widget.height()
    app.processEvents()
    settled = widget.height()

    assert opened == settled, f"abriu com {opened}px e assentou em {settled}px"
    assert card_height(widget) > 180, "uma frase longa tem que abrir com mais de uma linha"


def card_height(widget) -> int:
    """The visible card, without the padding the window reserves for the painted shadow."""
    return widget.height() - 2 * shadow_margin()


def test_a_short_phrase_gets_a_small_card(card, app):
    """The common case is one sentence; it must not open a box sized for an essay."""
    widget, _ = card
    widget.present(FRASE)
    app.processEvents()
    assert card_height(widget) < 200


def test_nothing_is_sent_on_a_timer(card, app):
    """The previous version auto-closed after 30 seconds. Removed on request: a dictated message
    must never vanish, and must never send, on its own."""
    widget, _ = card
    sent, dropped = [], []
    widget.send.connect(sent.append)
    widget.discard.connect(lambda: dropped.append(True))

    widget.present(FRASE)
    for _ in range(20):
        app.processEvents()

    assert widget.isVisible()
    assert sent == [] and dropped == []


def test_enter_does_not_leave_a_newline_behind(card, app):
    """The reported bug: Enter added a line instead of sending, because the text box handles
    Return itself and the card's handler never ran."""
    widget, _ = card
    sent: list[str] = []
    widget.send.connect(sent.append)

    widget.present(FRASE)
    press(widget, Qt.Key.Key_Return)

    assert sent == [FRASE], "Enter tem que enviar, não quebrar linha"
    assert "\n" not in (sent[0] if sent else "")


def test_shift_enter_really_inserts_a_line(card, app):
    widget, _ = card
    sent: list[str] = []
    widget.send.connect(sent.append)

    widget.present("primeira")
    press(widget, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    app.processEvents()

    assert sent == []
    assert widget.editor.toPlainText().count("\n") == 1


def test_the_card_never_needs_a_scrollbar_for_a_normal_dictation(card, app):
    """The owner asked for no scrolling: the text stays visible and the card grows instead."""
    widget, _ = card
    widget.present("uma frase de ditado bem comprida, do tamanho que sai na prática. " * 6)
    app.processEvents()

    # What matters is that no text is hidden. The scrollbar is off anyway; a clipped last line
    # would be the real failure.
    metrics = widget.editor.fontMetrics()
    document = widget.editor.document().size().height() * metrics.lineSpacing()
    assert document <= widget.editor.viewport().height(), (
        f"texto cortado: documento {document}px num viewport de "
        f"{widget.editor.viewport().height()}px"
    )


def test_growth_stops_at_the_screen_not_at_a_magic_number(card, app):
    widget, _ = card
    widget.present("linha muito comprida para forçar quebra. " * 400)
    app.processEvents()

    screen = app.primaryScreen().availableGeometry().height()
    assert widget.height() <= screen, "o cartão passou da tela"
    assert widget._line_ceiling() >= MIN_LINES
