"""Contrast and scale are requirements, not taste, so they live in a test that runs.

The thresholds are per ROLE. "4.5 for everything" fails correct decisions: a hint rendered with
body contrast stops reading as a hint, and a card edge is not something you operate. Each floor
below carries the reason it exists.
"""

from __future__ import annotations

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
    stylesheet,
)

THEMES = [pytest.param(LIGHT, id="light"), pytest.param(DARK, id="dark")]


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
def test_the_alarm_fill_is_the_same_in_both_themes(p: Palette):
    """The pill floats over arbitrary content, so it cannot inherit the desktop's theme and stay
    legible. Its surface set is theme-independent by design."""
    assert p.hud_danger == LIGHT.hud_danger == DARK.hud_danger
    assert p.hud_surface == LIGHT.hud_surface == DARK.hud_surface


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
def test_stylesheet_contains_no_stray_literals(p: Palette):
    """Every value in the QSS has to have come from a token."""
    css = stylesheet(p)
    known = {
        getattr(p, f) for f in p.__dataclass_fields__ if isinstance(getattr(p, f), str)
    }
    used = set()
    for chunk in css.replace(";", " ").replace(":", " ").split():
        if chunk.startswith("#") and len(chunk) in (4, 7):
            used.add(chunk)
    unknown = used - known
    assert not unknown, f"hex escrito à mão no QSS: {sorted(unknown)}"
