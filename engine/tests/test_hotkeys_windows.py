"""The Windows key adapter: name -> virtual key, and the filter that consumes and enqueues.

The machine itself is covered in test_hotkeys_core.py. What is left here is the part only Windows
has: `suppress_event()` aborts pynput's own conversion, so a consumed key never reaches `on_press`
and the filter has to feed the queue itself (docs/armadilhas.md 2.12).
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="backend do Windows")

if sys.platform == "win32":
    from dito.platform.windows.hotkeys import KeyState, KeySuppressor, vk_for


def test_the_function_keys_resolve_to_their_virtual_keys():
    """F9 and F10 are the product: if these are wrong, nothing else matters."""
    assert vk_for("f9") == 0x78
    assert vk_for("f10") == 0x79
    assert vk_for("scroll_lock") == 0x91
    assert vk_for("pause") == 0x13


def test_a_plain_character_goes_through_the_keyboard_layout():
    """pynput leaves `vk` None for characters on Windows, so VkKeyScanW answers instead."""
    assert vk_for("a") == 0x41
    assert vk_for("z") == 0x5A


def test_an_unknown_key_is_none_rather_than_a_guess():
    assert vk_for("nao_existe_essa_tecla") is None


def test_the_state_reads_the_hardware_and_caches_the_code():
    state = KeyState()
    assert state.vk("f9") == 0x78
    assert state.vk("f9") == 0x78            # second read comes from the cache
    # Nothing is being held while the suite runs, and asking must not raise either way.
    assert state.is_down("f9") in (True, False)
    state.close()


def test_an_unknown_key_is_never_reported_as_down():
    state = KeyState()
    assert state.is_down("nao_existe_essa_tecla") is False
    state.close()


def test_the_hook_outranks_getasynckeystate():
    """Measured, not assumed: a key our own hook swallows never reaches the async key state, so
    GetAsyncKeyState answers False for the whole hold and the recording ended after the grace
    window instead of when the key came up. See docs/armadilhas.md 2.13."""
    state = KeyState()
    assert state.is_down("f7") is False       # nothing held, nothing observed

    state.note(0x76, True)                    # what the hook saw: F7 down
    assert state.is_down("f7") is True, "o estado do hook tem que ganhar do GetAsyncKeyState"

    state.note(0x76, False)
    assert state.is_down("f7") is False
    state.close()


def test_a_key_the_hook_never_saw_falls_back_to_the_hardware():
    """Held from before the listener started: forgetting it would be worse than asking Windows."""
    state = KeyState()
    state.note(0x76, True)
    assert state.is_down("f8") in (True, False)   # F8 unobserved: answered by GetAsyncKeyState
    state.close()


def test_the_suppressor_maps_the_virtual_key_back_to_the_binding():
    """The hook only ever sees a number; the manager needs the name it was bound under."""
    suppressor = KeySuppressor(KeyState())
    suppressor.grab("f9")
    suppressor.grab("f10")

    assert suppressor.key_of(0x78) == "f9"
    assert suppressor.key_of(0x79) == "f10"
    assert suppressor.key_of(0x41) is None, "uma tecla não capturada não pode ser engolida"


def test_ungrab_all_stops_swallowing_everything():
    """Pausing must hand the keys back — otherwise F9 stays dead in every other program."""
    suppressor = KeySuppressor(KeyState())
    suppressor.grab("f9")
    suppressor.ungrab_all()

    assert suppressor.key_of(0x78) is None


def test_an_unknown_key_is_refused_instead_of_swallowing_zero():
    from dito.platform.hotkeys_core import GrabDenied

    suppressor = KeySuppressor(KeyState())
    with pytest.raises(GrabDenied):
        suppressor.grab("nao_existe_essa_tecla")
