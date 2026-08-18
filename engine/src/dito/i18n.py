"""Translation. Source strings are English; catalogues live in `locales/`."""

from __future__ import annotations

import gettext as _gettext
import locale
import os
from pathlib import Path

DOMAIN = "dito"
LOCALES = Path(__file__).resolve().parent / "locales"

AUTO = "auto"
DEFAULT = "en"
# Anything shipped in locales/ is offered; the label is what the settings screen shows.
LANGUAGES: dict[str, str] = {
    AUTO: "Seguir o sistema",
    "en": "English",
    "pt_BR": "Português (Brasil)",
}

_active: _gettext.NullTranslations = _gettext.NullTranslations()
_current = DEFAULT


def system_language() -> str:
    """Best guess from the environment, normalised to a catalogue name."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        raw = os.environ.get(var, "").strip()
        if raw and raw not in ("C", "POSIX"):
            return normalise(raw)
    try:
        code, _enc = locale.getdefaultlocale()
    except (ValueError, TypeError):
        code = None
    return normalise(code or DEFAULT)


def normalise(code: str) -> str:
    code = code.split(".")[0].split("@")[0].replace("-", "_")
    if code in LANGUAGES:
        return code
    lang = code.split("_")[0]
    # pt, pt_PT and anything else Portuguese land on the one Portuguese catalogue we ship.
    for known in LANGUAGES:
        if known != AUTO and known.split("_")[0] == lang:
            return known
    return DEFAULT


def available() -> list[str]:
    found = [AUTO, DEFAULT]
    if LOCALES.is_dir():
        found += sorted(
            d.name for d in LOCALES.iterdir()
            if d.is_dir() and d.name != DEFAULT and (d / "LC_MESSAGES" / f"{DOMAIN}.mo").exists()
        )
    return found


def setup(language: str = AUTO) -> str:
    """Install the catalogue and return the language actually in use."""
    global _active, _current
    wanted = system_language() if language in (AUTO, "", None) else normalise(language)
    try:
        _active = _gettext.translation(
            DOMAIN, localedir=str(LOCALES), languages=[wanted], fallback=True
        )
    except OSError:
        _active = _gettext.NullTranslations()
    _current = wanted
    return wanted


def current() -> str:
    return _current


def _(message: str) -> str:
    """Mark and translate. Untranslated strings fall through as their English source."""
    return _active.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _active.ngettext(singular, plural, n)
