"""Component behaviour that only shows up under a mouse — rendered for real, offscreen.

The wheel case is here because it passed every other gate: it type-checks, it lints, and reading
the source shows nothing wrong. It only appears when someone scrolls the settings screen and a
setting changes on the way past. See docs/armadilhas.md 7.12.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="PySide6 não instalado")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dito.ui.components import Select, Spin  # noqa: E402


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    yield existing or QApplication([])


def _wheel(widget, notches: int = -1) -> QWheelEvent:
    point = QPointF(widget.rect().center())
    return QWheelEvent(
        point,
        QPointF(widget.mapToGlobal(QPoint(0, 0))) + point,
        QPoint(0, notches * 120),
        QPoint(0, notches * 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_the_wheel_never_changes_a_select(app):
    """Scrolling the settings page was rewriting the model, the microphone or the language."""
    select = Select([("a", "A"), ("b", "B"), ("c", "C")])
    select.set_value("a")

    select.wheelEvent(_wheel(select))

    assert select.value() == "a"


def test_a_focused_select_still_refuses_the_wheel(app):
    """A combo keeps focus after you choose, so "only when focused" leaves the bug alive."""
    select = Select([("a", "A"), ("b", "B")])
    select.set_value("a")
    select.setFocus()

    select.wheelEvent(_wheel(select))

    assert select.value() == "a"


def test_the_wheel_passes_through_so_the_page_scrolls(app):
    """Ignoring is what makes Qt hand the event to the scroll area underneath."""
    select = Select([("a", "A"), ("b", "B")])
    event = _wheel(select)
    event.accept()

    select.wheelEvent(event)

    assert not event.isAccepted()


def test_relabelling_a_select_does_not_announce_a_change(app):
    """Retranslating the settings screen was writing config.toml: set_value ran outside the signal
    block, so every relabel fired on_change into _persist(). armadilhas 7.13."""
    seen = []
    select = Select([("a", "A"), ("b", "B")], on_change=seen.append)
    select.set_value("b")
    seen.clear()

    select.set_options([("a", "A traduzido"), ("b", "B traduzido")])

    assert select.value() == "b"
    assert seen == []


def test_an_option_that_disappeared_is_still_announced(app):
    """The other half: silence is right for a relabel and wrong for a value that is really gone."""
    seen = []
    select = Select([("a", "A"), ("b", "B")], on_change=seen.append)
    select.set_value("b")
    seen.clear()

    select.set_options([("a", "A"), ("c", "C")])

    assert select.value() == "a"
    assert seen == ["a"]


def test_a_spin_steps_only_when_it_has_the_focus(app):
    """The stepper keeps the wheel — focus there is deliberate, and stepping is the interaction."""
    spin = Spin(minimum=0.0, maximum=10.0)
    spin.setValue(5.0)

    spin.wheelEvent(_wheel(spin))
    assert spin.value() == 5.0

    # Offscreen refuses focus to a widget that was never shown, so the second half would pass
    # for the wrong reason: unfocused, like the first.
    spin.show()
    spin.activateWindow()
    spin.setFocus()
    app.processEvents()
    assert spin.hasFocus()

    spin.wheelEvent(_wheel(spin, notches=1))
    assert spin.value() != 5.0
