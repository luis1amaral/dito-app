"""The tray icon: the app's only presence on screen, and the alarm's fallback channel."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icons import TrayState, tray_icon
from .keycapture import pretty


class Tray(QSystemTrayIcon):
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

        self.setIcon(tray_icon(TrayState.IDLE))
        self.setToolTip("Dito — pronto")

        menu = QMenu()
        self._status = QAction("pronto", menu)
        self._status.setEnabled(False)
        menu.addAction(self._status)
        menu.addSeparator()

        open_action = QAction("Abrir o Dito", menu)
        open_action.triggered.connect(on_open)
        menu.addAction(open_action)

        self._copy_action = QAction("Copiar o último texto", menu)
        self._copy_action.setEnabled(False)
        if on_copy_last:
            self._copy_action.triggered.connect(on_copy_last)
        menu.addAction(self._copy_action)

        menu.addSeparator()
        self._pause_action = QAction("Pausar o ditado", menu)
        self._pause_action.setCheckable(True)
        if on_toggle_pause:
            self._pause_action.toggled.connect(on_toggle_pause)
        menu.addAction(self._pause_action)

        quit_action = QAction("Sair", menu)
        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self._menu = menu
        # Both reasons accepted: some panels deliver Trigger on a left click, others DoubleClick.
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            for action in self._menu.actions():
                if action.text() == "Abrir o Dito":
                    action.trigger()
                    return

    # ---- state -----------------------------------------------------------------------

    def set_ready(self, ptt_key: str, meeting_key: str) -> None:
        self._apply(
            TrayState.IDLE,
            "pronto",
            f"Dito — segure {pretty(ptt_key)} para ditar, {pretty(meeting_key)} para reunião",
        )

    def set_recording(self, meeting: bool = False) -> None:
        label = "gravando reunião" if meeting else "gravando"
        self._apply(TrayState.RECORDING, label, f"Dito — {label}")

    def set_transcribing(self) -> None:
        self._apply(TrayState.RECORDING, "transcrevendo…", "Dito — transcrevendo")

    def set_alarm(self, reason: str) -> None:
        """The alarm's last line of defence: red icon and the cause in the tooltip."""
        self._apply(TrayState.ALERT, "SEM ÁUDIO", f"Dito — {reason}")

    def set_paused(self) -> None:
        self._apply(TrayState.IDLE, "pausado", "Dito — ditado pausado")

    def set_preparing(self, detail: str) -> None:
        self._apply(TrayState.IDLE, detail, f"Dito — {detail}")

    def set_last_text(self, text: str | None) -> None:
        self._copy_action.setEnabled(bool(text))

    def _apply(self, state: TrayState, status: str, tip: str) -> None:
        if state is not self._state:
            self.setIcon(tray_icon(state))
            self._state = state
        self._status.setText(status)
        self.setToolTip(tip)
