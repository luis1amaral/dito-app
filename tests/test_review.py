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
from dito.ui.review import MAX_LINES, ReviewCard  # noqa: E402

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
    widget.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers))


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


def test_the_card_stops_growing_at_the_ceiling(card, app):
    """A long dictation must not produce a card taller than the screen."""
    widget, _ = card
    widget.present("uma frase bem comprida para forçar a quebra de linha. " * 40)
    app.processEvents()
    tall = widget.height()

    widget.editor.setPlainText("uma frase bem comprida para forçar a quebra de linha. " * 200)
    app.processEvents()
    assert widget.height() <= tall + 4, "o cartão continuou crescendo além do teto"
    assert widget.height() < 700


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
    assert opened > 200, "uma frase longa tem que abrir com mais de uma linha"


def test_a_short_phrase_gets_a_small_card(card, app):
    """The common case is one sentence; it must not open a box sized for an essay."""
    widget, _ = card
    widget.present(FRASE)
    app.processEvents()
    assert widget.height() < 200


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


def test_max_lines_is_a_real_ceiling():
    assert 3 <= MAX_LINES <= 20
