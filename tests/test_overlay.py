"""The pill, rendered for real on Qt's offscreen platform.

Two things are worth testing here and cannot be tested by reading the source:

1. **The alarm must be distinguishable without colour.** Colour alone is not accessible, and it
   also fails the ordinary case of glancing at the corner of the screen. The waveform collapsing
   to a flat line is the second, non-colour signal — this measures that the rendered pixels
   actually differ, rather than trusting that they do.

2. **The window must never be focusable.** The transcribed text is pasted into whatever the user
   was typing in; a pill that takes focus pastes into itself. That is a window-flag property, and
   a flag is exactly the kind of thing a refactor drops by accident.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="PySide6 não instalado")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dito import i18n  # noqa: E402
from dito.ui import theme  # noqa: E402
from dito.ui.overlay import HudState, Overlay, _clock  # noqa: E402


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    yield existing or QApplication([])


@pytest.fixture
def hud(app):
    widget = Overlay(theme.LIGHT)
    yield widget
    widget.close()


def ink(widget) -> float:
    """Fraction of the waveform's own area that is painted.

    Measured on the waveform widget rather than on the whole pill: the pill's area barely changes
    between states, so a whole-window signature reports ~0.25 either way and proves nothing. The
    waveform is the element whose SHAPE carries the alarm — thirteen bars versus one flat line —
    so that is what has to be measured.
    """
    image = widget.grab().toImage().convertToFormat(
        widget.grab().toImage().Format.Format_ARGB32
    )
    corner = image.pixelColor(0, 0)
    lit = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y) != corner
    )
    return lit / max(1, image.width() * image.height())


def test_the_pill_never_takes_focus(hud):
    flags = hud.windowFlags()
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert hud.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_overlay_alarm_changes_shape(hud, app):
    """The guarantee referenced by test_warning_and_alarm_are_different_hues: the alarm is
    readable without relying on colour at all."""
    hud.show_recording()
    for _ in range(20):
        hud.push_level(0.06)
        hud._wave.tick()
    app.processEvents()
    recording = ink(hud._wave)

    hud.show_dead("o microfone não está captando nada", "Corrigir")
    hud._wave.tick()
    app.processEvents()
    alarmed = ink(hud._wave)

    assert recording > alarmed * 2, (
        f"gravando e alarme desenham quase o mesmo ({recording:.3f} vs {alarmed:.3f}) — "
        "quem não distingue as cores não veria diferença"
    )


def test_alarm_shows_the_fix_action_and_the_reason(hud, app):
    hud.show_dead("o ganho de captura do hardware está em 0%", "Corrigir")
    app.processEvents()
    assert hud._action.isVisible()
    assert hud._action.text() == "Corrigir"
    assert "ganho" in hud._detail.text()
    # Source strings are English; with no catalogue installed they fall through unchanged.
    assert hud._title.text() == "NO AUDIO"


def test_alarm_foreground_does_not_flip_with_the_theme(app):
    """The pill floats over the user's content with a surface of its own, so its foreground has
    to be fixed too. Using `text_inverse` — which flips with the theme — put a near-black dot on
    the red fill in dark mode.

    It used to compare `_dot.styleSheet()`, which is empty on both sides because the dot is
    painted, so it proved nothing. It now compares the colours that actually reach the paint
    calls — and that is what caught the waveform still being drawn in `text_inverse`."""
    shots = {}
    for palette in (theme.LIGHT, theme.DARK):
        widget = Overlay(palette)
        widget.show_dead("nada", None)
        app.processEvents()
        shots[palette.mode] = (widget._dot.color, widget._wave.color)
        widget.close()
    assert shots[theme.Mode.LIGHT] == shots[theme.Mode.DARK]


def test_every_colour_the_alarm_paints_is_legible_on_the_red_fill(app):
    """The dot and the flat line are the alarm's two non-text signals; both sit on `hud_danger`."""
    widget = Overlay(theme.DARK)
    widget.show_dead("nada", None)
    app.processEvents()
    for painted in (widget._dot.color, widget._wave.color):
        ratio = theme.contrast(painted, theme.DARK.hud_danger)
        assert ratio >= theme.CONTRAST_FLOOR["control_edge"], f"{painted}: {ratio:.2f}"
    widget.close()


def test_the_pill_speaks_the_installed_language(app):
    """Changing the language must not need a restart, and must not leave two languages on screen."""
    widget = Overlay(theme.LIGHT)
    widget.show_recording()
    assert widget._title.text() == "Recording"

    i18n.setup("pt_BR")
    try:
        widget.retranslate()
        assert widget._title.text() == "Gravando"
    finally:
        i18n.setup("en")
    widget.retranslate()
    assert widget._title.text() == "Recording"
    widget.close()


def test_alarm_without_a_known_fix_hides_the_button(hud, app):
    """A button that does nothing is worse than no button."""
    hud.show_dead("o microfone não está captando nada", None)
    app.processEvents()
    assert not hud._action.isVisible()


def test_quiet_is_not_the_same_state_as_dead(hud, app):
    hud.show_quiet("chegue mais perto do microfone")
    assert hud._state is HudState.QUIET
    hud.show_dead("nada", None)
    assert hud._state is HudState.DEAD


def test_recording_state_recovers_after_the_alarm_clears(hud, app):
    hud.show_recording()
    hud.show_dead("nada", None)
    hud.show_recording()
    assert hud._state is HudState.RECORDING
    assert not hud._action.isVisible()


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "00:00"), (9, "00:09"), (75, "01:15"), (3599, "59:59"), (3600, "1:00:00"),
     (7325, "2:02:05"), (36000, "10:00:00")],
)
def test_clock_grows_past_an_hour_instead_of_wrapping(seconds, expected):
    """A meeting has no time limit, so the field has to grow. mm:ss wrapping at 60 minutes would
    show 00:00 an hour into a recording."""
    assert _clock(seconds) == expected


def test_an_alarm_from_a_refused_start_clears_itself(app):
    """The red pill from a recording that never began stayed on screen until a restart: releasing
    the key found no session to stop, so nothing dismissed it. See docs/armadilhas.md 9.5."""
    overlay = Overlay(theme.LIGHT)
    overlay.show_dead("o microfone «X» não está conectado", None)
    assert overlay._state is HudState.DEAD

    overlay.dismiss_alarm_after(0)
    app.processEvents()
    time.sleep(0.05)
    app.processEvents()

    assert overlay._state is HudState.HIDDEN


def test_dismissing_the_alarm_never_touches_a_live_recording(app):
    """Called on any other state it must do nothing: the pill belongs to whatever is recording."""
    overlay = Overlay(theme.LIGHT)
    overlay.show_recording()

    overlay.dismiss_alarm_after(0)
    app.processEvents()
    time.sleep(0.05)
    app.processEvents()

    assert overlay._state is HudState.RECORDING
