"""CUDA as a plain folder, for the .exe that carries no pip — see docs/armadilhas.md 3.11.

The wheels on PyPI are ordinary zips whose Windows payload is `nvidia/<lib>/bin/*.dll`, so the
installer can lay down exactly what pip would without pip existing. Same discipline as update.py:
the sha256 the index publishes is checked before anything is unpacked, and a mismatch throws the
download away instead of trusting it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...i18n import _

INDEX = "https://pypi.org/simple/{name}/"
INDEX_ACCEPT = "application/vnd.pypi.simple.v1+json"
WHEEL_TAIL = "win_amd64.whl"
TIMEOUT_S = 60.0
CHUNK = 1 << 20
# cuDNN 9.25 is the biggest at 732 MB; twice that is not a wheel we asked for, so stop reading.
MAX_WHEEL_BYTES = 1_600_000_000
# Only the DLLs: the headers and import libraries in the wheel are for compiling, not for running.
PAYLOAD = "/bin/"

Progress = Callable[[int, int], None]
Opener = Callable[[urllib.request.Request], object]


class PackError(RuntimeError):
    pass


@dataclass(frozen=True)
class Wheel:
    name: str
    url: str
    sha256: str
    size: int


def _version(filename: str) -> tuple[int, ...]:
    """`nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl` sorts by its numbers, not its text."""
    parts = filename.split("-")
    if len(parts) < 2:
        return ()
    numbers: list[int] = []
    for piece in parts[1].split("."):
        if not piece.isdigit():
            break
        numbers.append(int(piece))
    return tuple(numbers)


def pick(files: list[dict], major: int) -> Wheel | None:
    """The newest win_amd64 wheel of that major version; no network, so it is testable alone."""
    best: tuple[tuple[int, ...], Wheel] | None = None
    for entry in files:
        name = str(entry.get("filename") or "")
        if not name.endswith(WHEEL_TAIL):
            continue
        version = _version(name)
        if not version or version[0] != major:
            continue
        digest = str((entry.get("hashes") or {}).get("sha256") or "")
        url = str(entry.get("url") or "")
        if not digest or not url:
            continue
        wheel = Wheel(name, url, digest.lower(), int(entry.get("size") or 0))
        if best is None or version > best[0]:
            best = (version, wheel)
    return best[1] if best else None


def _open(url: str, opener: Opener | None, accept: str):
    request = urllib.request.Request(url, headers={"Accept": accept})
    try:
        return (opener or urllib.request.urlopen)(request, timeout=TIMEOUT_S)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise PackError(_("could not reach PyPI: {error}").format(error=exc)) from exc


def resolve(package: str, major: int, opener: Opener | None = None) -> Wheel:
    with _open(INDEX.format(name=package), opener, INDEX_ACCEPT) as response:
        body = response.read(1 << 22)
    try:
        files = json.loads(body).get("files") or []
    except (ValueError, TypeError) as exc:
        raise PackError(_("PyPI answered something that is not an index")) from exc

    wheel = pick(files, major)
    if wheel is None:
        raise PackError(
            _("PyPI has no Windows build of {package} {major}.x").format(
                package=package, major=major
            )
        )
    return wheel


def fetch(
    wheel: Wheel,
    folder: Path,
    on_progress: Progress | None = None,
    opener: Opener | None = None,
    done_before: int = 0,
    total: int = 0,
) -> Path:
    """Downloads one wheel and returns it only when its sha256 is the one PyPI published."""
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / f"{wheel.name}.part"
    digest = hashlib.sha256()
    written = 0

    # Everything that discards the file is raised from INSIDE and deleted from OUTSIDE: Windows
    # refuses to unlink a path whose handle is still open, and the cleanup became the real error.
    try:
        with _open(wheel.url, opener, "application/octet-stream") as response:
            with open(partial, "wb") as out:
                while chunk := response.read(CHUNK):
                    written += len(chunk)
                    if written > MAX_WHEEL_BYTES:
                        raise PackError(_("the download is far bigger than the wheel — stopped"))
                    digest.update(chunk)
                    out.write(chunk)
                    if on_progress is not None:
                        on_progress(done_before + written, total or wheel.size)

        if digest.hexdigest() != wheel.sha256:
            raise PackError(_("the checksum does not match — the download was discarded"))
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return partial


def extract(wheel_file: Path, target: Path) -> list[Path]:
    """Unpacks only `nvidia/*/bin/*`, each file through a `.part` so a crash leaves no half DLL."""
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(wheel_file) as zf:
        for member in zf.infolist():
            if member.is_dir() or PAYLOAD not in member.filename:
                continue
            destination = (target / member.filename).resolve()
            # A zip can name `../..`; refusing beats writing outside the folder we own.
            if not destination.is_relative_to(target.resolve()):
                raise PackError(_("the wheel names a file outside the folder — stopped"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            partial = destination.with_name(destination.name + ".part")
            with zf.open(member) as source, open(partial, "wb") as out:
                shutil.copyfileobj(source, out, CHUNK)
            os.replace(partial, destination)
            written.append(destination)
    if not written:
        raise PackError(_("the wheel carries no DLL — nothing was installed"))
    return written


def bin_dirs(target: Path) -> list[Path]:
    return sorted(p for p in target.glob("nvidia/*/bin") if p.is_dir())


def loads(target: Path) -> bool:
    """Proves the library the engine will ask for actually loads, before anything is marked ready.

    `ctypes.CDLL` alone is not enough: cublas64 pulls cublasLt64 from the same folder, and Windows
    does not look there unless the directory was registered first (docs/armadilhas.md 3.3).
    """
    import ctypes

    from .cuda_dlls import add

    # This folder's own bin dirs, not whatever the global scan finds: the answer has to be about
    # the `target` that was just filled, or a caller with another folder gets a false «yes».
    add([str(p) for p in bin_dirs(target)])
    found = sorted(target.glob("nvidia/cublas/bin/cublas64_*.dll"))
    if not found:
        return False
    try:
        ctypes.CDLL(str(found[0]))
    except OSError:
        return False
    return True


def install(
    packages: tuple[tuple[str, int], ...],
    target: Path,
    say: Callable[[str], None] | None = None,
    on_progress: Progress | None = None,
    opener: Opener | None = None,
) -> list[Path]:
    """Resolves, downloads, verifies and unpacks every package. Raises PackError on any failure."""
    tell = say or (lambda _m: None)

    tell(_("asking PyPI which build to take…"))
    wheels = [resolve(package, major, opener) for package, major in packages]
    total = sum(wheel.size for wheel in wheels)

    staging = target / "download"
    done = 0
    installed: list[Path] = []
    try:
        for wheel in wheels:
            tell(_("downloading {name}…").format(name=wheel.name))
            archive = fetch(wheel, staging, on_progress, opener, done, total)
            done += wheel.size
            tell(_("unpacking {name}…").format(name=wheel.name))
            installed += extract(archive, target)
            # Freed one wheel at a time: holding both costs 1.3 GB of disk for no reason.
            archive.unlink(missing_ok=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if not loads(target):
        raise PackError(_("the libraries were installed but do not load — Dito will use the CPU"))
    return installed


def remove(target: Path) -> bool:
    """Gives the ~1.9 GB back. Only ever the folder this module created, never a recording."""
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True
