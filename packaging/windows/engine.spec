# -*- mode: python ; coding: utf-8 -*-
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).resolve().parent.parent
SRC = ROOT / "src"
ICON = SRC / "dito" / "ui" / "assets" / "dito.ico"

with open(ROOT / "pyproject.toml", "rb") as _f:
    VERSION = tomllib.load(_f)["project"]["version"]

datas = []
binaries = []
hiddenimports = []

for package in ("faster_whisper", "onnxruntime"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

binaries += collect_dynamic_libs("ctranslate2")
datas += collect_data_files("tokenizers")
datas += collect_data_files("huggingface_hub")

hiddenimports += [
    "av",
    "ctranslate2",
    "onnxruntime",
    "sounddevice",
]

a = Analysis(
    [str(Path(SPECPATH) / "entry_engine.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6", "shiboken6", "tkinter", "pytest", "_pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dito-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="dito-engine",
)
