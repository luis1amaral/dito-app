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
DECLINED = VENV_DIR.parent / "gpu-declined"

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


def gpu_offer_pending() -> bool:
    """A ready venv never reaches install(), so an existing install needs its own offer."""
    return has_nvidia_gpu() and not gpu_extras_ready() and not DECLINED.exists()


def decline_gpu() -> None:
    """Remembering the "no" is what keeps the offer from becoming a window on every launch."""
    try:
        DECLINED.parent.mkdir(parents=True, exist_ok=True)
        DECLINED.touch()
    except OSError:
        pass


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


def _run_with_window(
    title: str, text: str, action, ask_first: bool = False, on_decline=None
) -> int:
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
    window.setWindowTitle(title)
    window.resize(460, 0)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(12)

    heading = QLabel(title)
    heading.setStyleSheet("font-size: 20px; font-weight: 600;")
    layout.addWidget(heading)

    body = QLabel(text)
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
    go = QPushButton(_("Enable") if ask_first else _("Try again"))
    dismiss = QPushButton(_("Not now") if ask_first else _("Close"))
    buttons.addWidget(go)
    buttons.addWidget(dismiss)
    layout.addLayout(buttons)

    state = {"code": 1}

    def work() -> None:
        ok, message = action(signals.step.emit)
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

    def leave() -> None:
        if on_decline is not None:
            on_decline()
        app.quit()

    signals.step.connect(status.setText, Qt.ConnectionType.QueuedConnection)
    signals.done.connect(finished, Qt.ConnectionType.QueuedConnection)
    go.clicked.connect(start)
    dismiss.clicked.connect(leave)

    window.show()
    if ask_first:
        bar.hide()
        state["code"] = 0       # turning the offer down is an answer, not a failure
    else:
        go.hide()
        dismiss.hide()
        start()
    app.exec()
    return state["code"]


def _offer_gpu(headless: bool) -> int:
    """Always returns 0: an offer that fails must never be what keeps Dito from opening."""
    if headless or not gpu_offer_pending():
        return 0

    try:
        _run_with_window(
            _("Use your graphics card?"),
            _("Dito found an NVIDIA card. Moving transcription onto it needs about 1.5 GB of\n"
              "libraries, downloaded once. Without them Dito keeps working on the CPU."),
            install_gpu_extras,
            ask_first=True,
            on_decline=decline_gpu,
        )
    except Exception as exc:      # noqa: BLE001 - the app opens either way
        print(f"[{_('warning')}] {type(exc).__name__}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    setup_language(os.environ.get("DITO_LANG", "auto"))

    # Set by the autostart entry: a login must never start a large download with no window.
    if os.environ.get("DITO_BOOTSTRAP") == "never":
        return 0

    headless = "--headless" in argv or not os.environ.get("DISPLAY")

    # A ready venv skips install(), so this is the only place an existing install hears the offer.
    if ready():
        return _offer_gpu(headless)

    if headless:
        ok, message = install(progress=lambda m: print(f"  {m}", flush=True))
        print(message)
        return 0 if ok else 1

    try:
        return _run_with_window(
            _("Setting up Dito"),
            _("A few components are missing that Debian does not package.\n"
              "About 50 MB, once."),
            lambda say: install(progress=say),
        )
    except Exception as exc:      # noqa: BLE001 - last resort, the install still has to happen
        print(f"[{_('warning')}] {type(exc).__name__}", flush=True)
        ok, message = install(progress=lambda m: print(f"  {m}", flush=True))
        print(message)
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
