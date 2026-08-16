"""What has to travel with the code when it is pip-installed, and is easy to forget.

The `.deb` never catches these: `make-deb.sh` copies `src/dito` wholesale, so anything the tree
contains arrives whether or not `package-data` declares it. A `pip install .` — which is how the
Windows install works — ships only what is declared, and silently drops the rest.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import dito
from dito import i18n

ROOT = Path(__file__).resolve().parent.parent


def _package_data() -> list[str]:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["tool"]["setuptools"]["package-data"]["dito"]


def test_the_compiled_catalogues_are_declared_as_package_data():
    """Without this the whole interface came out in English on a pip install, and only there."""
    assert any("locales" in pattern and ".mo" in pattern for pattern in _package_data()), (
        "locales/**/*.mo fora do package-data: a instalação sai em inglês"
    )


def test_the_icons_are_declared_as_package_data():
    assert any("ui/assets" in pattern for pattern in _package_data())


def test_the_catalogue_the_app_loads_actually_exists():
    """`i18n.LOCALES` is resolved from `__file__`, so this also proves the path survives install."""
    catalogue = i18n.LOCALES / "pt_BR" / "LC_MESSAGES" / "dito.mo"
    assert catalogue.exists(), f"catálogo compilado ausente: {catalogue}"
    assert catalogue.stat().st_size > 0


def test_every_entry_point_points_at_something_real():
    """`ditow` is the console-less twin the Start Menu and the autostart entry call."""
    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)["project"]
    targets = {**data.get("scripts", {}), **data.get("gui-scripts", {})}

    assert "dito" in targets and "ditow" in targets
    for name, target in targets.items():
        module, _, function = target.partition(":")
        assert module == "dito.cli", f"{name} aponta para {module}"
        assert hasattr(__import__(module, fromlist=[function]), function)


def test_the_version_is_the_one_the_installer_reports():
    with open(ROOT / "pyproject.toml", "rb") as f:
        assert dito.__version__ == tomllib.load(f)["project"]["version"]
