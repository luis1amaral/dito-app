"""Making cuBLAS/cuDNN findable on Windows.

pip installs them under `site-packages/nvidia/*/bin`, a directory Windows never searches. And
`os.add_dll_directory` alone does not fix it: that only affects `LoadLibraryEx` calls made with
the search-directory flags, while ctranslate2 resolves cuBLAS with a plain `LoadLibrary`, which
reads `PATH` and nothing else. Both are therefore required.

Kept in its own module so the Linux side never imports it, and so the reason survives — this took
a while to find, and the failure it prevents is a GPU that silently is not used.
"""

from __future__ import annotations

import glob
import os
import site


def register() -> list[str]:
    """Returns the directories that were added, for logging. Safe to call anywhere: on a platform
    without `add_dll_directory` it does nothing."""
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
