"""What the notification promises, and what it must never do.

Two defects live here, both about a notification that outstays its welcome. `--urgency critical`
never expires by freedesktop spec (9.6), and the desktop's own sound on top of Dito's alarm is
noise the owner cannot switch off from inside the app (9.8).
"""

from __future__ import annotations

from dito.platform.linux_x11 import notify


def _args(monkeypatch, **kwargs) -> list[str]:
    captured: list[list[str]] = []
    monkeypatch.setattr(notify.shutil, "which", lambda _n: "/usr/bin/notify-send")
    monkeypatch.setattr(notify, "_run", lambda a: captured.append(a) or True)
    notify.notify("titulo", "corpo", **kwargs)
    return captured[0]


def test_a_notification_always_carries_a_lifetime(monkeypatch):
    """`critical` never expires, so it is never used — armadilhas 9.6."""
    normal = _args(monkeypatch)
    alarme = _args(monkeypatch, urgent=True)

    assert "critical" not in normal and "critical" not in alarme
    assert "--expire-time" in normal and "--expire-time" in alarme
    assert int(alarme[alarme.index("--expire-time") + 1]) > int(
        normal[normal.index("--expire-time") + 1]
    ), "o alarme tem que durar mais que um aviso comum"


def test_the_desktop_ding_is_suppressed(monkeypatch):
    """Dito owns its alarm sound, with its own switch. The environment's generic ding on top is
    noise nobody asked for, and it fires even when Dito's own sound is off — armadilhas 9.8."""
    args = _args(monkeypatch, urgent=True)

    assert "--hint" in args
    assert args[args.index("--hint") + 1] == "boolean:suppress-sound:true"


def test_without_notify_send_it_reports_failure_instead_of_raising(monkeypatch):
    """Best effort, always: the alarm has three other channels and none may die with this one."""
    monkeypatch.setattr(notify.shutil, "which", lambda _n: None)
    assert notify.notify("titulo", "corpo") is False
