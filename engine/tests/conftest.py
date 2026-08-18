"""Every test runs in a home of its own.

Twice the suite wrote into the owner's real files. First `~/.config/dito/config.toml`, because a
Qt signal persisted the config on every relabel (armadilhas 7.13). Then, the moment sessions moved
into the library, `~/Documentos/Dito` — 38 fixture files filed by date, beside a real recording.

Neither test asked for it. Both were side effects the fixtures could not see, because the paths
are resolved from `$HOME` deep inside the code, far from the test that triggered the write. So the
guard is at the boundary and not in each fixture: `$HOME` and every `XDG_*` point at a temporary
directory for the whole session.

`XAUTHORITY` is deliberately left alone — the x11 tests talk to a real X server, and it is an
absolute path in the environment, not something derived from `$HOME`.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def home_of_its_own(tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    with pytest.MonkeyPatch.context() as env:
        env.setenv("HOME", str(home))
        env.setenv("XDG_CONFIG_HOME", str(home / ".config"))
        env.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
        env.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
        env.setenv("XDG_RUNTIME_DIR", str(home / "run"))
        yield home


@pytest.fixture(autouse=True)
def library_of_its_own(tmp_path, monkeypatch):
    """The library root is `~/Documentos/Dito` by default, which `$HOME` alone already moves —
    this pins it per test as well, so one test's recordings never appear in another's listing."""
    from dito import config as cfgmod

    original = cfgmod.Config.library_dir
    monkeypatch.setattr(
        cfgmod.Config, "library_dir", lambda self: tmp_path / "library", raising=True
    )
    yield tmp_path / "library"
    monkeypatch.setattr(cfgmod.Config, "library_dir", original, raising=True)
