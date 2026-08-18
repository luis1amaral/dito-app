"""The Windows notification channel: the tray shows it, and it must not ding.

Dito owns its alarm sound and its switch (docs/armadilhas.md 9.4). On Linux the notification is
sent with `suppress-sound:true`; Qt's showMessage() has no equivalent, so the balloon is sent
straight to the shell with NIIF_NOSOUND instead.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="backend do Windows")

if sys.platform == "win32":
    from dito.platform.windows import notify


def test_the_no_sound_flag_is_actually_set():
    """The whole reason this file talks to Win32: without it every notification dings."""
    assert notify._NIIF_NOSOUND == 0x10


def test_the_tray_window_is_found_by_title_not_by_class():
    """The class name carries the Qt version (Qt6111TrayIconMessageWindowClass) and rots on every
    upgrade; the title has been stable for years."""
    assert notify._TRAY_WINDOW_TITLE == "QTrayIconMessageWindow"
    assert "6" not in notify._TRAY_WINDOW_TITLE


def test_the_struct_is_the_size_the_shell_expects():
    """A wrong cbSize makes Shell_NotifyIcon refuse the call and the notification vanishes."""
    import ctypes

    size = ctypes.sizeof(notify._NOTIFYICONDATAW)
    assert size >= 500, f"NOTIFYICONDATAW pequena demais: {size} bytes"


def test_the_tray_window_is_looked_for_only_inside_this_process():
    """FindWindow varre o desktop inteiro: com o Dito rodando, a suíte mandou um balão de teste
    para a bandeja DELE, na tela do dono. Em produção o mesmo faria o Dito notificar pela bandeja
    de outro app Qt. Ver docs/armadilhas.md 9.9.

    Não dispara balão nenhum: pytest não tem bandeja, então a busca tem que voltar vazia."""
    assert notify._tray_window() is None, (
        "achou uma janela de bandeja fora deste processo — a busca não está isolada"
    )


def test_no_tray_window_means_no_balloon_rather_than_a_crash():
    """Headless, or before the tray is up: the caller falls back to Qt instead of dying."""
    assert notify.balloon("Dito", "corpo", False, 5000) is False


def test_notify_without_a_sink_says_no_instead_of_pretending():
    notify.set_sink(None)
    assert notify.notify("Dito", "ninguém escutando") is False


def test_the_sink_receives_the_urgency_and_the_lifetime():
    seen = []
    notify.set_sink(lambda t, b, u, ms: seen.append((t, b, u, ms)) or True)
    try:
        assert notify.notify("Dito", "corpo", urgent=True) is True
        assert seen[0][2] is True
        assert seen[0][3] == notify.ALARM_MS, "alarme tem que durar mais que um aviso comum"

        notify.notify("Dito", "corpo")
        assert seen[1][3] == notify.NORMAL_MS
    finally:
        notify.set_sink(None)


def test_a_sink_that_raises_never_takes_the_caller_down():
    """A notification failing must not kill the job queue behind it."""
    def boom(*_a):
        raise RuntimeError("bandeja morreu")

    notify.set_sink(boom)
    try:
        assert notify.notify("Dito", "corpo") is False
    finally:
        notify.set_sink(None)
