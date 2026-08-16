"""The Dito window, opened on request and never at login: transcriptions and settings."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import config as cfgmod
from ..core import library
from ..i18n import _
from .settings_page import SettingsPage
from .theme import Palette, Radius, Size, Space, Type, stylesheet


# Built on call, never at import: a label translated before setup() would keep the wrong language.
def state_label(state: str) -> tuple[str, str]:
    labels = {
        "done": (_("ready"), "success"),
        "recording": (_("interrupted"), "alert"),
        "failed": (_("failed"), "danger"),
        "transcribe_failed": (_("transcription failed"), "danger"),
        "unknown": (_("unknown"), "muted"),
    }
    return labels.get(state, labels["unknown"])


def _human_size(size: int) -> str:
    if size >= 1 << 30:
        return f"{size / (1 << 30):.1f} GB"
    if size >= 1 << 20:
        return f"{size / (1 << 20):.0f} MB"
    if size >= 1 << 10:
        return f"{size / (1 << 10):.0f} kB"
    return f"{size} B"


def _human_duration(seconds: float) -> str:
    total = int(seconds)
    if total >= 3600:
        return f"{total // 3600}h{(total % 3600) // 60:02d}"
    if total >= 60:
        return f"{total // 60} min"
    return f"{total}s"


def _human_when(when: datetime | None) -> str:
    if when is None:
        return _("unknown date")
    today = datetime.now().date()
    if when.date() == today:
        return _("today, {time}").format(time=f"{when:%H:%M}")
    delta = (today - when.date()).days
    if delta == 1:
        return _("yesterday, {time}").format(time=f"{when:%H:%M}")
    if delta < 7:
        return _("{days} days ago, {time}").format(days=delta, time=f"{when:%H:%M}")
    return f"{when:%d/%m/%Y %H:%M}"


class SessionRow(QFrame):
    """One recording in the list, not a table row: a column would truncate the text away."""

    def __init__(self, info: library.SessionInfo, palette: Palette, parent=None) -> None:
        super().__init__(parent)
        self.info = info
        self.setProperty("role", "card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(Space.LG, Space.MD, Space.LG, Space.MD)
        outer.setSpacing(Space.SM)

        head = QHBoxLayout()
        head.setSpacing(Space.SM)

        when = QLabel(_human_when(info.started))
        when.setStyleSheet(f"font-weight: {Type.MEDIUM};")
        head.addWidget(when)

        kind = QLabel(_("meeting") if info.mode == "meeting" else _("dictation"))
        # text_secondary: a chip label is content and owes the 4.5 floor; muted was a smudge.
        kind.setStyleSheet(
            f"color: {palette.text_secondary}; background: {palette.surface_alt};"
            f" border-radius: {Radius.CONTROL}px; padding: 2px {Space.SM}px;"
            f" font-size: {Type.CAPTION}px;"
        )
        head.addWidget(kind)

        label, role = state_label(info.state)
        if info.state != "done":
            color = {"danger": palette.danger, "alert": palette.alert}.get(
                role, palette.text_muted
            )
            flag = QLabel(label)
            flag.setStyleSheet(f"color: {color}; font-size: {Type.CAPTION}px;")
            head.addWidget(flag)

        head.addStretch(1)

        meta = QLabel(f"{_human_duration(info.seconds)} · {_human_size(info.size_bytes)}")
        meta.setStyleSheet(
            f"color: {palette.text_muted}; font-family: {Type.MONO};"
            f" font-size: {Type.CAPTION}px;"
        )
        head.addWidget(meta)

        open_btn = QPushButton(_("Open folder"))
        open_btn.setProperty("variant", "ghost")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda: library.open_folder(info.path))
        head.addWidget(open_btn)

        outer.addLayout(head)

        preview = QLabel(info.preview or _("— no text —"))
        preview.setWordWrap(True)
        preview.setProperty("role", "secondary")
        outer.addWidget(preview)


class SessionsPage(QWidget):
    def __init__(self, cfg: cfgmod.Config, palette: Palette, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._palette = palette

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Space.MD)

        head = QHBoxLayout()
        self._summary = QLabel("")
        self._summary.setProperty("role", "hint")
        head.addWidget(self._summary)
        head.addStretch(1)

        folder_btn = QPushButton(_("Open the folder"))
        folder_btn.clicked.connect(lambda: library.open_folder(self.cfg.library_dir()))
        head.addWidget(folder_btn)

        refresh = QPushButton(_("Refresh"))
        refresh.setProperty("variant", "ghost")
        refresh.clicked.connect(self.reload)
        head.addWidget(refresh)
        root.addLayout(head)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._list.setSpacing(0)
        root.addWidget(self._list, 1)

        self._empty = QLabel(
            _("Nothing recorded yet.\nHold the dictation key and speak — the text appears "
              "wherever the cursor is.")
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setProperty("role", "hint")
        root.addWidget(self._empty)

        self.reload()

    def reload(self) -> None:
        self._list.clear()
        sessions = library.list_sessions()

        self._empty.setVisible(not sessions)
        self._list.setVisible(bool(sessions))

        for info in sessions:
            row = SessionRow(info, self._palette)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)

        total = library.total_size()
        broken = [s for s in sessions if not s.done]
        parts = [_("{count} recordings").format(count=len(sessions)), _human_size(total)]
        if broken:
            parts.append(_("{count} to recover").format(count=len(broken)))
        self._summary.setText(" · ".join(parts))


class MainWindow(QWidget):
    closed = Signal()

    def __init__(
        self,
        cfg: cfgmod.Config,
        palette: Palette,
        icon: QIcon | None = None,
        pause_hotkeys: Callable[[], None] | None = None,
        resume_hotkeys: Callable[[], None] | None = None,
        conflicts: Callable[[str, str], str | None] | None = None,
        on_config_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self._palette = palette
        self._on_config_changed = on_config_changed or (lambda: None)

        self.setObjectName("root")
        self.setWindowTitle("Dito")
        if icon is not None:
            self.setWindowIcon(icon)
        self.resize(Size.WINDOW_W, Size.WINDOW_H)
        self.setStyleSheet(stylesheet(palette))

        root = QVBoxLayout(self)
        root.setContentsMargins(Space.XXL, Space.XL, Space.XXL, Space.XL)
        root.setSpacing(Space.LG)

        header = QHBoxLayout()
        title = QLabel("Dito")
        title.setProperty("role", "display")
        header.addWidget(title)
        subtitle = QLabel(_("voice dictation, offline"))
        subtitle.setProperty("role", "hint")
        header.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignBottom)
        header.addStretch(1)
        self._toast = QLabel("")
        self._toast.setProperty("role", "hint")
        header.addWidget(self._toast)
        root.addLayout(header)

        tabs = QTabWidget()
        self.sessions = SessionsPage(cfg, palette)
        tabs.addTab(self._scrollable(self.sessions), _("Transcriptions"))

        self.settings = SettingsPage(
            cfg,
            palette,
            pause_hotkeys=pause_hotkeys,
            resume_hotkeys=resume_hotkeys,
            conflicts=conflicts,
        )
        self.settings.changed.connect(self._saved)
        self.settings.notice.connect(self._notice)
        tabs.addTab(self._scrollable(self.settings), _("Settings"))
        root.addWidget(tabs, 1)

    def _scrollable(self, inner: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(inner)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return area

    def _saved(self) -> None:
        self._flash(_("settings saved"))
        self._on_config_changed()

    def _notice(self, message: str) -> None:
        self._flash(message)

    def _flash(self, message: str) -> None:
        self._toast.setText(message)
        QTimer.singleShot(2200, lambda: self._toast.setText(""))

    def present(self) -> None:
        """Bring the window forward from hidden, minimised or open: a second launch lands here."""
        self.sessions.reload()
        self.show()
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive
        )
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Closing does NOT quit: the daemon keeps listening; quitting is the tray menu."""
        event.ignore()
        self.hide()
        self.closed.emit()
