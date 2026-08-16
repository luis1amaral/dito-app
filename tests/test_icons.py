"""The tray icons, measured at the size they are actually shown.

The tray icon is the alarm's last line of defence: if the pill is behind a fullscreen window or
on another workspace, a red icon in the panel is all that is left. So the three states have to be
told apart at 22 px — and by SHAPE, because colour alone is not accessible and because a panel
can be light or dark.

"Fraction of painted pixels" was tried first and is a bad proxy: a hollow bubble and a filled
triangle cover almost the same area (0.417 vs 0.421) while looking nothing alike. Comparing the
silhouettes pixel by pixel is the measurement that matches what the eye does.
"""

from __future__ import annotations

import itertools
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="PySide6 não instalado")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dito.ui.icons import ASSETS, TrayState, tray_icon  # noqa: E402
from dito.ui.theme import Size  # noqa: E402

STATES = ("idle", "recording", "alert")
MIN_SILHOUETTE_DIFF = 0.15


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def _silhouette(path: Path, size: int) -> list[bool]:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(str(path)).render(painter)
    painter.end()
    return [
        image.pixelColor(x, y).alpha() > 40
        for y in range(size)
        for x in range(size)
    ]


@pytest.mark.parametrize("state", STATES)
def test_every_tray_state_has_art(state):
    assert (ASSETS / f"tray-{state}.svg").exists()


@pytest.mark.parametrize("state", STATES)
def test_the_icon_actually_paints_something_at_tray_size(app, state):
    """An SVG that renders empty at 22 px is worse than no icon: the panel shows a blank gap and
    the alarm has no fallback at all."""
    painted = sum(_silhouette(ASSETS / f"tray-{state}.svg", Size.TRAY_ICON))
    total = Size.TRAY_ICON**2
    assert 0.05 < painted / total < 0.95, f"{state}: {painted}/{total} pixels"


def test_the_three_states_differ_by_shape_at_tray_size(app):
    """The accessibility guarantee. Someone who cannot distinguish red from grey still has to be
    able to tell 'recording' from 'not hearing you'."""
    shapes = {s: _silhouette(ASSETS / f"tray-{s}.svg", Size.TRAY_ICON) for s in STATES}
    for first, second in itertools.combinations(STATES, 2):
        differing = sum(1 for a, b in zip(shapes[first], shapes[second], strict=True) if a != b)
        ratio = differing / len(shapes[first])
        assert ratio > MIN_SILHOUETTE_DIFF, (
            f"{first} e {second} diferem em só {ratio:.1%} dos pixels a "
            f"{Size.TRAY_ICON}px — a forma precisa distinguir, não só a cor"
        )


def test_loading_never_returns_an_empty_icon(app):
    """A missing asset must degrade to the drawn fallback, never to a blank tray."""
    for state in TrayState:
        assert not tray_icon(state).isNull()
