"""The tray icon: the app's only presence on screen, and the alarm's fallback channel."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..i18n import _
from . import live
from .icons import TrayState, tray_icon
from .keycapture import pretty


class Tray(QSystemTrayIcon):
    # Where Windows toasts come out; the alarm fires off-thread and Qt only paints on its own.
    toast = Signal(str, str, bool, int)

    def __init__(
        self,
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
        on_copy_last: Callable[[], None] | None = None,
        on_toggle_pause: Callable[[bool], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._on_copy_last = on_copy_last
        self._on_toggle_pause = on_toggle_pause
        self._state = TrayState.IDLE
        self._status_key = "ready"
        self._tip = ""

        self.setIcon(tray_icon(TrayState.IDLE))

        menu = QMenu()
        self._status = QAction(menu)
        self._status.setEnabled(False)
        menu.addAction(self._status)
        menu.addSeparator()

        self._open_action = QAction(menu)
        self._open_action.triggered.connect(on_open)
        menu.addAction(self._open_action)

        self._copy_action = QAction(menu)
        self._copy_action.setEnabled(False)
        if on_copy_last:
            self._copy_action.triggered.connect(on_copy_last)
        menu.addAction(self._copy_action)

        menu.addSeparator()
        self._pause_action = QAction(menu)
        self._pause_action.setCheckable(True)
        if on_toggle_pause:
            self._pause_action.toggled.connect(on_toggle_pause)
        menu.addAction(self._pause_action)

        self._quit_action = QAction(menu)
        self._quit_action.triggered.connect(on_quit)
        menu.addAction(self._quit_action)

        self.setContextMenu(menu)
        self._menu = menu
        # Both reasons accepted: some panels deliver Trigger on a left click, others DoubleClick.
        self.activated.connect(self._on_activated)

        self.toast.connect(self._show_toast)

        self.retranslate()
        # No parent window, so the walk in ui/live.py cannot find it: it signs up instead.
        live.register(self)

    def notify(self, title: str, body: str, urgent: bool, msecs: int) -> bool:
        """Callable from any thread; the signal hops to the GUI thread on its own."""
        if not self.isVisible():
            return False
        self.toast.emit(title, body, urgent, msecs)
        return True

    def _show_toast(self, title: str, body: str, urgent: bool, msecs: int) -> None:
        icon = (
            QSystemTrayIcon.MessageIcon.Critical
            if urgent
            else QSystemTrayIcon.MessageIcon.Information
        )
        self.showMessage(title, body, icon, msecs)

    def retranslate(self) -> None:
        self._open_action.setText(_("Open Dito"))
        self._copy_action.setText(_("Copy the last text"))
        self._pause_action.setText(_("Pause dictation"))
        self._quit_action.setText(_("Quit"))
        self._status.setText(self._status_text())
        self.setToolTip(self._tip or f"Dito — {self._status_text()}")

    def _status_text(self) -> str:
        return {
            "ready": _("ready"),
            "recording": _("recording"),
            "meeting": _("recording the meeting"),
            "transcribing": _("transcribing…"),
            "alarm": _("NO AUDIO"),
            "paused": _("paused"),
        }.get(self._status_key, self._status_key)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            # By reference, never by label: the label is translated and would stop matching.
            self._open_action.trigger()

    # ---- state -----------------------------------------------------------------------

    def set_ready(self, ptt_key: str, meeting_key: str) -> None:
        self._apply(
            TrayState.IDLE,
            "ready",
            _("Dito — hold {dictate} to dictate, {meeting} for a meeting").format(
                dictate=pretty(ptt_key), meeting=pretty(meeting_key)
            ),
        )

    def set_recording(self, meeting: bool = False) -> None:
        key = "meeting" if meeting else "recording"
        self._apply(TrayState.RECORDING, key, "")

    def set_transcribing(self) -> None:
        self._apply(TrayState.RECORDING, "transcribing", "")

    def set_alarm(self, reason: str) -> None:
        """The alarm's last line of defence: red icon and the cause in the tooltip."""
        self._apply(TrayState.ALERT, "alarm", f"Dito — {reason}")

    def set_paused(self) -> None:
        self._apply(TrayState.IDLE, "paused", "")

    def set_preparing(self, detail: str) -> None:
        self._apply(TrayState.IDLE, detail, f"Dito — {detail}")

    def set_last_text(self, text: str | None) -> None:
        self._copy_action.setEnabled(bool(text))

    def _apply(self, state: TrayState, status_key: str, tip: str) -> None:
        if state is not self._state:
            self.setIcon(tray_icon(state))
            self._state = state
        self._status_key = status_key
        self._tip = tip
        self._status.setText(self._status_text())
        self.setToolTip(tip or f"Dito — {self._status_text()}")
