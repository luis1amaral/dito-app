"""Every bindable key, checked against a live X server.

This exists because the keysym used to be DERIVED from the name by capitalising it, and the rule
is wrong for four of the keys the settings screen offers: space, print_screen, page_up and
page_down resolve to Space, Print_Screen, Page_Up and Page_Down, none of which exist. Choosing one
of them left the app mute — the grab failed to a log nobody reads, and the hold watcher saw the
key as never pressed, so recording ended 0.30 s after it began.

A table can be wrong in the same way. What makes it stay right is asking the X server.
"""

from __future__ import annotations

import os

import pytest

from dito import keys

pytestmark = pytest.mark.x11

pytest.importorskip("Xlib", reason="python-xlib não instalado")

if not os.environ.get("DISPLAY"):
    pytest.skip("sem DISPLAY", allow_module_level=True)

from Xlib import XK, display  # noqa: E402


@pytest.fixture(scope="module")
def dsp():
    d = display.Display()
    yield d
    d.close()


@pytest.mark.parametrize("key", keys.BINDABLE, ids=lambda k: k.name)
def test_every_offered_key_resolves_to_a_real_keycode(key, dsp):
    """An offered key that cannot be grabbed is a trap, not a feature."""
    keysym = XK.string_to_keysym(key.keysym)
    assert keysym, f"{key.name}: keysym «{key.keysym}» não existe"
    assert dsp.keysym_to_keycode(keysym), f"{key.name}: «{key.keysym}» sem keycode neste teclado"


def test_the_naive_capitalise_rule_really_is_wrong(dsp):
    """Guards the reason this module exists, so nobody 'simplifies' it back into a derivation.

    Measured: of the keys whose derived name differs from the real keysym, Page_Up and Page_Down
    happen to be valid X aliases and resolve anyway — space and print_screen do not, and those two
    left the app mute for anyone who picked them."""
    broken = []
    for key in keys.BINDABLE:
        derived = "_".join(part.capitalize() for part in key.name.split("_"))
        keysym = XK.string_to_keysym(derived)
        if not keysym or not dsp.keysym_to_keycode(keysym):
            broken.append(key.name)
    assert set(broken) == {"space", "print_screen"}, (
        f"esperava exatamente space e print_screen quebrados pela derivação, veio {broken}"
    )


def test_names_are_unique_and_lowercase():
    names = [k.name for k in keys.BINDABLE]
    assert len(names) == len(set(names))
    assert all(n == n.lower() for n in names)


def test_qt_names_exist_on_the_qt_enum():
    """The UI resolves these with getattr, so a typo would only show up when someone presses it."""
    qt = pytest.importorskip("PySide6.QtCore", reason="PySide6 não instalado")
    for key in keys.BINDABLE:
        assert hasattr(qt.Qt.Key, key.qt_name), f"{key.name}: Qt.Key.{key.qt_name} não existe"


def test_lookup_helpers_are_case_insensitive_and_safe():
    assert keys.keysym("F9") == "F9"
    assert keys.keysym("space") == "space"
    assert keys.keysym("naoexiste") is None
    assert keys.label("page_up") == "Page Up"
    assert keys.label("naoexiste") == "NAOEXISTE"
    assert keys.is_bindable("f9") and not keys.is_bindable("a")
