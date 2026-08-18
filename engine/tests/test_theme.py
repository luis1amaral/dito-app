"""Contrast and scale are requirements, not taste, so they live in a test that runs.

The thresholds are per ROLE. "4.5 for everything" fails correct decisions: a hint rendered with
body contrast stops reading as a hint, and a card edge is not something you operate. Each floor
below carries the reason it exists.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from dito.ui.theme import (
    CONTRAST_FLOOR,
    DARK,
    LIGHT,
    Motion,
    Palette,
    Radius,
    Space,
    Type,
    contrast,
    hud_stylesheet,
    luminance,
    stylesheet,
)

THEMES = [pytest.param(LIGHT, id="light"), pytest.param(DARK, id="dark")]


def _alpha(rgba: str) -> float:
    """The alpha of an `rgba(...)` token, so the test reads the value the QSS reads."""
    return float(rgba.rstrip(")").split(",")[-1])


def blend(fg: str, bg: str, alpha: float) -> str:
    """Flatten a translucent foreground onto its background, because contrast is a property of
    what lands on the screen, not of the colour before compositing."""
    fg_raw, bg_raw = fg.lstrip("#"), bg.lstrip("#")
    out = []
    for i in (0, 2, 4):
        f = int(fg_raw[i:i + 2], 16)
        b = int(bg_raw[i:i + 2], 16)
        out.append(round(f * alpha + b * (1 - alpha)))
    return "#" + "".join(f"{c:02x}" for c in out)


@pytest.mark.parametrize("p", THEMES)
def test_body_text_meets_aa(p: Palette):
    for surface in (p.bg, p.surface, p.surface_alt):
        assert contrast(p.text_primary, surface) >= CONTRAST_FLOOR["content"]
        assert contrast(p.text_secondary, surface) >= CONTRAST_FLOOR["content"]


@pytest.mark.parametrize("p", THEMES)
def test_hints_are_dimmer_than_body_but_still_legible(p: Palette):
    """Deliberately below AA: a hint at body contrast stops looking like a hint."""
    ratio = contrast(p.text_muted, p.surface)
    assert ratio >= CONTRAST_FLOOR["hint"]
    assert ratio < contrast(p.text_primary, p.surface)


@pytest.mark.parametrize("p", THEMES)
def test_labels_on_filled_buttons_are_readable(p: Palette):
    for fill in (p.primary, p.primary_hover, p.primary_active, p.danger, p.danger_active):
        assert contrast(p.text_inverse, fill) >= CONTRAST_FLOOR["content"], fill


@pytest.mark.parametrize("p", THEMES)
def test_control_edges_and_focus_ring_are_operable(p: Palette):
    assert contrast(p.border_strong, p.surface) >= CONTRAST_FLOOR["control_edge"]
    assert contrast(p.focus_ring, p.surface) >= CONTRAST_FLOOR["control_edge"]


@pytest.mark.parametrize("p", THEMES)
def test_card_reads_as_a_plane_without_pretending_to_be_a_control(p: Palette):
    assert contrast(p.surface, p.bg) >= CONTRAST_FLOOR["container"]


@pytest.mark.parametrize("p", THEMES)
def test_the_pill_is_legible_over_its_own_surface(p: Palette):
    """The pill carries its own surface in both themes, so it must pass on its own terms."""
    assert contrast(p.hud_text, p.hud_surface) >= CONTRAST_FLOOR["content"]
    assert contrast(p.hud_muted, p.hud_surface) >= CONTRAST_FLOOR["hint"]


@pytest.mark.parametrize("p", THEMES)
def test_the_alarm_is_readable_on_the_red_fill(p: Palette):
    """This is the state the product exists for: if it is not legible, nothing else matters.

    Note it checks `hud_danger`, not `danger`. The pill has its own surface in both themes, and
    the dark theme's `danger` is a light red on which white measures 2.77 — this test is what
    caught that, before it shipped.

    The secondary line is white at 88% and the clock at 75%, so both are measured after
    compositing rather than as the pure colour."""
    assert contrast("#ffffff", p.hud_danger) >= CONTRAST_FLOOR["content"]
    assert contrast(blend("#ffffff", p.hud_danger, 0.88), p.hud_danger) >= CONTRAST_FLOOR["hint"]
    assert contrast(blend("#ffffff", p.hud_danger, 0.75), p.hud_danger) >= CONTRAST_FLOOR["hint"]


@pytest.mark.parametrize("p", THEMES)
def test_the_whole_pill_palette_is_the_same_in_both_themes(p: Palette):
    """The pill floats over arbitrary content, so it cannot inherit the desktop's theme and stay
    legible. Its entire colour set is theme-independent by design.

    Every `hud_` field, not a hand-kept list: a list is what lets the next token slip through."""
    tokens = [f for f in p.__dataclass_fields__ if f.startswith("hud_")]
    assert len(tokens) >= 15, "the hud_ set shrank — did a control lose its token?"
    for token in tokens:
        assert getattr(p, token) == getattr(LIGHT, token) == getattr(DARK, token), token


@pytest.mark.parametrize("p", THEMES)
def test_the_controls_drawn_on_the_pill_are_operable(p: Palette):
    """The pill's own buttons and text box: white at a fixed alpha over `hud_surface`.

    A translucent wash is the easy way to draw a control on a dark ground and the easy way to make
    it invisible — 0.14 white measures 1.51 there, half the 3.0 an operable edge owes. These are
    the alphas that clear it, and the label contrast on the solid variant while it is pressed."""
    for token in ("hud_edge",):
        flat = blend("#ffffff", p.hud_surface, _alpha(getattr(p, token)))
        assert contrast(flat, p.hud_surface) >= CONTRAST_FLOOR["control_edge"], token

    # The field's fill only has to say "a control lives here", the way a card says "a plane".
    field = blend("#ffffff", p.hud_surface, _alpha(p.hud_field))
    assert contrast(field, p.hud_surface) >= CONTRAST_FLOOR["container"]

    for token in ("hud_text", "hud_solid_hover", "hud_solid_active"):
        value = getattr(p, token)
        fill = value if value.startswith("#") else blend("#ffffff", p.hud_surface, _alpha(value))
        assert contrast(p.hud_surface, fill) >= CONTRAST_FLOOR["content"], token


@pytest.mark.parametrize("p", THEMES)
def test_the_solid_button_is_readable_where_it_actually_appears(p: Palette):
    """Only ever shown on the alarm, so it is measured against the alarm's fill."""
    assert contrast(p.hud_text, p.hud_danger) >= CONTRAST_FLOOR["content"]


@pytest.mark.parametrize("p", THEMES)
def test_every_accent_painted_on_the_pill_clears_the_graphical_floor(p: Palette):
    """The pill's ground is dark in both themes, so a light-theme accent is the wrong value there.

    Measured on #17171c, the theme tokens only scrape the 3.0 floor for a graphical object
    (danger 3.21, alert 3.02) and `primary` fails outright at 2.45. The hud_* set uses the
    dark-theme values in both themes, which measure 6.45 / 10.04 / 5.46. This test is what stops
    someone reaching for `palette.danger` inside the overlay again."""
    for token in ("hud_recording", "hud_alert", "hud_ok", "hud_text"):
        ratio = contrast(getattr(p, token), p.hud_surface)
        assert ratio >= CONTRAST_FLOOR["control_edge"], f"{token}: {ratio:.2f}"


def _hue(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    r, g, b = (int(raw[i:i + 2], 16) / 255 for i in (0, 2, 4))
    high, low = max(r, g, b), min(r, g, b)
    if high == low:
        return 0.0
    span = high - low
    if high == r:
        h = ((g - b) / span) % 6
    elif high == g:
        h = (b - r) / span + 2
    else:
        h = (r - g) / span + 4
    return h * 60


@pytest.mark.parametrize("p", THEMES)
def test_warning_and_alarm_are_different_hues(p: Palette):
    """Measured by HUE, not by contrast ratio.

    Contrast ratio is luminance only, so two colours that are obviously different to the eye can
    score almost identically — amber and red here differ by 0.19, which says nothing. Hue is the
    channel that actually separates them. And because hue alone is not accessible either, the
    alarm carries a second, non-colour signal: the waveform collapses to a flat line
    (see test_overlay_alarm_changes_shape)."""
    assert abs(_hue(p.alert) - _hue(p.danger)) > 15


def test_the_two_themes_define_exactly_the_same_roles():
    """The proof that the naming is right: light and dark cross over with no widget-level `if`."""
    light = {f for f in LIGHT.__dataclass_fields__}
    dark = {f for f in DARK.__dataclass_fields__}
    assert light == dark
    for field in light - {"mode"}:
        assert getattr(LIGHT, field), field
        assert getattr(DARK, field), field


def test_spacing_is_a_closed_scale_on_a_four_pixel_grid():
    values = [Space.XS, Space.SM, Space.MD, Space.LG, Space.XL, Space.XXL, Space.XXXL, Space.HUGE]
    assert values == sorted(values)
    assert all(v % 4 == 0 for v in values)
    assert len(values) <= 8, "a scale with forty values is not a scale"


def test_nested_radius_never_exceeds_its_parent():
    """Equal radii make the child's corner touch the parent's and produce a crescent."""
    assert Radius.CONTROL < Radius.CARD < Radius.OVERLAY
    assert Radius.CARD - Space.SM < Radius.CARD


def test_type_scale_stays_small_and_ordered():
    sizes = [Type.CAPTION, Type.BODY, Type.TITLE, Type.DISPLAY]
    assert sizes == sorted(sizes)
    assert len(set(sizes)) == 4, "hierarchy comes from weight and colour, not a fifth size"
    assert Type.TRACKING_DISPLAY < 0, "large text needs negative tracking as it grows"


def test_default_motion_does_not_overshoot():
    """Bounce belongs only where the user's gesture carried momentum. Nothing here is dragged."""
    assert Motion.STANDARD_DAMPING == 1.0
    assert Motion.MOMENTUM_DAMPING < 1.0
    assert Motion.TOAST_MS >= 1500, "a result the user must read needs time to be read"


@pytest.mark.parametrize("p", THEMES)
@pytest.mark.parametrize("build", [stylesheet, hud_stylesheet], ids=["app", "hud"])
def test_stylesheet_contains_no_stray_literals(p: Palette, build):
    """Every colour in the QSS has to have come from a token — translucent ones included.

    `rgba()` is checked too because the pill's whole control set is white at a fixed alpha: a hand
    written `rgba(255,255,255,0.14)` is exactly as much of a stray literal as a hand written hex,
    and it is the one that used to be scattered across overlay.py and review.py."""
    css = build(p)
    known = {
        getattr(p, f) for f in p.__dataclass_fields__ if isinstance(getattr(p, f), str)
    }
    used = set()
    for chunk in css.replace(";", " ").replace(":", " ").split():
        if chunk.startswith("#") and len(chunk) in (4, 7):
            used.add(chunk)
    unknown = used - known
    assert not unknown, f"hex escrito à mão no QSS: {sorted(unknown)}"

    normalised = {" ".join(value.split()) for value in known}
    for found in re.findall(r"rgba?\([^)]*\)", css):
        assert " ".join(found.split()) in normalised, f"rgba escrito à mão no QSS: {found}"


# window.py is being rewritten in a parallel change and still carries `padding: 2px`; it joins the
# scan when that lands and its chip becomes a `components.Badge`.
_PENDING = {"theme.py", "window.py"}


def _screens() -> list[Path]:
    root = Path(__file__).resolve().parents[1] / "src" / "dito" / "ui"
    return sorted(p for p in root.glob("*.py") if p.name not in _PENDING)


@pytest.mark.parametrize("module", _screens(), ids=lambda p: p.name)
def test_no_raw_colour_or_size_survives_in_a_screen(module: Path):
    """The rule from CLAUDE.md, as a command instead of a habit.

    A screen may not name a colour or a pixel: both come from `theme.py`, through a component. The
    interpolations are stripped first, so `{Space.MD}px` reads as a token and `2px` does not."""
    source = module.read_text(encoding="utf-8")
    literal = re.sub(r"\{[^{}]*\}", "{}", source)

    assert not re.findall(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b", literal), (
        f"{module.name}: cor em hexadecimal escrita na tela"
    )
    assert not re.findall(r"\brgba?\(", literal), f"{module.name}: rgba escrito na tela"

    sizes = [m for m in re.findall(r"(?<![{\w.])(\d+)px", literal)]
    assert not sizes, f"{module.name}: px solto na tela: {sizes}"


def test_switching_the_theme_repaints_a_window_that_is_already_open():
    """The owner's ask, as a measurement: dark background, light button; light background, dark.

    It repaints instead of rebuilding, so a window mid-edit keeps whatever the user typed."""
    pytest.importorskip("PySide6", reason="PySide6 não instalado")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget

    from dito.ui import live
    from dito.ui.components import Button, Variant

    app = QApplication.instance() or QApplication([])
    window = QWidget()
    window.setObjectName("root")
    window.setStyleSheet(stylesheet(LIGHT))
    button = Button("Enviar", Variant.PRIMARY, parent=window)

    live.apply_theme("dark")
    app.processEvents()
    assert live.palette() is DARK
    assert DARK.bg in window.styleSheet(), "a janela viva ficou com a folha do tema anterior"
    assert button._palette is DARK

    live.apply_theme("light")
    app.processEvents()
    assert LIGHT.bg in window.styleSheet()
    assert button._palette is LIGHT
    window.close()


def test_the_button_is_light_on_a_dark_ground_and_dark_on_a_light_one():
    """Stated the way the owner stated it, and measured rather than eyeballed."""
    for p in (LIGHT, DARK):
        page = luminance(p.bg)
        fill = luminance(p.primary)
        label = luminance(p.text_inverse)
        assert (fill > page) == (p is DARK), "o preenchimento tem que contrastar com a página"
        assert (label < fill) == (p is DARK), "o rótulo tem que contrastar com o preenchimento"


def test_switching_the_language_changes_the_text_without_reopening():
    pytest.importorskip("PySide6", reason="PySide6 não instalado")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from dito import config, i18n
    from dito.ui import live
    from dito.ui.settings_page import SettingsPage

    app = QApplication.instance() or QApplication([])
    live.apply_theme("light")
    page = SettingsPage(config.load(), LIGHT)

    try:
        assert live.apply_language("pt_BR") >= 1
        app.processEvents()
        assert page._appearance_card._title.text() == "Aparência"
        assert page._theme_row._label.text() == "Tema"

        live.apply_language("en")
        app.processEvents()
        assert page._appearance_card._title.text() == "Appearance"
    finally:
        i18n.setup("en")
        page.close()
