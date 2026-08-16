"""The visual system. Every colour, gap, radius, size and duration in the UI comes from here.

The rule this file enforces: **no literal hex and no literal px anywhere in a widget.** A value
typed straight into a screen is a value that will disagree with its neighbour six months from
now, and nobody will be able to say which one is right.

Colours are named by ROLE, never by lightness. `surface` is still `surface` in the dark theme,
whereas `grey100` becomes a lie the moment the background goes dark. The proof that the naming is
right is that light and dark cross over with no `if` in any widget — a widget asks for
`palette.surface` and gets the correct answer in both.

Motion uses Apple's two parameters (damping ratio and response) rather than the physics triplet,
because those are the ones you can reason about: damping 1.0 settles without overshoot, and
overshoot is only appropriate when the user's own gesture carried momentum. Nothing in this app
is dragged, so the default is critically damped.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    LIGHT = "light"
    DARK = "dark"


# ---------------------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    mode: Mode

    bg: str
    surface: str
    surface_alt: str
    border: str
    border_strong: str

    text_primary: str
    text_secondary: str
    text_muted: str
    text_inverse: str

    # Each semantic role carries its own hover/active. Deciding the pressed shade once, here, is
    # what stops one button dimming with opacity while its neighbour darkens by 8%.
    primary: str
    primary_hover: str
    primary_active: str

    danger: str
    danger_hover: str
    danger_active: str

    success: str
    alert: str

    overlay_scrim: str
    focus_ring: str

    # The recording pill floats over arbitrary content, so it carries its own surface: on a light
    # desktop a light pill would disappear into a light window behind it.
    hud_surface: str
    hud_text: str
    hud_muted: str
    # The alarm fill is NOT the theme's `danger`. The pill carries its own surface in both themes,
    # and in the dark theme `danger` is a light red on which white text measures 2.77 — unreadable,
    # in the one state the whole product exists for. Fixed here, measured at 5.18 against white.
    hud_danger: str


LIGHT = Palette(
    mode=Mode.LIGHT,
    bg="#f0f0f2",
    surface="#ffffff",
    surface_alt="#e8e8ee",
    border="#dcdce3",
    border_strong="#8f8f9a",
    text_primary="#16161a",
    text_secondary="#43434e",
    text_muted="#6b6b7a",
    text_inverse="#ffffff",
    primary="#4b3bd4",
    primary_hover="#3f31b8",
    primary_active="#342899",
    danger="#c62a30",
    danger_hover="#ab2126",
    danger_active="#8f1a1e",
    success="#1f7a4d",
    alert="#8a5a06",
    overlay_scrim="rgba(0, 0, 0, 0.42)",
    focus_ring="#4b3bd4",
    hud_surface="#17171c",
    hud_text="#f7f7f9",
    hud_muted="#a3a3b2",
    hud_danger="#d02a30",
)

DARK = Palette(
    mode=Mode.DARK,
    bg="#0e0e13",
    surface="#1b1b21",
    surface_alt="#25252e",
    border="#33333e",
    border_strong="#6c6c77",
    text_primary="#f5f5f7",
    text_secondary="#c2c2cd",
    text_muted="#8e8e9d",
    text_inverse="#16161a",
    # Lifted against a dark background: the light-theme indigo reads as near-black here. Same
    # role, different value — which is exactly what the tokens exist to absorb.
    primary="#8b7cff",
    primary_hover="#9c90ff",
    primary_active="#7e6ef4",
    danger="#ff6b6f",
    danger_hover="#ff8285",
    danger_active="#e85054",
    success="#4ecf8f",
    alert="#f0b95c",
    overlay_scrim="rgba(0, 0, 0, 0.6)",
    focus_ring="#8b7cff",
    hud_surface="#17171c",
    hud_text="#f7f7f9",
    hud_muted="#a3a3b2",
    hud_danger="#d02a30",
)


def palette(mode: Mode | str) -> Palette:
    return DARK if Mode(mode) is Mode.DARK else LIGHT


def resolve_mode(setting: str) -> Mode:
    """`auto` follows the desktop. Qt 6.5+ reports the system colour scheme; when it cannot say,
    light is the safer default — a dark app on a light desktop is louder than the reverse."""
    if setting == "dark":
        return Mode.DARK
    if setting == "light":
        return Mode.LIGHT
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication

        scheme = QGuiApplication.styleHints().colorScheme()
        return Mode.DARK if scheme == Qt.ColorScheme.Dark else Mode.LIGHT
    except Exception:
        return Mode.LIGHT


# ---------------------------------------------------------------------------------------
# Scales
# ---------------------------------------------------------------------------------------


class Space:
    """Base 8 with a 4 half-step for fine adjustment. Closed on purpose: a scale with forty
    values is not a scale, it is a list of excuses."""

    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    XXL = 24
    XXXL = 32
    HUGE = 48


class Radius:
    """Named by use rather than by number, so the name says where it belongs.

    A child's radius must never exceed its parent's: the correct inner radius is
    `outer - padding`, and equal radii make the child's corner touch the parent's, which produces
    that ugly crescent. PILL is a clamp, not a computed half-height — that way it follows any
    change in control height on its own."""

    CONTROL = 8
    CARD = 12
    OVERLAY = 18
    PILL = 9999


class Type:
    """Four sizes carry a whole app. Hierarchy comes from weight and colour, not from inventing
    a fifth size. Line height moves inversely with size: body copy wants air, a title does not.

    No Inter on this machine (checked with fc-list), so the stack is what actually exists."""

    FAMILY = "Cantarell, 'Noto Sans', 'DejaVu Sans', sans-serif"
    MONO = "'DejaVu Sans Mono', monospace"

    CAPTION = 11
    BODY = 13
    TITLE = 16
    DISPLAY = 22

    REGULAR = 400
    MEDIUM = 500
    SEMIBOLD = 600

    LEADING_TIGHT = 1.15
    LEADING_BODY = 1.5

    # Tracking is size-specific: large text reads too loose as it grows, small text too tight.
    TRACKING_DISPLAY = -0.4     # px
    TRACKING_BODY = 0.0


class Layer:
    """A named map instead of z-index bidding, where someone always wins with one more nine."""

    CONTENT = 0
    CARD = 10
    HEADER = 50
    DROPDOWN = 100
    MODAL = 200
    HUD = 400
    TOAST = 500


class Motion:
    """Apple's damping ratio + response, in seconds.

    Damping 1.0 is critically damped: it settles without overshoot, which is right for anything
    that simply appears. Overshoot belongs only where the user's own gesture carried momentum,
    and nothing here is dragged — so bounce is the exception, not the house style.
    """

    STANDARD_RESPONSE = 0.35
    STANDARD_DAMPING = 1.0

    MOMENTUM_RESPONSE = 0.30
    MOMENTUM_DAMPING = 0.8

    # Feedback has to be immediate on press: the moment lag appears, directness falls off a cliff.
    PRESS_MS = 100
    # A result the user has to read needs time to be read. Measured against reading speed, not
    # taste: "Salvo" at 900 ms is gone before the eye reaches it.
    TOAST_MS = 1800
    ALARM_PULSE_MS = 1000
    SHAKE_MS = 220


class Size:
    """Minimum, never fixed: a fixed height clips the text the moment someone raises the system
    font size."""

    CONTROL_H = 34
    CONTROL_H_LG = 40
    TOUCH_TARGET = 44
    TRAY_ICON = 22
    HUD_H = 52
    HUD_W = 340
    WINDOW_W = 880
    WINDOW_H = 600


# ---------------------------------------------------------------------------------------
# Contrast — a requirement, and the threshold depends on the role
# ---------------------------------------------------------------------------------------


def _channel(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    r, g, b = (int(raw[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


# Per role, with the reason written down, because "4.5 for everything" fails correct decisions:
# a hint with body contrast stops reading as a hint, and a card border is not a control.
CONTRAST_FLOOR = {
    "content": 4.5,      # WCAG AA. Button and chip labels count as content
    "hint": 3.0,         # deliberately below: a hint with body contrast stops looking like a hint
    "control_edge": 3.0,  # WCAG 1.4.11 — things you operate
    "container": 1.1,    # a card against the page is a plane, not a control
}


# ---------------------------------------------------------------------------------------
# Qt stylesheet, generated from the tokens above — never written by hand
# ---------------------------------------------------------------------------------------


def stylesheet(p: Palette) -> str:
    return f"""
* {{
    font-family: {Type.FAMILY};
    font-size: {Type.BODY}px;
    color: {p.text_primary};
}}
QWidget#root, QDialog, QMainWindow {{
    background: {p.bg};
}}
QLabel[role="display"] {{
    font-size: {Type.DISPLAY}px;
    font-weight: {Type.SEMIBOLD};
    letter-spacing: {Type.TRACKING_DISPLAY}px;
    color: {p.text_primary};
}}
QLabel[role="title"] {{
    font-size: {Type.TITLE}px;
    font-weight: {Type.SEMIBOLD};
    color: {p.text_primary};
}}
QLabel[role="secondary"] {{ color: {p.text_secondary}; }}
QLabel[role="hint"] {{
    color: {p.text_muted};
    font-size: {Type.CAPTION}px;
}}
QLabel[role="danger"] {{ color: {p.danger}; font-weight: {Type.MEDIUM}; }}

QFrame[role="card"] {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: {Radius.CARD}px;
}}

QPushButton {{
    min-height: {Size.CONTROL_H}px;
    padding: 0 {Space.LG}px;
    border-radius: {Radius.CONTROL}px;
    border: 1px solid {p.border_strong};
    background: {p.surface};
    color: {p.text_primary};
    font-weight: {Type.MEDIUM};
}}
QPushButton:hover {{ background: {p.surface_alt}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:disabled {{ color: {p.text_muted}; border-color: {p.border}; }}
QPushButton:focus {{ outline: none; border: 2px solid {p.focus_ring}; }}

QPushButton[variant="primary"] {{
    background: {p.primary};
    border: 1px solid {p.primary};
    color: {p.text_inverse};
    font-weight: {Type.SEMIBOLD};
}}
QPushButton[variant="primary"]:hover {{
    background: {p.primary_hover}; border-color: {p.primary_hover};
}}
QPushButton[variant="primary"]:pressed {{
    background: {p.primary_active}; border-color: {p.primary_active};
}}
QPushButton[variant="danger"] {{
    background: {p.danger}; border: 1px solid {p.danger}; color: {p.text_inverse};
}}
QPushButton[variant="danger"]:hover {{
    background: {p.danger_hover}; border-color: {p.danger_hover};
}}
QPushButton[variant="ghost"] {{
    background: transparent; border: 1px solid transparent; color: {p.text_secondary};
}}
QPushButton[variant="ghost"]:hover {{ background: {p.surface_alt}; color: {p.text_primary}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    min-height: {Size.CONTROL_H}px;
    padding: 0 {Space.MD}px;
    border: 1px solid {p.border_strong};
    border-radius: {Radius.CONTROL}px;
    background: {p.surface};
    selection-background-color: {p.primary};
    selection-color: {p.text_inverse};
}}
QPlainTextEdit, QTextEdit {{ padding: {Space.SM}px {Space.MD}px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 2px solid {p.focus_ring};
}}
QLineEdit:disabled, QComboBox:disabled {{ color: {p.text_muted}; background: {p.surface_alt}; }}
QComboBox::drop-down {{ border: none; width: {Space.XXL}px; }}
QComboBox QAbstractItemView {{
    background: {p.surface};
    border: 1px solid {p.border};
    selection-background-color: {p.primary};
    selection-color: {p.text_inverse};
}}

QCheckBox {{ spacing: {Space.SM}px; min-height: {Size.TOUCH_TARGET}px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {p.border_strong};
    border-radius: {Radius.CONTROL // 2}px;
    background: {p.surface};
}}
QCheckBox::indicator:checked {{ background: {p.primary}; border-color: {p.primary}; }}
QCheckBox::indicator:focus {{ border: 2px solid {p.focus_ring}; }}

QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{
    padding: {Space.SM}px {Space.LG}px;
    margin-right: {Space.XS}px;
    border: none;
    border-radius: {Radius.CONTROL}px;
    color: {p.text_secondary};
    font-weight: {Type.MEDIUM};
}}
QTabBar::tab:hover {{ background: {p.surface_alt}; }}
QTabBar::tab:selected {{ background: {p.surface}; color: {p.text_primary}; }}

/* The scroll area's viewport and its inner container do not inherit the window background, so
   without this they paint the palette's default white and show up as bands between cards. */
QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{ background: transparent; width: {Space.MD}px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {p.border_strong};
    border-radius: {Space.XS}px;
    min-height: {Space.XXXL}px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QListWidget {{
    background: transparent; border: none;
}}
QListWidget::item {{
    border-radius: {Radius.CARD}px;
    margin-bottom: {Space.SM}px;
    padding: {Space.MD}px;
}}
QListWidget::item:selected {{ background: {p.surface_alt}; color: {p.text_primary}; }}

QToolTip {{
    background: {p.hud_surface};
    color: {p.hud_text};
    border: none;
    padding: {Space.SM}px {Space.MD}px;
    border-radius: {Radius.CONTROL}px;
}}
"""
