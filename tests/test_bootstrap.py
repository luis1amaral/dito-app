"""When the CUDA libraries get downloaded, and when downloading them would be wrong.

The driver being installed is not the same as the GPU being usable: cuBLAS and cuDNN are separate
libraries, ~1.5 GB, and without them `device="cuda"` raises and the engine falls back to the CPU
without telling anyone (docs/armadilhas.md 3.8). So the download is not optional — it is what makes
the card real. What it must never be is a surprise on a machine that has no card, or a repeat on a
machine that already has the libraries.
"""

from __future__ import annotations

import pytest

from dito import bootstrap


@pytest.fixture
def venv(tmp_path, monkeypatch):
    """A venv of our own: the real one may or may not have the libraries installed."""
    root = tmp_path / "dito"
    monkeypatch.setattr(bootstrap, "VENV_DIR", root / "venv")
    return root


def _with_cublas(venv):
    lib = venv / "venv" / "lib" / "python3.13" / "site-packages" / "nvidia" / "cublas" / "lib"
    lib.mkdir(parents=True)
    (lib / "libcublas.so.12").write_bytes(b"")


def test_extras_are_missing_until_cublas_is_there(venv):
    assert bootstrap.gpu_extras_ready() is False
    _with_cublas(venv)
    assert bootstrap.gpu_extras_ready() is True


def test_nothing_to_download_without_a_card(venv, monkeypatch):
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: False)
    assert bootstrap.gpu_extras_missing() is False


def test_download_is_due_when_the_card_is_there_and_the_libraries_are_not(venv, monkeypatch):
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: True)
    assert bootstrap.gpu_extras_missing() is True


def test_nothing_to_download_once_installed(venv, monkeypatch):
    """1.5 GB is worth downloading once; downloading it every launch is not."""
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: True)
    _with_cublas(venv)
    assert bootstrap.gpu_extras_missing() is False


def test_a_failed_download_reports_instead_of_raising(venv, monkeypatch):
    """Losing acceleration must never cost the user an install that works on the CPU."""
    class Failed:
        returncode = 1

    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: Failed())

    ok, message = bootstrap.install_gpu_extras(lambda _m: None)

    assert ok is False
    assert "CPU" in message


def test_a_download_that_explodes_is_still_only_a_message(venv, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("no network")

    monkeypatch.setattr(bootstrap.subprocess, "run", boom)

    ok, message = bootstrap.install_gpu_extras(lambda _m: None)

    assert ok is False
    assert "CPU" in message
