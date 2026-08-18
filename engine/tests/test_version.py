"""The version lives in two files, and only one of them is read at build time.

`packaging/deb/make-deb.sh` reads `pyproject.toml`; `dito --version` prints `__init__.__version__`.
The `.deb` ships no pip metadata (the code is copied to /usr/lib/dito, not pip-installed), so
deriving one from the other at runtime is not available. This is the guard instead: bump one and
the suite says which other file you forgot.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import dito

ROOT = Path(__file__).resolve().parent.parent


def test_the_package_version_matches_the_pyproject():
    with open(ROOT / "pyproject.toml", "rb") as f:
        declared = tomllib.load(f)["project"]["version"]
    assert dito.__version__ == declared
