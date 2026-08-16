"""cuBLAS findable on Windows (armadilhas 3.3); own module so the Linux side never imports it."""

from __future__ import annotations

import glob
import os
import site


def register() -> list[str]:
    """Returns the directories added, for logging; a no-op without `add_dll_directory`."""
    if not hasattr(os, "add_dll_directory"):
        return []

    roots = list(site.getsitepackages())
    user_site = site.getusersitepackages()
    if isinstance(user_site, str):
        roots.append(user_site)
    else:
        roots.extend(user_site)

    found: list[str] = []
    for root in roots:
        for path in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            found.append(path)
            try:
                os.add_dll_directory(path)
            except OSError:
                pass

    if found:
        os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")
    return found
