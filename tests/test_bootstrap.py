"""The GPU offer, and the gap it closes: an install that already works never runs install().

A venv that passes `ready()` returns from `main()` before `install()` is ever called — so the
machine that had Dito working in CPU would keep working in CPU forever after an upgrade, with the
graphics card sitting idle and nothing on screen saying so. The offer is the only path those
installs have, and every guard below exists so it does not become a window on every launch.
"""

from __future__ import annotations

import pytest

from dito import bootstrap


@pytest.fixture
def venv(tmp_path, monkeypatch):
    """A venv of our own: the real one may or may not have the libraries installed."""
    root = tmp_path / "dito"
    monkeypatch.setattr(bootstrap, "VENV_DIR", root / "venv")
    monkeypatch.setattr(bootstrap, "DECLINED", root / "gpu-declined")
    return root


def _with_cublas(venv):
    lib = venv / "venv" / "lib" / "python3.13" / "site-packages" / "nvidia" / "cublas" / "lib"
    lib.mkdir(parents=True)
    (lib / "libcublas.so.12").write_bytes(b"")


def test_extras_are_missing_until_cublas_is_there(venv):
    assert bootstrap.gpu_extras_ready() is False
    _with_cublas(venv)
    assert bootstrap.gpu_extras_ready() is True


def test_no_offer_without_a_card(venv, monkeypatch):
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: False)
    assert bootstrap.gpu_offer_pending() is False


def test_offer_when_the_card_is_there_and_the_libraries_are_not(venv, monkeypatch):
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: True)
    assert bootstrap.gpu_offer_pending() is True


def test_nothing_to_offer_once_the_libraries_are_installed(venv, monkeypatch):
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: True)
    _with_cublas(venv)
    assert bootstrap.gpu_offer_pending() is False


def test_a_no_is_remembered(venv, monkeypatch):
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: True)
    assert bootstrap.gpu_offer_pending() is True

    bootstrap.decline_gpu()

    assert bootstrap.DECLINED.exists()
    assert bootstrap.gpu_offer_pending() is False


def test_headless_never_offers(venv, monkeypatch):
    """1.5 GB needs an answer, and a session with no screen has nobody to give one."""
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: True)
    called = []
    monkeypatch.setattr(bootstrap, "_run_with_window", lambda *a, **k: called.append(1))

    assert bootstrap._offer_gpu(headless=True) == 0
    assert called == []


def test_a_failing_offer_still_lets_the_app_open(venv, monkeypatch):
    """The offer is a bonus; it must never be what stops Dito from starting."""
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: True)

    def boom(*_a, **_k):
        raise RuntimeError("no Qt here")

    monkeypatch.setattr(bootstrap, "_run_with_window", boom)

    assert bootstrap._offer_gpu(headless=False) == 0
