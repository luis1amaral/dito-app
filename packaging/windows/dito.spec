# -*- mode: python ; coding: utf-8 -*-
# O bundle do Dito para Windows: uma pasta com `dito.exe` (com console, para o terminal) e
# `ditow.exe` (sem console, para o atalho e o autostart) — os mesmos dois nomes do pyproject.
#
#   .venv\Scripts\pyinstaller.exe --noconfirm packaging\windows\dito.spec
#
# Quem monta o instalador é packaging\windows\construir.ps1; este arquivo só faz o bundle.
# O modelo Whisper NÃO entra aqui (486 MB no `small`): é baixado no primeiro uso.
# O porquê de cada linha está em packaging/windows/README.md.

import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs
from PyInstaller.utils.win32 import versioninfo

ROOT = Path(SPECPATH).resolve().parent.parent
SRC = ROOT / "src"
ICON = SRC / "dito" / "ui" / "assets" / "dito.ico"
SCRATCH = ROOT / "build" / "windows"

with open(ROOT / "pyproject.toml", "rb") as _f:
    VERSION = tomllib.load(_f)["project"]["version"]

datas = []
binaries = []
hiddenimports = []

# faster_whisper carrega o Silero VAD de assets/, e onnxruntime tem .pyd e DLLs fora do .py.
for package in ("faster_whisper", "onnxruntime"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# ctranslate2 é um .pyd com 60 MB de DLL ao lado, e nada as importa por nome.
binaries += collect_dynamic_libs("ctranslate2")

# Nenhum dos dois é só .py: tokenizers tem núcleo compilado, huggingface_hub leva dados.
datas += collect_data_files("tokenizers")
datas += collect_data_files("huggingface_hub")

hiddenimports += [
    "av",
    "ctranslate2",
    # faster_whisper/vad.py importa ISTO DENTRO DE UMA FUNÇÃO: a análise estática não acha.
    "onnxruntime",
    # See docs/armadilhas.md 6.5: the tray art is SVG, and no plugin means no tray icon at all.
    "PySide6.QtSvg",
]

# Os .mo NÃO são opcionais: sem eles a interface inteira sai em inglês — foi o defeito da
# primeira instalação de verdade, e tests/test_packaging.py prende os dois empacotamentos.
datas += [
    (str(SRC / "dito" / "locales"), "dito/locales"),
    (str(SRC / "dito" / "ui" / "assets"), "dito/ui/assets"),
]


def version_resource(name: str) -> str:
    """Sem recurso de versão o .exe não tem nome nenhum nas Propriedades do Windows."""
    numbers = tuple(int(part) for part in VERSION.split(".")[:3]) + (0, 0, 0, 0)
    info = versioninfo.VSVersionInfo(
        ffi=versioninfo.FixedFileInfo(filevers=numbers[:4], prodvers=numbers[:4]),
        kids=[
            versioninfo.StringFileInfo([
                versioninfo.StringTable("040904B0", [
                    versioninfo.StringStruct("CompanyName", "Luis Amaral"),
                    versioninfo.StringStruct("FileDescription", "Dito - ditado por voz offline"),
                    versioninfo.StringStruct("FileVersion", VERSION),
                    versioninfo.StringStruct("InternalName", name),
                    versioninfo.StringStruct("LegalCopyright", "Luis Amaral"),
                    versioninfo.StringStruct("OriginalFilename", f"{name}.exe"),
                    versioninfo.StringStruct("ProductName", "Dito"),
                    versioninfo.StringStruct("ProductVersion", VERSION),
                ]),
            ]),
            versioninfo.VarFileInfo([versioninfo.VarStruct("Translation", [0x0409, 1200])]),
        ],
    )
    SCRATCH.mkdir(parents=True, exist_ok=True)
    target = SCRATCH / f"version-{name}.txt"
    target.write_text(str(info), encoding="utf-8")
    return str(target)


a = Analysis(
    [str(Path(SPECPATH) / "entry.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "_pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

# Dois .exe sobre a MESMA análise: um `dito status` no terminal precisa de console, e o atalho
# do Menu Iniciar não pode piscar janela nenhuma no login.
console_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dito",
    console=True,
    icon=str(ICON),
    version=version_resource("dito"),
    debug=False,
    strip=False,
    upx=False,
)

windowed_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ditow",
    console=False,
    icon=str(ICON),
    version=version_resource("ditow"),
    debug=False,
    strip=False,
    upx=False,
)

coll = COLLECT(
    console_exe,
    windowed_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Dito",
)
