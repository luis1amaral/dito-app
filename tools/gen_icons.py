"""Rasterises the brand SVGs into PNG with QtSvg.

QtSvg is not a convenience here, it is the only option: this machine has no inkscape, no
imagemagick and no rsvg-convert, and the packaging step cannot depend on a tool that is absent.
Qt is already a hard dependency of the app, so the renderer that draws the tray icon at runtime
is the same one that bakes the PNGs — what you see installed is what you saw in development.

    python tools/gen_icons.py            # writes src/dito/ui/assets/png/
    python tools/gen_icons.py --check    # writes nothing, exits 1 if a PNG is out of date

Idempotent by content: a PNG is only rewritten when its bytes actually change, so running twice
leaves the tree untouched and `--check` can be trusted in a build.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
except ImportError as erro:
    raise SystemExit(
        "ERRO: o PySide6 não está instalado neste interpretador, e é ele que rasteriza os SVG.\n"
        f"  interpretador em uso: {sys.executable}\n"
        "  instale com um dos dois:\n"
        "    sudo apt install --no-install-recommends "
        "python3-pyside6.qtsvg python3-pyside6.qtgui\n"
        '    .venv/bin/pip install "PySide6>=6.8"\n'
        "  a venv do projeto é criada com --system-site-packages, então o pacote do apt já vale."
    ) from erro

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dito.ui.theme import Size  # noqa: E402

ASSETS = ROOT / "src" / "dito" / "ui" / "assets"
OUT = ASSETS / "png"

# Stop at 512. 1024 does not render and has already burned two projects in this house — it is
# written down in the standard make-deb.sh. Adding it back costs a debugging session, not a line.
HICOLOR = (48, 64, 128, 256, 512)
# The panel draws the tray icon at Size.TRAY_ICON; the double is the HiDPI variant.
TRAY = (Size.TRAY_ICON, Size.TRAY_ICON * 2)
# The lockup is wide: these are HEIGHTS, and the width follows the viewBox.
LOGO = (64, 128)

JOBS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("icon", HICOLOR),
    ("tray-idle", TRAY),
    ("tray-recording", TRAY),
    ("tray-alert", TRAY),
    ("logo", LOGO),
)


def render(svg: Path, height: int) -> tuple[bytes, int, int]:
    """Render one SVG at a given height. Width comes from the viewBox, so a square icon and a
    wide lockup go through the same path with no special case."""
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise SystemExit(f"ERRO: SVG inválido ou ilegível: {svg}")

    box = renderer.viewBoxF()
    if box.height() <= 0:
        raise SystemExit(f"ERRO: {svg.name} não declara viewBox — sem ela não há proporção")
    width = max(1, round(height * box.width() / box.height()))

    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data.data()), width, height


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera os PNG da marca do Dito a partir dos SVG, com o QtSvg."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="não grava nada; sai com código 1 se algum PNG estiver desatualizado ou faltando",
    )
    args = parser.parse_args()

    QGuiApplication([])

    if not args.check:
        OUT.mkdir(parents=True, exist_ok=True)

    nota = "  (modo --check, nada será gravado)" if args.check else ""
    print(f"origem : {ASSETS.relative_to(ROOT)}")
    print(f"destino: {OUT.relative_to(ROOT)}{nota}\n")

    desatualizados: list[str] = []
    gravados = 0
    iguais = 0
    total = 0

    for stem, sizes in JOBS:
        svg = ASSETS / f"{stem}.svg"
        if not svg.exists():
            raise SystemExit(f"ERRO: não encontrei {svg.relative_to(ROOT)}")
        for size in sizes:
            data, width, height = render(svg, size)
            destino = OUT / f"{stem}-{size}.png"
            atual = destino.read_bytes() if destino.exists() else None
            total += len(data)
            if atual == data:
                estado = "inalterado"
                iguais += 1
            elif args.check:
                estado = "DESATUALIZADO" if atual is not None else "FALTANDO"
                desatualizados.append(destino.name)
            else:
                destino.write_bytes(data)
                estado = "gravado"
                gravados += 1
            print(f"  {destino.name:<24} {width:>4}x{height:<4} {len(data):>7} bytes  {estado}")

    print()
    if args.check:
        if desatualizados:
            print(f"FALHA: {len(desatualizados)} arquivo(s) fora de data: "
                  f"{', '.join(desatualizados)}")
            print("Rode  python tools/gen_icons.py  para regerar.")
            return 1
        print(f"OK: os {iguais} PNG estão em dia ({total} bytes no total).")
        return 0

    print(f"OK: {gravados} gravado(s), {iguais} inalterado(s), {total} bytes no total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
