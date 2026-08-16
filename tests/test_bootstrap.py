"""When the CUDA libraries get downloaded, and every way that must not go wrong.

The driver being installed is not the same as the GPU being usable: cuBLAS and cuDNN are separate
libraries, ~1.5 GB, and without them `device="cuda"` raises and the engine falls back to the CPU
without telling anyone (docs/armadilhas.md 3.8). Each test here stands for a way that download
turned into a defect on somebody else's machine: two pips in one venv, a truncated .so that reads
as "installed" forever, a sleeping dGPU woken for nothing, a disk filled during a meeting.
"""

from __future__ import annotations

import subprocess

import pytest

from dito import bootstrap


@pytest.fixture
def venv(tmp_path, monkeypatch):
    """A venv of our own: the real one may or may not have the libraries installed."""
    root = tmp_path / "dito"
    root.mkdir(parents=True)
    monkeypatch.setattr(bootstrap, "VENV_DIR", root / "venv")
    monkeypatch.setattr(bootstrap, "GPU_MARK", root / "gpu-ready")
    monkeypatch.setattr(bootstrap, "GPU_LOCK", root / "gpu-install.lock")
    return root


class _Pip:
    """Stands in for the pip subprocess, with the returncode the test wants."""

    def __init__(self, code=0):
        self.returncode = code
        self.killed = False

    def communicate(self, timeout=None):
        return ("", "")

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True


def test_the_marker_decides_not_the_file(venv, monkeypatch):
    """A .so truncated by two concurrent pips passes an existence test and never retries."""
    monkeypatch.setattr(bootstrap, "_adopt_preexisting", lambda: False)
    assert bootstrap.gpu_extras_ready() is False

    bootstrap.GPU_MARK.write_text("ok\n")
    assert bootstrap.gpu_extras_ready() is True


def _cublas_where_pip_puts_it(venv_root):
    """Lay the library down exactly where this platform's pip would — see bootstrap.CUBLAS_GLOB."""
    import sys

    if sys.platform == "win32":
        lib = venv_root / "venv" / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin"
        name = "cublas64_12.dll"
    else:
        parts = ("lib", "python3.13", "site-packages", "nvidia", "cublas", "lib")
        lib = venv_root.joinpath("venv", *parts)
        name = "libcublas.so.12"
    lib.mkdir(parents=True)
    return lib / name


def test_libraries_installed_before_the_marker_are_adopted(venv, monkeypatch):
    """Upgrading must not re-download 1.5 GB that is already on disk and loads fine."""
    _cublas_where_pip_puts_it(venv).write_bytes(b"")
    monkeypatch.setattr(bootstrap.ctypes, "CDLL", lambda *a, **k: object())

    assert bootstrap.gpu_extras_ready() is True
    assert bootstrap.GPU_MARK.exists()


def test_a_library_that_does_not_load_is_not_adopted(venv, monkeypatch):
    _cublas_where_pip_puts_it(venv).write_bytes(b"truncated")

    def boom(*_a, **_k):
        raise OSError("file too short")

    monkeypatch.setattr(bootstrap.ctypes, "CDLL", boom)

    assert bootstrap.gpu_extras_ready() is False
    assert not bootstrap.GPU_MARK.exists()


def test_a_ready_install_never_asks_the_card(venv, monkeypatch):
    """nvidia-smi wakes a sleeping dGPU on Optimus: asking it needlessly costs seconds at login."""
    bootstrap.GPU_MARK.write_text("ok\n")
    asked = []
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: asked.append(1) or True)

    assert bootstrap.gpu_extras_missing() is False
    assert asked == []


def test_download_is_due_when_the_card_is_there_and_the_libraries_are_not(venv, monkeypatch):
    monkeypatch.setattr(bootstrap, "_adopt_preexisting", lambda: False)
    monkeypatch.setattr(bootstrap, "has_nvidia_gpu", lambda: True)
    assert bootstrap.gpu_extras_missing() is True


def test_the_marker_is_written_only_when_pip_succeeds(venv, monkeypatch):
    monkeypatch.setattr(bootstrap.subprocess, "Popen", lambda *a, **k: _Pip(0))

    ok, _msg = bootstrap.install_gpu_extras(lambda _m: None)

    assert ok is True
    assert bootstrap.GPU_MARK.exists()


def test_a_failed_pip_leaves_no_marker_so_it_retries(venv, monkeypatch):
    monkeypatch.setattr(bootstrap.subprocess, "Popen", lambda *a, **k: _Pip(1))

    ok, message = bootstrap.install_gpu_extras(lambda _m: None)

    assert ok is False
    assert "CPU" in message
    assert not bootstrap.GPU_MARK.exists()


def test_a_second_install_cannot_start_while_one_is_running(venv, monkeypatch):
    """Two pips in one venv can truncate a .so — the lock is what keeps that impossible."""
    bootstrap.GPU_LOCK.write_text("")
    monkeypatch.setattr(bootstrap.subprocess, "Popen", lambda *a, **k: pytest.fail("ran twice"))

    ok, _msg = bootstrap.install_gpu_extras(lambda _m: None)

    assert ok is False


def test_the_lock_is_released_for_the_next_attempt(venv, monkeypatch):
    monkeypatch.setattr(bootstrap.subprocess, "Popen", lambda *a, **k: _Pip(1))

    bootstrap.install_gpu_extras(lambda _m: None)

    assert not bootstrap.GPU_LOCK.exists()


def test_a_full_disk_stops_before_downloading(venv, monkeypatch):
    """Filling the disk mid-meeting costs recorded audio: refuse rather than start."""
    monkeypatch.setattr(bootstrap, "_enough_disk", lambda: False)
    monkeypatch.setattr(bootstrap.subprocess, "Popen", lambda *a, **k: pytest.fail("started"))

    ok, message = bootstrap.install_gpu_extras(lambda _m: None)

    assert ok is False
    assert "disk" in message.lower() or "disco" in message.lower()


def test_a_hanging_pip_is_killed_not_waited_on(venv, monkeypatch):
    pip = _Pip(0)

    def timeout(*_a, **_k):
        raise subprocess.TimeoutExpired("pip", 1)

    pip.communicate = timeout
    real_kill = []
    pip.kill = lambda: real_kill.append(1)
    monkeypatch.setattr(bootstrap.subprocess, "Popen", lambda *a, **k: pip)
    monkeypatch.setattr(bootstrap.subprocess, "TimeoutExpired", subprocess.TimeoutExpired)

    ok, _msg = bootstrap.install_gpu_extras(lambda _m: None)

    assert ok is False
    assert real_kill == [1]


def test_windows_is_never_headless(monkeypatch):
    """DISPLAY does not exist on Windows, so deciding by it alone sent every Windows run down the
    headless path and the preparation window never appeared. See docs/porte-windows.md."""
    monkeypatch.setattr(bootstrap.sys, "platform", "win32")
    monkeypatch.delenv("DISPLAY", raising=False)

    assert bootstrap.has_display() is True


def test_x11_without_display_still_means_headless(monkeypatch):
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert bootstrap.has_display() is False

    monkeypatch.setenv("DISPLAY", ":0")
    assert bootstrap.has_display() is True


def test_the_cublas_glob_matches_what_pip_lays_down_on_each_platform():
    """The Linux glob found nothing on Windows, so the GPU was never adopted and every dictation
    ran on the CPU — silently, because the engine falls back on its own."""
    import sys

    from dito import bootstrap as b

    if sys.platform == "win32":
        assert b.CUBLAS_GLOB.endswith("cublas64_*.dll")
        assert "Lib/site-packages" in b.CUBLAS_GLOB
        assert b.venv_python().name == "python.exe"
    else:
        assert b.CUBLAS_GLOB.endswith("libcublas.so*")
        assert "lib/python*" in b.CUBLAS_GLOB
        assert b.venv_python().name == "python"


def test_the_gpu_marker_never_lands_inside_a_repository(tmp_path, monkeypatch):
    """On Windows VENV_DIR is wherever the app runs from, which may be a checkout: the marker
    belongs in the state directory, not next to the source."""
    import sys

    from dito import bootstrap as b

    if sys.platform != "win32":
        pytest.skip("o caminho de Windows")
    assert "state" in b.GPU_MARK.parts
    assert b.GPU_MARK.parent == b.GPU_LOCK.parent
