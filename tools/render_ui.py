"""Renders UI states to PNG without touching the user's screen.

Reviewing an interface by reading its source is guessing. This runs Qt on the offscreen platform
plugin, grabs each state, and composites it over a mock desktop so the floating pill is judged
the way it will actually be seen — over content, not over white.

    python tools/render_ui.py [--out shots]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from dito import config  # noqa: E402
from dito.ui import theme  # noqa: E402
from dito.ui.overlay import Overlay  # noqa: E402
from dito.ui.window import MainWindow  # noqa: E402

PAD = 40


def mock_desktop(width: int, height: int, dark: bool) -> QPixmap:
    """A gradient stands in for real content. A pill judged against flat white looks fine and
    then disappears over a photo or a code editor."""
    canvas = QPixmap(width, height)
    painter = QPainter(canvas)
    gradient = QLinearGradient(0, 0, width, height)
    if dark:
        gradient.setColorAt(0.0, QColor("#20242c"))
        gradient.setColorAt(1.0, QColor("#101318"))
    else:
        gradient.setColorAt(0.0, QColor("#e9ecf2"))
        gradient.setColorAt(1.0, QColor("#cfd6e2"))
    painter.fillRect(0, 0, width, height, gradient)
    painter.end()
    return canvas


def shoot(widget, out: Path, dark: bool) -> tuple[int, int, int]:
    widget.adjustSize()
    QApplication.processEvents()
    shot = widget.grab()
    canvas = mock_desktop(shot.width() + PAD * 2, shot.height() + PAD * 2, dark)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.drawPixmap(PAD, PAD, shot)
    painter.end()
    canvas.save(str(out))
    return canvas.width(), canvas.height(), out.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="shots")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    for mode in (theme.Mode.LIGHT, theme.Mode.DARK):
        pal = theme.palette(mode)
        app.setStyleSheet(theme.stylesheet(pal))
        hud = Overlay(pal)
        dark = mode is theme.Mode.DARK

        states = {
            "recording": lambda h: h.show_recording(),
            "meeting": lambda h: h.show_recording(meeting=True),
            "quiet": lambda h: h.show_quiet("chegue mais perto do microfone"),
            "dead": lambda h: h.show_dead(
                "o ganho de captura do hardware está em 0%", "Corrigir"
            ),
            "working": lambda h: h.show_working("trecho 3 de 4"),
            "toast": lambda h: h.show_toast("Reunião salva", "42 min · 8.320 palavras"),
        }
        for name, setup in states.items():
            setup(hud)
            for _ in range(6):          # let the waveform ease into a shape worth looking at
                hud.push_level(0.05 if name in ("recording", "meeting") else 0.0)
                hud._wave.tick()
            QApplication.processEvents()
            path = out_dir / f"hud-{mode.value}-{name}.png"
            w, h, size = shoot(hud, path, dark)
            print(f"  {path}  {w}x{h}  {size / 1024:.0f} kB")
        hud.close()

    for mode in (theme.Mode.LIGHT, theme.Mode.DARK):
        pal = theme.palette(mode)
        window = MainWindow(cfg=config.load(), palette=pal)
        window.resize(880, 620)
        window.show()
        QApplication.processEvents()
        for tab, name in ((0, "sessions"), (1, "settings")):
            window.findChild(QTabWidget).setCurrentIndex(tab)
            QApplication.processEvents()
            shot = window.grab()
            path = out_dir / f"window-{mode.value}-{name}.png"
            shot.save(str(path))
            print(f"  {path}  {shot.width()}x{shot.height()}  "
                  f"{path.stat().st_size / 1024:.0f} kB")
        window.hide()

    print(f"\n{len(list(out_dir.glob('*.png')))} imagens em {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
