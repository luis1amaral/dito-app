"""Where things live on each platform, and the environment lie that broke it before.

Both branches are exercised from either OS: `paths` asks `sys.platform` at call time precisely so
that neither branch can rot unseen on the machine that never runs it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dito import paths


@pytest.fixture
def on_windows(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\Tester\AppData\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Tester\AppData\Local")


@pytest.fixture
def on_linux(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
        monkeypatch.delenv(var, raising=False)


def test_windows_splits_roaming_config_from_local_state(on_windows):
    """Config follows the user between machines; recordings and caches must not."""
    assert paths.config_dir().parts[-2:] == ("Roaming", "dito")
    assert paths.data_dir().parts[-2:] == ("Local", "dito")
    assert paths.state_dir() == paths.data_dir() / "state"
    assert paths.runtime_dir() == paths.state_dir()


def test_linux_stays_xdg(on_linux):
    assert paths.config_dir() == Path.home() / ".config" / "dito"
    assert paths.data_dir() == Path.home() / ".local" / "share" / "dito"
    assert paths.state_dir() == Path.home() / ".local" / "state" / "dito"


def test_a_variable_defined_and_empty_does_not_win(on_windows, monkeypatch):
    """See docs/armadilhas.md 5.4: `os.environ.get(var, default)` returns "" and the path becomes
    the current directory. It has to fall back as though the variable were absent."""
    monkeypatch.setenv("APPDATA", "")
    monkeypatch.setenv("LOCALAPPDATA", "   ")

    assert paths.config_dir() == Path.home() / "AppData" / "Roaming" / "dito"
    assert paths.data_dir() == Path.home() / "AppData" / "Local" / "dito"
    assert paths.config_dir().is_absolute()


def test_the_same_lie_on_the_linux_side(on_linux, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "  ")

    assert paths.config_dir() == Path.home() / ".config" / "dito"
    assert paths.runtime_dir() == paths.state_dir()


def test_the_library_is_a_plain_documents_folder(on_windows):
    """Any program can pick it up as context without knowing anything about Dito."""
    library = paths.default_library()
    assert library.name == "Dito"
    assert library.is_absolute()
    assert library.parent == paths.documents_dir()


def test_the_library_is_named_in_portuguese_on_linux(on_linux):
    assert paths.default_library() == Path.home() / "Documentos" / "Dito"


def test_session_layout_is_findable_by_hand():
    from datetime import datetime

    started = datetime(2026, 8, 16, 7, 42, 13)
    assert paths.session_dir(Path("/root"), started).parts[-3:] == ("2026", "08", "16")
    assert paths.session_stem(started) == "07-42-13"
