"""cuBLAS findable on Windows (armadilhas 3.3); own module so the Linux side never imports it."""

from __future__ import annotations

import glob
import os
import site

from ... import paths


def _roots() -> list[str]:
    """The installer's pack first: the .exe has no site-packages worth reading (armadilhas 3.11)."""
    roots = [str(paths.cuda_dir())]
    roots += list(site.getsitepackages())
    user_site = site.getusersitepackages()
    if isinstance(user_site, str):
        roots.append(user_site)
    else:
        roots.extend(user_site)
    return roots


def add(dirs: list[str]) -> list[str]:
    """Both halves of armadilha 3.3: `add_dll_directory` AND the PATH prefix, never one alone."""
    if not hasattr(os, "add_dll_directory"):
        return []

    for path in dirs:
        try:
            os.add_dll_directory(path)
        except OSError:
            pass

    # Idempotent on purpose: the engine reloads, and a PATH that grows every time is a slow leak.
    current = os.environ.get("PATH", "")
    entries = {p.rstrip("\\") for p in current.split(os.pathsep)}
    missing = [p for p in dirs if p.rstrip("\\") not in entries]
    if missing:
        os.environ["PATH"] = os.pathsep.join(missing) + os.pathsep + current
    return dirs


def register() -> list[str]:
    """Returns the directories added, for logging; a no-op without `add_dll_directory`."""
    found: list[str] = []
    for root in _roots():
        found += glob.glob(os.path.join(root, "nvidia", "*", "bin"))
    return add(found)
