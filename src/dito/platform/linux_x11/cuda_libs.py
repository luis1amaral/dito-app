"""cuBLAS/cuDNN findable on Linux (armadilhas 3.8); own module so Windows never imports it."""

from __future__ import annotations

import ctypes
import glob
import os
import site
import sysconfig

# cudnn depends on cublas, and both on their own _ops/Lt halves: RTLD_GLOBAL is what links them.
_MODE = getattr(ctypes, "RTLD_GLOBAL", 0)

# An allowlist, not *.so*: libnvblas exports sgemm_ and friends and exists to hijack BLAS.
WANTED = ("libcublas*.so*", "libcudnn*.so*", "libnvrtc*.so*")


def _roots() -> list[str]:
    roots = [sysconfig.get_paths()["purelib"], *site.getsitepackages()]
    user_site = site.getusersitepackages()
    if isinstance(user_site, str):
        roots.append(user_site)
    else:
        roots.extend(user_site)
    return list(dict.fromkeys(r for r in roots if r))


def register() -> tuple[list[str], list[str]]:
    """Returns (loaded, failed) basenames; pip puts these where the linker does not look."""
    loaded: list[str] = []
    failed: list[str] = []
    seen: set[str] = set()

    for root in _roots():
        for pattern in WANTED:
            for path in sorted(glob.glob(os.path.join(root, "nvidia", "*", "lib", pattern))):
                name = os.path.basename(path)
                if name in seen or ".alt.so" in name:
                    continue
                seen.add(name)
                try:
                    ctypes.CDLL(path, mode=_MODE)
                except OSError:
                    failed.append(name)
                    continue
                loaded.append(name)

    return loaded, failed
