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
# The .exe has no pip, so its CUDA lives beside the state instead of in a venv (armadilhas 3.11).
CUDA_DIR = paths.cuda_dir()
CUDA_PACK_GLOB = "nvidia/cublas/bin/cublas64_*.dll"

# ctranslate2 loads these at runtime; the driver alone is not enough — see docs/armadilhas.md 3.8.
# Pinned by major: a future cuDNN 10 against this ctranslate2 fails as a swallowed RuntimeError.
CUDA_LIBRARIES = (("nvidia-cublas-cu12", 12), ("nvidia-cudnn-cu12", 9))
CUDA_PACKAGES = tuple(f"{name}>={major},<{major + 1}" for name, major in CUDA_LIBRARIES)
GPU_DISK_FLOOR_GB = 5          # 1.3 GB downloaded unpacks to 1.9 GB, and pip needs room to work
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


def cublas_paths() -> list[Path]:
    """Both places it can be: the venv pip filled, and the folder the .exe's installer filled."""
    found = sorted(VENV_DIR.glob(CUBLAS_GLOB))
    if _WINDOWS:
        found += sorted(CUDA_DIR.glob(CUDA_PACK_GLOB))
    return found


def _cublas_on_disk() -> bool:
    return bool(cublas_paths())


def gpu_extras_ready() -> bool:
    """The marker decides among libraries that EXIST — see docs/armadilhas.md 3.10."""
    if not _cublas_on_disk():
        # The venv it described is gone; keeping it would pin the CPU forever, in silence.
        # Not from the .exe though: its `sys.prefix` never holds cuBLAS, so it would erase a
        # marker that describes the venv install sharing this state directory.
        if not frozen():
            GPU_MARK.unlink(missing_ok=True)
        return False
    return GPU_MARK.exists() or _adopt_preexisting()


def _adopt_preexisting() -> bool:
    """Installed before the marker existed: prove it loads, record it, skip a second download."""
    found = cublas_paths()
    if not found:
        return False
    if _WINDOWS:
        # cublas64 pulls cublasLt64 from its own folder, which Windows ignores (armadilhas 3.3).
        from .platform.windows.cuda_dlls import register

        register()
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


def _enough_disk(where: Path | None = None) -> bool:
    target = where or VENV_DIR.parent
    try:
        free = shutil.disk_usage(target if target.exists() else Path.home()).free
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


def install_gpu_pack(say, on_progress=None) -> tuple[bool, str]:
    """The .exe's road to the GPU: no pip, so the wheels are unpacked by hand (armadilhas 3.11)."""
    from .platform.windows import cuda_pack

    if not _enough_disk(CUDA_DIR.parent):
        return False, _("Not enough free disk space for GPU acceleration — Dito will use the CPU.")

    try:
        GPU_LOCK.parent.mkdir(parents=True, exist_ok=True)
        # The same lock as pip's road: two of these racing would truncate a DLL just as well.
        handle = os.open(GPU_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, _("GPU acceleration is already being set up.")
    except OSError:
        return False, _("GPU acceleration unavailable — Dito will use the CPU.")

    try:
        cuda_pack.install(CUDA_LIBRARIES, CUDA_DIR, say, on_progress)
        GPU_MARK.parent.mkdir(parents=True, exist_ok=True)
        # Written last, and only here: the marker means "proved to load", not "files arrived".
        GPU_MARK.write_text("ok\n", encoding="utf-8")
    except (cuda_pack.PackError, OSError) as exc:
        return False, str(exc)
    finally:
        os.close(handle)
        GPU_LOCK.unlink(missing_ok=True)

    return True, _("ready")


def remove_gpu_pack() -> bool:
    """Gives the 1.9 GB back; the marker goes with it or it would pin the CPU in silence (3.10)."""
    from .platform.windows import cuda_pack

    gone = cuda_pack.remove(CUDA_DIR)
    if gone:
        GPU_MARK.unlink(missing_ok=True)
    return gone


def has_display() -> bool:
    """Windows always has a desktop; only on X11 does a missing DISPLAY mean headless."""
    return sys.platform == "win32" or bool(os.environ.get("DISPLAY"))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    setup_language(os.environ.get("DITO_LANG", "auto"))

    if os.environ.get("DITO_BOOTSTRAP") == "never":
        return 0

    if ready():
        return 0

    ok, message = install(progress=lambda m: print(f"  {m}", flush=True))
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
