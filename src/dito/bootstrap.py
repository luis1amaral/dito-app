"""First-run setup of the user venv, with a window — see docs/armadilhas.md 6.4."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from . import paths
from .i18n import _
from .i18n import setup as setup_language

_WINDOWS = sys.platform == "win32"

APP_DIR = Path("/usr/lib/dito")
# On Linux the .deb builds this venv on first run; on Windows the installer already did, and the
# app is running inside it — so `sys.prefix` is the one whose GPU extras matter.
VENV_DIR = (
    Path(sys.prefix)
    if _WINDOWS
    else Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    / "dito"
    / "venv"
)
LOCK = APP_DIR / "requirements.lock"
_GPU_STATE = paths.state_dir() if _WINDOWS else VENV_DIR.parent
GPU_MARK = _GPU_STATE / "gpu-ready"
GPU_LOCK = _GPU_STATE / "gpu-install.lock"

# pip lays CUDA out differently on each platform, down to the file extension.
CUBLAS_GLOB = (
    "Lib/site-packages/nvidia/cublas/bin/cublas64_*.dll"
    if _WINDOWS
    else "lib/python*/site-packages/nvidia/cublas/lib/libcublas.so*"
)

# ctranslate2 loads these at runtime; the driver alone is not enough — see docs/armadilhas.md 3.8.
# Pinned by major: a future cuDNN 10 against this ctranslate2 fails as a swallowed RuntimeError.
CUDA_PACKAGES = ("nvidia-cublas-cu12>=12,<13", "nvidia-cudnn-cu12>=9,<10")
GPU_DISK_FLOOR_GB = 5          # ~1.5 GB downloaded unpacks to ~2.3 GB, and pip needs room to work
GPU_INSTALL_TIMEOUT_S = 1800


def venv_python() -> Path:
    return VENV_DIR / ("Scripts" if _WINDOWS else "bin") / ("python.exe" if _WINDOWS else "python")


def has_nvidia_gpu() -> bool:
    """True when an NVIDIA GPU is actually usable, so the CUDA libraries are worth the download."""
    if Path("/dev/nvidia0").exists():
        return True
    try:
        # Never call this before the tray is up: on Optimus it wakes a sleeping dGPU, which is slow.
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

    if gpu_extras_missing():
        ok, message = install_gpu_extras(say)
        if not ok:
            say(message)
    return True, _("ready")


def _cublas_on_disk() -> bool:
    return next(VENV_DIR.glob(CUBLAS_GLOB), None) is not None


def gpu_extras_ready() -> bool:
    """The marker decides among libraries that EXIST — see docs/armadilhas.md 3.10."""
    if not _cublas_on_disk():
        # The venv it described is gone; keeping it would pin the CPU forever, in silence.
        GPU_MARK.unlink(missing_ok=True)
        return False
    return GPU_MARK.exists() or _adopt_preexisting()


def _adopt_preexisting() -> bool:
    """Installed before the marker existed: prove it loads, record it, skip a second download."""
    found = sorted(VENV_DIR.glob(CUBLAS_GLOB))
    if not found:
        return False
    try:
        ctypes.CDLL(str(found[0]))
    except OSError:
        return False
    try:
        GPU_MARK.parent.mkdir(parents=True, exist_ok=True)
        GPU_MARK.write_text("ok\n", encoding="utf-8")
    except OSError:
        pass
    return True


def frozen() -> bool:
    """The .exe from the installer has no venv to pip into — and no `sys.prefix` worth reading."""
    return bool(getattr(sys, "frozen", False))


def gpu_extras_missing() -> bool:
    """Cheap test first: has_nvidia_gpu() may wake a sleeping dGPU, so never ask it needlessly."""
    # `frozen` first: gpu_extras_ready() would erase the marker the venv install shares with us.
    return not frozen() and not gpu_extras_ready() and has_nvidia_gpu()


def _enough_disk() -> bool:
    try:
        free = shutil.disk_usage(VENV_DIR.parent if VENV_DIR.parent.exists() else Path.home()).free
    except OSError:
        return True
    return free >= GPU_DISK_FLOOR_GB * 1_000_000_000


def install_gpu_extras(say, on_process=None) -> tuple[bool, str]:
    """Acceleration is a bonus: losing it must never cost the user a working CPU install."""
    if not _enough_disk():
        return False, _("Not enough free disk space for GPU acceleration — Dito will use the CPU.")

    try:
        GPU_LOCK.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create is the whole point: two pips in one venv can truncate a .so.
        handle = os.open(GPU_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, _("GPU acceleration is already being set up.")
    except OSError:
        return False, _("GPU acceleration unavailable — Dito will use the CPU.")

    say(_("enabling GPU acceleration…"))
    failed = _("GPU acceleration unavailable — Dito will use the CPU.")
    try:
        proc = subprocess.Popen(
            [str(venv_python()), "-m", "pip", "install", "--no-cache-dir", *CUDA_PACKAGES],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if on_process is not None:
            on_process(proc)
        try:
            proc.communicate(timeout=GPU_INSTALL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return False, failed
        if proc.returncode != 0:
            return False, failed
        GPU_MARK.write_text("ok\n", encoding="utf-8")
    except (subprocess.SubprocessError, OSError):
        return False, failed
    finally:
        os.close(handle)
        GPU_LOCK.unlink(missing_ok=True)

    return True, _("ready")


def has_display() -> bool:
    """Windows always has a desktop; only on X11 does a missing DISPLAY mean headless."""
    return sys.platform == "win32" or bool(os.environ.get("DISPLAY"))


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
        _("A few components are missing that Debian does not package. About 1.5 GB to download "
          "and 2.5 GB on disk, once — most of it is what puts transcription on your NVIDIA card "
          "instead of the CPU.")
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

    if "--headless" in argv or not has_display():
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
