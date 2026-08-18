"""The «placa de vídeo» box in the installer, and the `dito gpu` command behind it.

The .exe is CPU-only by construction: no CUDA in the bundle and no pip to fetch it. So the choice
moved to install time — a task in dito.iss runs `ditow gpu --install --window`, this module shows
the progress, and platform/windows/cuda_pack.py does the fetching. Measured difference on this
machine: RTF 0.26 on the card against 0.94 on the processor. See docs/armadilhas.md 3.11.
"""

from __future__ import annotations

import sys
import threading

from . import bootstrap
from .i18n import _

MB = 1_000_000


def _mb(value: int) -> int:
    return round(value / MB)


def ready() -> bool:
    return bootstrap.GPU_MARK.exists() and bool(bootstrap.cublas_paths())


def where() -> str:
    found = bootstrap.cublas_paths()
    return str(found[0].parent) if found else ""


def _skip_reason(force: bool) -> str | None:
    """Everything that means «do not download 1.3 GB», in the order that is cheap to ask."""
    if sys.platform != "win32":
        return _("this command is for Windows; on Linux the packages come from apt")
    if ready():
        return _("GPU acceleration is already installed.")
    # Asked last: nvidia-smi wakes a sleeping dGPU on Optimus, so never ask needlessly.
    if not force and not bootstrap.has_nvidia_gpu():
        return _("No NVIDIA card found — nothing was downloaded. Dito will use the processor.")
    return None


def run(install: bool, window: bool, force: bool, remove: bool) -> int:
    if remove:
        gone = bootstrap.remove_gpu_pack()
        print(_("GPU acceleration removed.") if gone else _("there was nothing to remove"))
        return 0

    if not install:
        if ready():
            print(_("GPU acceleration is installed: {path}").format(path=where()))
        else:
            print(_("GPU acceleration is not installed. Run «dito gpu --install»."))
        return 0

    skip = _skip_reason(force)
    if skip is not None:
        _tell(skip, window)
        # Zero on purpose: a machine with no card is not a failed installation.
        return 0

    ok, message = bootstrap.install_gpu_pack(
        say=lambda m: print(f"  {m}", flush=True),
        on_progress=_printing_progress(),
    )
    print(message)
    return 0 if ok else 1


def _tell(message: str, window: bool = False) -> None:
    print(message)


def _printing_progress():
    """One line per 5%: byte-by-byte would flood a redirected console with megabytes of text."""
    last = [-1]

    def report(done: int, total: int) -> None:
        step = int(done * 20 / total) if total else 0
        if step != last[0]:
            last[0] = step
            print(f"  {_mb(done)} MB / {_mb(total)} MB", flush=True)

    return report


