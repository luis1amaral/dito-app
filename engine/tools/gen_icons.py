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
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
    from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter
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

from dito.ui.theme import LIGHT, Size  # noqa: E402

ASSETS = ROOT / "src" / "dito" / "ui" / "assets"
OUT = ASSETS / "png"
# Outside ui/assets on purpose: the .spec copies that folder wholesale into the bundle, and an
# uncompressed BMP the app never opens has no business travelling inside the .exe.
WIZARD = ROOT / "packaging" / "windows" / "wizard"

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

# Every size the Windows shell asks for: 16 in the title bar, 32 in the taskbar, 48 in the Start
# Menu, 256 in the large view. A .ico missing one makes Windows scale a neighbour, and it shows.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICO = ASSETS / "dito.ico"

# The Inno Setup wizard: the tall strip on the welcome page and the badge in the header. These are
# the sizes Inno itself asks for by DPI — it picks from the list, so a 150% desktop stays sharp.
WIZARD_LARGE = ((164, 314), (192, 386), (246, 459), (328, 628))
WIZARD_SMALL = ((55, 58), (64, 68), (83, 80), (110, 116))
# The lockup sits in the upper third, as wide as the strip minus its clear space.
LOGO_WIDTH = 0.72
LOGO_CENTRE = 0.33
BAND_HEIGHT = 0.22


def encode(image: QImage, fmt: str) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, fmt)
    buffer.close()
    return bytes(data.data())


def _renderer(svg: Path) -> QSvgRenderer:
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise SystemExit(f"ERRO: SVG inválido ou ilegível: {svg}")
    return renderer


def _fit(renderer: QSvgRenderer, left: float, centre_y: float, width: float) -> QRectF:
    """Places the art by its width, taking the height from the viewBox so nothing is stretched."""
    box = renderer.viewBoxF()
    height = width * box.height() / box.width()
    return QRectF(left, centre_y - height / 2, width, height)


def wizard_large(width: int, height: int) -> bytes:
    """The welcome strip: the positive lockup on white, over a band of the plate gradient."""
    # Format_RGB32 and not ARGB: Inno reads a BMP, and an alpha channel there is a coin flip.
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor(LIGHT.surface))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    band = round(height * BAND_HEIGHT)
    gradient = QLinearGradient(0, height - band, 0, height)
    gradient.setColorAt(0, QColor(LIGHT.primary))
    gradient.setColorAt(1, QColor(LIGHT.primary_active))
    painter.fillRect(QRectF(0, height - band, width, band), gradient)

    logo = _renderer(ASSETS / "logo.svg")
    art = width * LOGO_WIDTH
    logo.render(painter, _fit(logo, (width - art) / 2, height * LOGO_CENTRE, art))
    painter.end()
    return encode(image, "BMP")


def wizard_small(width: int, height: int) -> bytes:
    """The header badge: the plate mark on white, since the header is white on every Inno style."""
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor(LIGHT.surface))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    icon = _renderer(ASSETS / "icon.svg")
    side = min(width, height)
    icon.render(painter, QRectF((width - side) / 2, (height - side) / 2, side, side))
    painter.end()
    return encode(image, "BMP")


def render(svg: Path, height: int) -> tuple[bytes, int, int]:
    """Render one SVG at a given height. Width comes from the viewBox, so a square icon and a
    wide lockup go through the same path with no special case."""
    renderer = _renderer(svg)
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
    return encode(image, "PNG"), width, height


def build_ico(svg: Path) -> bytes:
    """One .ico carrying every shell size. PNG entries, which Windows has read since Vista."""
    images = [render(svg, size)[0] for size in ICO_SIZES]
    directory = b""
    offset = 6 + 16 * len(images)
    for size, data in zip(ICO_SIZES, images, strict=True):
        # 256 is written as 0: the field is one byte and the format says 0 means 256.
        side = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return struct.pack("<HHH", 0, 1, len(images)) + directory + b"".join(images)


class Placar:
    """Grava (ou confere) um arquivo e conta o resultado — a mesma decisão para PNG, ICO e BMP."""

    def __init__(self, conferindo: bool) -> None:
        self.conferindo = conferindo
        self.desatualizados: list[str] = []
        self.gravados = 0
        self.iguais = 0
        self.total = 0

    def por(self, destino: Path, data: bytes) -> str:
        atual = destino.read_bytes() if destino.exists() else None
        self.total += len(data)
        if atual == data:
            self.iguais += 1
            return "inalterado"
        if self.conferindo:
            self.desatualizados.append(destino.name)
            return "DESATUALIZADO" if atual is not None else "FALTANDO"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(data)
        self.gravados += 1
        return "gravado"


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
    print(f"destino: {OUT.relative_to(ROOT)} e {WIZARD.relative_to(ROOT)}{nota}\n")

    placar = Placar(args.check)

    for stem, sizes in JOBS:
        svg = ASSETS / f"{stem}.svg"
        if not svg.exists():
            raise SystemExit(f"ERRO: não encontrei {svg.relative_to(ROOT)}")
        for size in sizes:
            data, width, height = render(svg, size)
            destino = OUT / f"{stem}-{size}.png"
            estado = placar.por(destino, data)
            print(f"  {destino.name:<24} {width:>4}x{height:<4} {len(data):>7} bytes  {estado}")

    # The Windows shell reads .ico and nothing else: a shortcut pointed at a .png silently keeps
    # the launcher stub's own icon, which is how Dito wore the Python one.
    ico = build_ico(ASSETS / "icon.svg")
    estado = placar.por(ICO, ico)
    print(f"  {ICO.name:<24} {'x'.join(str(s) for s in ICO_SIZES[:3])}... "
          f"{len(ico):>7} bytes  {estado}")

    for kind, sizes, draw in (
        ("wizard", WIZARD_LARGE, wizard_large),
        ("wizard-small", WIZARD_SMALL, wizard_small),
    ):
        for width, height in sizes:
            data = draw(width, height)
            destino = WIZARD / f"{kind}-{width}x{height}.bmp"
            estado = placar.por(destino, data)
            print(f"  {destino.name:<24} {width:>4}x{height:<4} {len(data):>7} bytes  {estado}")

    print()
    if args.check:
        if placar.desatualizados:
            print(f"FALHA: {len(placar.desatualizados)} arquivo(s) fora de data: "
                  f"{', '.join(placar.desatualizados)}")
            print("Rode  python tools/gen_icons.py  para regerar.")
            return 1
        print(f"OK: as {placar.iguais} imagens estão em dia ({placar.total} bytes no total).")
        return 0

    print(f"OK: {placar.gravados} gravado(s), {placar.iguais} inalterado(s), "
          f"{placar.total} bytes no total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
