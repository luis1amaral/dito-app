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

# ctranslate2 loads these at runtime; the driver alone is not enough — see docs/armadilhas.md 3.8.
CUDA_PACKAGES = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12")


def venv_python() -> Path:
    return VENV_DIR / "bin" / "python"


def has_nvidia_gpu() -> bool:
    """True when an NVIDIA GPU is actually usable, so the CUDA libraries are worth the download."""
    if Path("/dev/nvidia0").exists():
        return True
    try:
        subprocess.run(["nvidia-smi", "-L"], check=True, capture_output=True, timeout=15)
    except (subprocess.SubprocessError, OSError):
        return False
    return True


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

    if has_nvidia_gpu():
        ok, message = install_gpu_extras(say)
        if not ok:
            say(message)
    return True, _("ready")


def gpu_extras_ready() -> bool:
    """True when cuBLAS is already in the venv, which is what the GPU path fails without."""
    return any(VENV_DIR.glob("lib/python*/site-packages/nvidia/cublas/lib/libcublas.so*"))


def gpu_extras_missing() -> bool:
    """There is a card and nothing to drive it with: the one case worth downloading for."""
    return has_nvidia_gpu() and not gpu_extras_ready()


def install_gpu_extras(say) -> tuple[bool, str]:
    """Acceleration is a bonus: losing it must never cost the user a working CPU install."""
    say(_("enabling GPU acceleration…"))
    try:
        done = subprocess.run(
            [str(venv_python()), "-m", "pip", "install", "--upgrade", *CUDA_PACKAGES],
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except (subprocess.SubprocessError, OSError):
        return False, _("GPU acceleration unavailable — Dito will use the CPU.")

    if done.returncode != 0:
        return False, _("GPU acceleration unavailable — Dito will use the CPU.")
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
        _("A few components are missing that Debian does not package. About 1.5 GB, once — "
          "most of it is what puts transcription on your NVIDIA card instead of the CPU.")
        if gpu_extras_missing()
        else _("A few components are missing that Debian does not package.\n"
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
    go = QPushButton(_("Try again"))
    dismiss = QPushButton(_("Close"))
    buttons.addWidget(go)
    buttons.addWidget(dismiss)
    layout.addLayout(buttons)

    state = {"code": 1}

    def work() -> None:
        ok, message = install(progress=signals.step.emit)
        signals.done.emit(ok, message)

    def start() -> None:
        go.hide()
        dismiss.hide()
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
        go.setText(_("Try again"))
        dismiss.setText(_("Close"))
        go.show()
        dismiss.show()

    signals.step.connect(status.setText, Qt.ConnectionType.QueuedConnection)
    signals.done.connect(finished, Qt.ConnectionType.QueuedConnection)
    go.clicked.connect(start)
    dismiss.clicked.connect(app.quit)

    window.show()
    go.hide()
    dismiss.hide()
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
