"""The «placa de vídeo» box in the installer, and the `dito gpu` command behind it.

The .exe is CPU-only by construction: no CUDA in the bundle and no pip to fetch it. So the choice
moved to install time — a task in dito.iss runs `ditow gpu --install --window`, this module shows
the progress, and platform/windows/cuda_pack.py does the fetching. Measured difference on this
machine: RTF 0.26 on the card against 0.94 on the processor. See docs/armadilhas.md 3.11.
"""

from __future__ import annotations

import sys
import threading

from . import bootstrap
from .i18n import _

MB = 1_000_000


def _mb(value: int) -> int:
    return round(value / MB)


def ready() -> bool:
    return bootstrap.GPU_MARK.exists() and bool(bootstrap.cublas_paths())


def where() -> str:
    found = bootstrap.cublas_paths()
    return str(found[0].parent) if found else ""


def _skip_reason(force: bool) -> str | None:
    """Everything that means «do not download 1.3 GB», in the order that is cheap to ask."""
    if sys.platform != "win32":
        return _("this command is for Windows; on Linux the packages come from apt")
    if ready():
        return _("GPU acceleration is already installed.")
    # Asked last: nvidia-smi wakes a sleeping dGPU on Optimus, so never ask needlessly.
    if not force and not bootstrap.has_nvidia_gpu():
        return _("No NVIDIA card found — nothing was downloaded. Dito will use the processor.")
    return None


def run(install: bool, window: bool, force: bool, remove: bool) -> int:
    if remove:
        gone = bootstrap.remove_gpu_pack()
        print(_("GPU acceleration removed.") if gone else _("there was nothing to remove"))
        return 0

    if not install:
        if ready():
            print(_("GPU acceleration is installed: {path}").format(path=where()))
        else:
            print(_("GPU acceleration is not installed. Run «dito gpu --install»."))
        return 0

    skip = _skip_reason(force)
    if skip is not None:
        _tell(skip, window)
        # Zero on purpose: a machine with no card is not a failed installation.
        return 0

    if window and bootstrap.has_display():
        return _run_with_window()

    ok, message = bootstrap.install_gpu_pack(
        say=lambda m: print(f"  {m}", flush=True),
        on_progress=_printing_progress(),
    )
    print(message)
    return 0 if ok else 1


def _tell(message: str, window: bool) -> None:
    """`ditow.exe` has no console: called from the installer, a print goes nowhere at all."""
    print(message)
    if not window or not bootstrap.has_display():
        return
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        from .ui import icons

        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox(QMessageBox.Icon.Information, _("GPU acceleration"), message)
        box.setWindowIcon(icons.app_icon())
        box.exec()
        app.quit()
    except Exception:      # noqa: BLE001 - a message that fails to show must not fail the install
        pass


def _printing_progress():
    """One line per 5%: byte-by-byte would flood a redirected console with megabytes of text."""
    last = [-1]

    def report(done: int, total: int) -> None:
        step = int(done * 20 / total) if total else 0
        if step != last[0]:
            last[0] = step
            print(f"  {_mb(done)} MB / {_mb(total)} MB", flush=True)

    return report


def _run_with_window() -> int:
    from PySide6.QtCore import QObject, Qt, QTimer, Signal
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    from .ui import icons
    from .ui.theme import Size, Space, Type, palette, resolve_mode

    class Signals(QObject):
        step = Signal(str)
        progress = Signal(int, int)
        done = Signal(bool, str)

    app = QApplication.instance() or QApplication(sys.argv)
    # Read after the QApplication exists: `auto` asks Qt for the desktop's scheme.
    colors = palette(resolve_mode("auto"))
    signals = Signals()

    window = QWidget()
    window.setWindowTitle(_("GPU acceleration"))
    window.setWindowIcon(icons.app_icon())
    window.setFixedWidth(Size.DIALOG_W)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(Space.XXXL, Space.XXL, Space.XXXL, Space.XXL)
    layout.setSpacing(Space.MD)

    # The plate mark, not the lockup: its wordmark is dark and would vanish on a dark desktop.
    logo = QLabel()
    art = QPixmap(str(icons.ASSETS / "png" / "icon-48.png"))
    if not art.isNull():
        logo.setPixmap(art)
        layout.addWidget(logo)

    heading = QLabel(_("Enabling GPU acceleration"))
    heading.setStyleSheet(f"font-size: {Type.DISPLAY}px; font-weight: {Type.SEMIBOLD};")
    layout.addWidget(heading)

    body = QLabel(
        _("Downloading the NVIDIA libraries that put transcription on the graphics card instead "
          "of the processor — about 1.3 GB, once. Dito works either way; this only makes it "
          "roughly three times faster.")
    )
    body.setWordWrap(True)
    body.setStyleSheet(f"color: {colors.text_secondary};")
    layout.addWidget(body)

    bar = QProgressBar()
    bar.setRange(0, 0)          # indeterminate until PyPI says how many bytes there are
    bar.setTextVisible(False)
    layout.addWidget(bar)

    status = QLabel("")
    status.setWordWrap(True)
    status.setStyleSheet(f"color: {colors.text_muted}; font-size: {Type.CAPTION}px;")
    layout.addWidget(status)

    buttons = QHBoxLayout()
    buttons.addStretch(1)
    go = QPushButton(_("Try again"))
    dismiss = QPushButton(_("Close"))
    buttons.addWidget(go)
    buttons.addWidget(dismiss)
    layout.addLayout(buttons)

    state = {"code": 1}

    def work() -> None:
        ok, message = bootstrap.install_gpu_pack(
            say=signals.step.emit, on_progress=signals.progress.emit
        )
        signals.done.emit(ok, message)

    def advance(done: int, total: int) -> None:
        if not total:
            return
        # Megabytes, not bytes: QProgressBar counts in int, and the label reads better anyway.
        bar.setRange(0, _mb(total))
        bar.setValue(_mb(done))
        status.setText(_("{done} MB of {total} MB").format(done=_mb(done), total=_mb(total)))

    def start() -> None:
        go.hide()
        dismiss.hide()
        bar.setRange(0, 0)
        bar.show()
        status.setText("")
        threading.Thread(target=work, daemon=True).start()

    def finished(ok: bool, message: str) -> None:
        bar.hide()
        if ok:
            state["code"] = 0
            status.setStyleSheet(f"color: {colors.success};")
            status.setText(_("All set. Dictation will run on the graphics card."))
            QTimer.singleShot(1200, app.quit)
            return
        status.setStyleSheet(f"color: {colors.danger};")
        status.setText(message)
        go.show()
        dismiss.show()

    signals.step.connect(status.setText, Qt.ConnectionType.QueuedConnection)
    signals.progress.connect(advance, Qt.ConnectionType.QueuedConnection)
    signals.done.connect(finished, Qt.ConnectionType.QueuedConnection)
    go.clicked.connect(start)
    dismiss.clicked.connect(app.quit)

    window.show()
    go.hide()
    dismiss.hide()
    start()
    app.exec()
    return state["code"]
