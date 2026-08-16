"""First-run setup of the user venv, with a window — see docs/armadilhas.md 6.4."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from .i18n import _
from .i18n import setup as setup_language

APP_DIR = Path("/usr/lib/dito")
VENV_DIR = Path(
    os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
) / "dito" / "venv"
LOCK = APP_DIR / "requirements.lock"


def venv_python() -> Path:
    return VENV_DIR / "bin" / "python"


def ready() -> bool:
    """True when the venv exists and the packages it was built for actually import."""
    if not venv_python().exists():
        return False
    try:
        subprocess.run(
            [str(venv_python()), "-c", "import faster_whisper, sounddevice"],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return True


def _requirements() -> list[str]:
    if not LOCK.exists():
        return ["faster-whisper>=1.1", "sounddevice>=0.5"]
    return [
        line.strip()
        for line in LOCK.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def install(progress=None) -> tuple[bool, str]:
    """Create the venv and install what Debian does not package. Returns (ok, message)."""
    say = progress or (lambda _m: None)
    try:
        VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
        if not venv_python().exists():
            say(_("creating the environment…"))
            # --system-site-packages is what lets pip reuse the apt Qt/numpy/onnxruntime.
            subprocess.run(
                [sys.executable, "-m", "venv", "--system-site-packages", str(VENV_DIR)],
                check=True,
                capture_output=True,
            )

        say(_("downloading the components…"))
        done = subprocess.run(
            [str(venv_python()), "-m", "pip", "install", "--upgrade", *_requirements()],
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            tail = (done.stderr or done.stdout or "").strip().splitlines()
            reason = tail[-1] if tail else _("pip failed without saying why")
            return False, f"{_('could not download the components.')}\n{reason}"
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or b"").decode(errors="replace").strip().splitlines()
        return False, tail[-1] if tail else _("could not create the environment")
    except OSError as exc:
        return False, str(exc)

    if not ready():
        return False, _("the environment was created but the components do not load")
    return True, _("ready")


def _run_with_window() -> int:
    from PySide6.QtCore import QObject, Qt, QTimer, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    class Signals(QObject):
        step = Signal(str)
        done = Signal(bool, str)

    app = QApplication.instance() or QApplication(sys.argv)
    signals = Signals()

    window = QWidget()
    window.setWindowTitle(_("Setting up Dito"))
    window.resize(460, 0)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(12)

    heading = QLabel(_("Setting up Dito"))
    heading.setStyleSheet("font-size: 20px; font-weight: 600;")
    layout.addWidget(heading)

    body = QLabel(
        _("A few components are missing that Debian does not package.\n"
          "About 50 MB, once.")
    )
    body.setWordWrap(True)
    layout.addWidget(body)

    bar = QProgressBar()
    bar.setRange(0, 0)          # indeterminate: pip reports no usable total
    layout.addWidget(bar)

    status = QLabel("")
    status.setWordWrap(True)
    layout.addWidget(status)

    buttons = QHBoxLayout()
    buttons.addStretch(1)
    retry = QPushButton(_("Try again"))
    retry.hide()
    close = QPushButton(_("Close"))
    close.hide()
    buttons.addWidget(retry)
    buttons.addWidget(close)
    layout.addLayout(buttons)

    state = {"code": 1}

    def work() -> None:
        ok, message = install(progress=signals.step.emit)
        signals.done.emit(ok, message)

    def start() -> None:
        retry.hide()
        close.hide()
        bar.show()
        status.setText("")
        threading.Thread(target=work, daemon=True).start()

    def finished(ok: bool, message: str) -> None:
        bar.hide()
        if ok:
            state["code"] = 0
            status.setText(_("All set. Opening Dito…"))
            QTimer.singleShot(600, app.quit)
            return
        status.setText(message)
        status.setStyleSheet("color: #c62a30;")
        retry.show()
        close.show()

    signals.step.connect(status.setText, Qt.ConnectionType.QueuedConnection)
    signals.done.connect(finished, Qt.ConnectionType.QueuedConnection)
    retry.clicked.connect(start)
    close.clicked.connect(app.quit)

    window.show()
    start()
    app.exec()
    return state["code"]


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    setup_language(os.environ.get("DITO_LANG", "auto"))

    # Set by the autostart entry: a login must never start a large download with no window.
    if os.environ.get("DITO_BOOTSTRAP") == "never":
        return 0

    if ready():
        return 0

    if "--headless" in argv or not os.environ.get("DISPLAY"):
        ok, message = install(progress=lambda m: print(f"  {m}", flush=True))
        print(message)
        return 0 if ok else 1

    try:
        return _run_with_window()
    except Exception as exc:      # noqa: BLE001 - last resort, the install still has to happen
        print(f"[{_('warning')}] {type(exc).__name__}", flush=True)
        ok, message = install(progress=lambda m: print(f"  {m}", flush=True))
        print(message)
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
