"""The visual system: every colour, gap, radius, size and duration in the UI comes from here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    LIGHT = "light"
    DARK = "dark"


# ---- Colour --------------------------------------------------------------------------


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

    # Each role carries its own hover/active, decided once here so no two controls press alike.
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

    # The pill floats over arbitrary content, so it carries its own surface, dark in both themes.
    hud_surface: str
    hud_text: str
    hud_muted: str
    # See docs/armadilhas.md 7.3: a theme token on the pill's dark ground is the wrong value.
    hud_danger: str
    hud_recording: str
    hud_alert: str
    hud_ok: str

    # Controls drawn ON the pill: white at a fixed alpha, because the ground below them varies.
    hud_wash: str
    hud_wash_strong: str
    hud_edge: str
    hud_field: str
    hud_solid_hover: str
    hud_solid_active: str
    hud_on_danger: str
    hud_on_danger_muted: str


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
    hud_recording="#ff6b6f",
    hud_alert="#f0b95c",
    hud_ok="#4ecf8f",
    hud_wash="rgba(255, 255, 255, 0.10)",
    hud_wash_strong="rgba(255, 255, 255, 0.18)",
    hud_edge="rgba(255, 255, 255, 0.35)",
    hud_field="rgba(255, 255, 255, 0.06)",
    hud_solid_hover="rgba(255, 255, 255, 0.86)",
    hud_solid_active="rgba(255, 255, 255, 0.74)",
    hud_on_danger="rgba(255, 255, 255, 0.88)",
    hud_on_danger_muted="rgba(255, 255, 255, 0.75)",
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
    # Lifted: the light theme's indigo reads as near-black here. Same role, different value.
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
    hud_recording="#ff6b6f",
    hud_alert="#f0b95c",
    hud_ok="#4ecf8f",
    hud_wash="rgba(255, 255, 255, 0.10)",
    hud_wash_strong="rgba(255, 255, 255, 0.18)",
    hud_edge="rgba(255, 255, 255, 0.35)",
    hud_field="rgba(255, 255, 255, 0.06)",
    hud_solid_hover="rgba(255, 255, 255, 0.86)",
    hud_solid_active="rgba(255, 255, 255, 0.74)",
    hud_on_danger="rgba(255, 255, 255, 0.88)",
    hud_on_danger_muted="rgba(255, 255, 255, 0.75)",
)


def palette(mode: Mode | str) -> Palette:
    return DARK if Mode(mode) is Mode.DARK else LIGHT


def resolve_mode(setting: str) -> Mode:
    """`auto` asks Qt for the desktop's scheme; light when it cannot say, the quieter mistake."""
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


# ---- Scales --------------------------------------------------------------------------


class Space:
    """Base 8 with a 4 half-step, closed on purpose: forty values would not be a scale."""

    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    XXL = 24
    XXXL = 32
    HUGE = 48


class Radius:
    """Named by use; a child's radius is `outer - padding`. See docs/armadilhas.md 7.4."""

    CONTROL = 8
    CARD = 12
    OVERLAY = 18
    PILL = 9999      # a clamp, not a computed half-height, so it follows the control's height


class Type:
    """Four sizes; hierarchy comes from weight and colour. Stack measured in docs/marca.md 6."""

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
    """Apple's damping ratio + response, in seconds. See docs/armadilhas.md 7.8."""

    STANDARD_RESPONSE = 0.35
    STANDARD_DAMPING = 1.0

    MOMENTUM_RESPONSE = 0.30
    MOMENTUM_DAMPING = 0.8

    # A 20 px knob at the window's response reads as sluggish: travel is short, so time must be.
    CONTROL_RESPONSE = 0.22
    SPINNER_MS = 1000

    # Feedback has to be immediate on press: the moment lag appears, directness falls off a cliff.
    PRESS_MS = 100
    # Measured against reading speed, not taste: "Salvo" at 900 ms is gone before the eye lands.
    TOAST_MS = 1800
    ALARM_PULSE_MS = 1000
    SHAKE_MS = 220


class Size:
    """Minimum, never fixed: a fixed height clips the text at a larger system font size."""

    CONTROL_H_SM = 28
    CONTROL_H = 34
    CONTROL_H_LG = 40
    TOUCH_TARGET = 44
    TRAY_ICON = 22
    HUD_H = 52
    HUD_W = 340
    WINDOW_W = 880
    WINDOW_H = 600
    # A exceção da regra acima, e por um motivo medido: um QLabel com quebra de linha não tem
    # largura preferida, então a janela de preparo saía com 922 px. Aqui a largura é o que MANDA
    # o texto quebrar — a altura continua livre.
    DIALOG_W = 460

    # Painted controls: the geometry is the drawing, so it cannot come from a padding rule.
    SWITCH_W = 44
    SWITCH_H = 24
    SWITCH_KNOB = 18
    SWITCH_KNOB_PRESSED = 22
    SPINNER = 16
    CHEVRON = 10
    # A number needs a number's worth of width; a full-card spin box reads as an empty field.
    FIELD_W_SM = 140
    FOCUS_RING = 2
    HAIRLINE = 1


class Alpha:
    """Opacity is a token too, or the same wash gets re-invented at three different strengths."""

    FOCUS_RING = 0.5
    SPINNER_TRACK = 0.25
    # Near-opaque, not frosted: there is no reliable backdrop blur here and fake frost reads dirty.
    HUD_SURFACE = 0.96
    REVIEW_SURFACE = 0.97


# ---- Contrast: a requirement, and the threshold depends on the role --------------------


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


# Per role: "4.5 for everything" fails correct decisions. Measured pairs in docs/marca.md 5.
CONTRAST_FLOOR = {
    "content": 4.5,      # WCAG AA. Button and chip labels count as content
    "hint": 3.0,         # deliberately below: a hint with body contrast stops looking like a hint
    "control_edge": 3.0,  # WCAG 1.4.11 — things you operate
    "container": 1.1,    # a card against the page is a plane, not a control
}


# ---- Qt stylesheet, generated from the tokens above — never written by hand ------------


# A live window is re-themed by swapping the sheet that carries its marker — see ui/live.py.
APP_MARKER = "/* dito-theme:app */"
HUD_MARKER = "/* dito-theme:hud */"


def stylesheet(p: Palette) -> str:
    """The app's whole look. Every component in ui/components.py styles itself from here."""
    return f"""{APP_MARKER}
* {{
    font-family: {Type.FAMILY};
    font-size: {Type.BODY}px;
    color: {p.text_primary};
}}
QWidget#root, QDialog, QMainWindow {{
    background: {p.bg};
}}

/* ---- text roles: four sizes, hierarchy from weight and colour ---- */
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
/* The label is quieter than the value it names — the MarkUp signature. Still AA on surface. */
QLabel[role="label"] {{ font-weight: {Type.MEDIUM}; color: {p.text_secondary}; }}
QLabel[role="secondary"] {{ color: {p.text_secondary}; }}
QLabel[role="hint"] {{
    color: {p.text_muted};
    font-size: {Type.CAPTION}px;
}}
QLabel[role="danger"] {{
    color: {p.danger};
    font-size: {Type.CAPTION}px;
    font-weight: {Type.MEDIUM};
}}
QLabel[role="mono"] {{
    font-family: {Type.MONO};
    font-size: {Type.CAPTION}px;
    color: {p.text_muted};
}}

/* ---- containers ---- */
QFrame[role="card"] {{
    background: {p.surface};
    border: {Size.HAIRLINE}px solid {p.border};
    border-radius: {Radius.CARD}px;
}}
QFrame[role="divider"] {{
    background: {p.border};
    border: none;
    max-height: {Size.HAIRLINE}px;
    min-height: {Size.HAIRLINE}px;
}}

/* ---- badge: neutral is a grey step, every status is its role colour filled ---- */
QLabel[role="badge"] {{
    padding: {Space.XS}px {Space.SM}px;
    border-radius: {Radius.CONTROL}px;
    background: {p.surface_alt};
    color: {p.text_secondary};
    font-size: {Type.CAPTION}px;
    font-weight: {Type.MEDIUM};
}}
QLabel[role="badge"][tone="primary"] {{ background: {p.primary}; color: {p.text_inverse}; }}
QLabel[role="badge"][tone="success"] {{ background: {p.success}; color: {p.text_inverse}; }}
QLabel[role="badge"][tone="alert"] {{ background: {p.alert}; color: {p.text_inverse}; }}
QLabel[role="badge"][tone="danger"] {{ background: {p.danger}; color: {p.text_inverse}; }}

/* ---- button: size sets geometry, variant sets colour, so the two never fight ---- */
QPushButton {{
    min-height: {Size.CONTROL_H}px;
    padding: 0 {Space.LG}px;
    border-radius: {Radius.CONTROL}px;
    border: {Size.HAIRLINE}px solid {p.border_strong};
    background: {p.surface};
    color: {p.text_primary};
    font-weight: {Type.MEDIUM};
}}
QPushButton[size="sm"] {{ min-height: {Size.CONTROL_H_SM}px; padding: 0 {Space.MD}px; }}
QPushButton[size="lg"] {{ min-height: {Size.CONTROL_H_LG}px; padding: 0 {Space.XL}px; }}
/* Hover on an outlined control darkens the EDGE one step; filling is the ghost/list idiom. */
QPushButton:hover {{ border-color: {p.text_muted}; }}
QPushButton:pressed {{ border-color: {p.text_primary}; background: {p.surface_alt}; }}
/* The focus ring is painted, not styled: a border that grows on focus moves the layout by 1px. */
QPushButton:focus {{ outline: none; border-color: {p.focus_ring}; }}
QPushButton:disabled {{
    background: {p.surface_alt}; color: {p.text_muted}; border-color: {p.border};
}}

QPushButton[variant="primary"] {{
    background: {p.primary};
    border-color: {p.primary};
    color: {p.text_inverse};
    font-weight: {Type.SEMIBOLD};
}}
QPushButton[variant="primary"]:hover {{
    background: {p.primary_hover}; border-color: {p.primary_hover};
}}
QPushButton[variant="primary"]:pressed {{
    background: {p.primary_active}; border-color: {p.primary_active};
}}
QPushButton[variant="primary"]:focus {{ border-color: {p.focus_ring}; }}
QPushButton[variant="primary"]:disabled {{
    background: {p.surface_alt}; color: {p.text_muted}; border-color: {p.border};
}}

QPushButton[variant="danger"] {{
    background: {p.danger};
    border-color: {p.danger};
    color: {p.text_inverse};
    font-weight: {Type.SEMIBOLD};
}}
QPushButton[variant="danger"]:hover {{
    background: {p.danger_hover}; border-color: {p.danger_hover};
}}
QPushButton[variant="danger"]:pressed {{
    background: {p.danger_active}; border-color: {p.danger_active};
}}
QPushButton[variant="danger"]:disabled {{
    background: {p.surface_alt}; color: {p.text_muted}; border-color: {p.border};
}}

QPushButton[variant="ghost"] {{
    background: transparent; border-color: transparent; color: {p.text_secondary};
}}
QPushButton[variant="ghost"]:hover {{ background: {p.surface_alt}; color: {p.text_primary}; }}
QPushButton[variant="ghost"]:pressed {{ background: {p.border}; }}
QPushButton[variant="ghost"]:disabled {{ background: transparent; border-color: transparent; }}

/* A key name is a value, not prose, and the recorder is the button's seventh state. */
QPushButton[mono="true"] {{ font-family: {Type.MONO}; }}
QPushButton[capturing="true"] {{
    border-color: {p.primary}; color: {p.primary}; font-weight: {Type.SEMIBOLD};
}}

/* ---- field, select, spin ---- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    min-height: {Size.CONTROL_H}px;
    padding: 0 {Space.MD}px;
    border: {Size.HAIRLINE}px solid {p.border_strong};
    border-radius: {Radius.CONTROL}px;
    background: {p.surface};
    color: {p.text_primary};
    selection-background-color: {p.primary};
    selection-color: {p.text_inverse};
}}
QPlainTextEdit, QTextEdit {{ padding: {Space.SM}px {Space.MD}px; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {p.text_muted};
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ background: {p.surface_alt}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    outline: none; border-color: {p.focus_ring};
}}
QLineEdit[invalid="true"], QComboBox[invalid="true"], QPlainTextEdit[invalid="true"] {{
    border-color: {p.danger};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {p.text_muted}; background: {p.surface_alt}; border-color: {p.border};
}}
QComboBox::drop-down {{ border: none; width: {Space.XXL}px; }}
/* Qt's own arrow is a bitmap that ignores the theme; ui/components.py paints the chevron. */
QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
QComboBox QAbstractItemView {{
    background: {p.surface};
    border: {Size.HAIRLINE}px solid {p.border};
    border-radius: {Radius.CONTROL}px;
    padding: {Space.XS}px;
    outline: none;
    selection-background-color: {p.primary};
    selection-color: {p.text_inverse};
}}
QComboBox QAbstractItemView::item {{
    min-height: {Size.CONTROL_H_SM}px;
    padding: 0 {Space.SM}px;
    border-radius: {Radius.CONTROL - Space.XS}px;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: {Space.LG}px; border: none; background: transparent;
}}

/* ---- tabs ---- */
/* The pane has no border to separate it, so the gap has to be spacing or the content sits glued. */
QTabWidget::pane {{ border: none; background: transparent; padding-top: {Space.LG}px; }}
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

/* See docs/armadilhas.md 7.6: the scroll area paints white bands between cards without this. */
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


def hud_stylesheet(p: Palette) -> str:
    """The pill and the review card: same anatomy, the `hud_*` set instead of the theme's.

    It is a widget-level sheet on purpose. See docs/armadilhas.md 7.6: a local sheet REPLACES the
    app's for that subtree, so the scrollbar rules have to be repeated here or Qt draws its arrows.
    """
    return f"""{HUD_MARKER}
* {{
    font-family: {Type.FAMILY};
    font-size: {Type.BODY}px;
    color: {p.hud_text};
}}
QLabel[role="hud-title"] {{ font-weight: {Type.SEMIBOLD}; color: {p.hud_text}; }}
QLabel[role="hud-hint"] {{ font-size: {Type.CAPTION}px; color: {p.hud_muted}; }}
QLabel[role="hud-clock"] {{ font-family: {Type.MONO}; color: {p.hud_muted}; }}

QPushButton {{
    min-height: {Size.CONTROL_H}px;
    padding: 0 {Space.LG}px;
    border-radius: {Radius.CONTROL}px;
    border: {Size.HAIRLINE}px solid transparent;
    font-weight: {Type.MEDIUM};
}}
QPushButton[size="sm"] {{ min-height: {Size.CONTROL_H_SM}px; padding: 0 {Space.MD}px; }}
QPushButton[variant="hud-solid"] {{
    background: {p.hud_text}; color: {p.hud_surface}; font-weight: {Type.SEMIBOLD};
}}
QPushButton[variant="hud-solid"]:hover {{ background: {p.hud_solid_hover}; }}
QPushButton[variant="hud-solid"]:pressed {{ background: {p.hud_solid_active}; }}
QPushButton[variant="hud-outline"] {{
    background: transparent; color: {p.hud_text}; border-color: {p.hud_edge};
}}
QPushButton[variant="hud-outline"]:hover {{ background: {p.hud_wash}; }}
QPushButton[variant="hud-outline"]:pressed {{ background: {p.hud_wash_strong}; }}
QPushButton:disabled {{ color: {p.hud_muted}; background: {p.hud_wash}; }}

QPlainTextEdit {{
    background: {p.hud_field};
    color: {p.hud_text};
    border: {Size.HAIRLINE}px solid {p.hud_edge};
    border-radius: {Radius.CONTROL}px;
    padding: {Space.SM}px {Space.MD}px;
    selection-background-color: {p.hud_text};
    selection-color: {p.hud_surface};
}}
QPlainTextEdit:focus {{ outline: none; border-color: {p.hud_text}; }}

QScrollBar:vertical {{ background: transparent; width: {Space.SM}px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {p.hud_edge};
    border-radius: {Space.XS}px;
    min-height: {Space.XXL}px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
