"""First run after installing the .deb: build the user's virtualenv, with something on screen.

Why this is not in the package's postinst, where it would be more conventional: `pip install` as
root writes files dpkg does not know about, and a postinst that fails leaves the package
half-configured and apt jammed — with no window anywhere to say what went wrong. Here it runs as
the user, in their own directory, with a progress bar, a readable error and a retry button.

It is not a new requirement either. The app already has to download a 464 MB model on first use,
so first use already needs the network.

This module runs on the SYSTEM python, before the venv exists. It may therefore import only the
standard library and Qt — Qt because the .deb depends on the Debian package, so it is guaranteed
present. Nothing from `dito` beyond this file.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

APP_DIR = Path("/usr/lib/dito")
VENV_DIR = Path(
    os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
) / "dito" / "venv"
LOCK = APP_DIR / "requirements.lock"

TITLE = "Preparando o Dito"
INTRO = (
    "Faltam alguns componentes que o Debian não empacota.\n"
    "São cerca de 50 MB, uma vez só."
)


def venv_python() -> Path:
    return VENV_DIR / "bin" / "python"


def ready() -> bool:
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
    """Create the venv and install what is missing. Returns (ok, message in pt-BR)."""
    say = progress or (lambda _m: None)
    try:
        VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
        if not venv_python().exists():
            say("criando o ambiente…")
            # --system-site-packages is load-bearing: it is what lets pip see the Qt, numpy and
            # onnxruntime already installed by apt instead of downloading ~250 MB of wheels.
            subprocess.run(
                [sys.executable, "-m", "venv", "--system-site-packages", str(VENV_DIR)],
                check=True,
                capture_output=True,
            )

        say("baixando os componentes…")
        done = subprocess.run(
            [str(venv_python()), "-m", "pip", "install", "--upgrade", *_requirements()],
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            tail = (done.stderr or done.stdout or "").strip().splitlines()
            reason = tail[-1] if tail else "o pip falhou sem dizer o motivo"
            return False, f"não consegui baixar os componentes.\n{reason}"
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or b"").decode(errors="replace").strip().splitlines()
        return False, tail[-1] if tail else "falha ao criar o ambiente"
    except OSError as exc:
        return False, str(exc)

    if not ready():
        return False, "o ambiente foi criado mas os componentes não carregam"
    return True, "pronto"


# ---------------------------------------------------------------------------------------


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
    window.setWindowTitle(TITLE)
    window.resize(460, 0)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(12)

    heading = QLabel(TITLE)
    heading.setStyleSheet("font-size: 20px; font-weight: 600;")
    layout.addWidget(heading)

    body = QLabel(INTRO)
    body.setWordWrap(True)
    layout.addWidget(body)

    bar = QProgressBar()
    bar.setRange(0, 0)          # indeterminate: pip does not report a usable total
    layout.addWidget(bar)

    status = QLabel("")
    status.setWordWrap(True)
    layout.addWidget(status)

    buttons = QHBoxLayout()
    buttons.addStretch(1)
    retry = QPushButton("Tentar de novo")
    retry.hide()
    close = QPushButton("Fechar")
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
            status.setText("Tudo pronto. Abrindo o Dito…")
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

    if os.environ.get("DITO_BOOTSTRAP") == "never":
        # Set by the autostart entry: a login must never trigger a large download with no window
        # to explain it. The daemon simply does not start until the user opens the app once.
        return 0

    if ready():
        return 0

    if "--headless" in argv or not os.environ.get("DISPLAY"):
        ok, message = install(progress=lambda m: print(f"  {m}", flush=True))
        print(message)
        return 0 if ok else 1

    try:
        return _run_with_window()
    except Exception as exc:      # noqa: BLE001 - last resort, must still install
        print(f"[aviso] sem janela ({type(exc).__name__}); seguindo pelo terminal", flush=True)
        ok, message = install(progress=lambda m: print(f"  {m}", flush=True))
        print(message)
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
