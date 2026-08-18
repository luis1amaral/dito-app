"""Update from this project's GitHub Releases; nothing downloaded runs before its hash matches.

There is no update server and there will not be one: the public GitHub API is the whole backend,
so the only thing that can be tampered with is the download, and that is what the hash guards.
Refusing an update is always safe; running an unverified installer is not — see docs/armadilhas.md
6.7 for what "fail closed" means here.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import __version__, paths
from .i18n import _

REPO = "luis1amaral/dito-app"
# O manifesto vem do dito-api, nao do GitHub: o dito-app e privado e um app distribuido nao
# pode carregar token. O worker devolve o MESMO formato, entao o parsing abaixo nao muda.
API = "https://dito-api.defaltm.com/api/app/latest"

INSTALLER_SUFFIX = ".exe"
CHECKSUMS_ASSET = "SHA256SUMS.txt"
TIMEOUT_S = 20.0
CHUNK = 1 << 16
# The bundle is in the hundreds of MB; anything past this is not our installer, so stop reading.
MAX_INSTALLER_BYTES = 600_000_000

_USER_AGENT = f"dito/{__version__} (+https://github.com/{REPO})"
_NUMBER = re.compile(r"\d+")
_SHA256 = re.compile(r"\b([0-9a-f]{64})\b", re.IGNORECASE)

Opener = Callable[[urllib.request.Request], object]


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    page_url: str
    notes: str
    asset: str | None
    asset_url: str | None
    sha256: str | None
    checksums_url: str | None


def parse_version(text: str) -> tuple[int, int, int]:
    """`0.3.10` has to sort ABOVE `0.3.9`, and comparing the two strings gets that backwards."""
    numbers = [int(n) for n in _NUMBER.findall(text or "")]
    padded = (numbers + [0, 0, 0])[:3]
    return (padded[0], padded[1], padded[2])


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def parse_release(payload: dict, suffix: str = INSTALLER_SUFFIX) -> Release:
    """Reads the release JSON and nothing else — no network, so the parsing is testable alone."""
    tag = str(payload.get("tag_name") or "")
    assets = [a for a in payload.get("assets") or [] if isinstance(a, dict)]

    installer = next(
        (a for a in assets if str(a.get("name", "")).lower().endswith(suffix.lower())), None
    )
    checksums = next((a for a in assets if str(a.get("name", "")) == CHECKSUMS_ASSET), None)

    return Release(
        version=tag.lstrip("vV") or str(payload.get("name") or ""),
        tag=tag,
        page_url=str(payload.get("html_url") or ""),
        notes=str(payload.get("body") or ""),
        asset=str(installer["name"]) if installer else None,
        asset_url=str(installer.get("browser_download_url") or "") or None if installer else None,
        sha256=_digest_field(installer) if installer else None,
        checksums_url=(
            str(checksums.get("browser_download_url") or "") or None if checksums else None
        ),
    )


def _digest_field(asset: dict) -> str | None:
    """GitHub publishes the asset hash as `sha256:<hex>`; older releases carry no field at all."""
    raw = str(asset.get("digest") or "")
    algorithm, _sep, value = raw.partition(":")
    return value.lower() if algorithm.lower() == "sha256" and _SHA256.fullmatch(value) else None


def _open(url: str, opener: Opener | None = None, accept: str = "application/vnd.github+json"):
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": accept}
    )
    try:
        return (opener or urllib.request.urlopen)(request, timeout=TIMEOUT_S)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateError(_("could not reach GitHub: {error}").format(error=exc)) from exc


def latest(repo: str = REPO, opener: Opener | None = None) -> Release:
    with _open(API, opener) as response:
        body = response.read(1 << 20)
    try:
        return parse_release(json.loads(body))
    except (ValueError, TypeError) as exc:
        raise UpdateError(_("GitHub answered something that is not a release")) from exc


def check(
    current: str = __version__, repo: str = REPO, opener: Opener | None = None
) -> Release | None:
    """The newer release, or `None` when this Dito is already it."""
    release = latest(repo, opener)
    return release if is_newer(release.version, current) else None


def download_dir() -> Path:
    return paths.state_dir() / "update"


def published_checksum(release: Release, opener: Opener | None = None) -> str | None:
    """The hash the release itself published, from the asset field or from `SHA256SUMS.txt`."""
    if release.sha256:
        return release.sha256
    if not release.checksums_url or not release.asset:
        return None
    with _open(release.checksums_url, opener, accept="text/plain") as response:
        text = response.read(1 << 20).decode("utf-8", errors="replace")
    for line in text.splitlines():
        if release.asset in line:
            found = _SHA256.search(line)
            if found:
                return found.group(1).lower()
    return None


def download(
    release: Release,
    folder: Path | None = None,
    opener: Opener | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Fetches the installer and returns it only if its sha256 is the published one."""
    if not release.asset or not release.asset_url:
        raise UpdateError(
            _("release {tag} carries no Windows installer").format(tag=release.tag or "?")
        )

    expected = published_checksum(release, opener)
    if not expected:
        # Fail closed: an installer runs with the user's rights, so no hash means no install.
        raise UpdateError(
            _("release {tag} publishes no checksum — refusing to run it").format(
                tag=release.tag or "?"
            )
        )

    folder = folder or download_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for stale in folder.glob(f"*{INSTALLER_SUFFIX}"):
        stale.unlink(missing_ok=True)

    partial = folder / f"{release.asset}.part"
    digest = hashlib.sha256()
    written = 0
    # Raised from INSIDE, deleted from OUTSIDE: Windows refuses to unlink a path whose handle is
    # still open, so the cleanup used to replace the real error and the `.part` stayed on disk.
    try:
        with _open(release.asset_url, opener, accept="application/octet-stream") as response:
            total = int(response.headers.get("Content-Length") or 0) if response.headers else 0
            with open(partial, "wb") as out:
                while chunk := response.read(CHUNK):
                    written += len(chunk)
                    if written > MAX_INSTALLER_BYTES:
                        raise UpdateError(
                            _("the download is far bigger than an installer — stopped")
                        )
                    digest.update(chunk)
                    out.write(chunk)
                    if on_progress is not None:
                        on_progress(written, total)

        if digest.hexdigest() != expected:
            raise UpdateError(_("the checksum does not match — the download was discarded"))
    except BaseException:
        partial.unlink(missing_ok=True)
        raise

    target = folder / release.asset
    partial.replace(target)
    return target


def can_apply() -> bool:
    """Only the frozen .exe replaces itself; over a pip install the installer would fight it."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def install(installer: Path, silent: bool = False) -> None:
    """Hands over and returns: the installer is what closes this Dito and swaps its files."""
    command = [str(installer)]
    if silent:
        command += ["/SILENT", "/NORESTART"]
    flags = 0
    if sys.platform == "win32":
        # Detached, or the installer dies with the Dito it is about to replace.
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(command, close_fds=True, creationflags=flags)
    except OSError as exc:
        raise UpdateError(_("could not start the installer: {error}").format(error=exc)) from exc
