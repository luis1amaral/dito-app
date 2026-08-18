"""The defect this file exists for: Linux was importing the Windows adapter.

`register_cuda_dlls()` imported `platform.windows.cuda_dlls` unconditionally, so on Linux the CUDA
libraries pip installs under site-packages/nvidia/*/lib were never loaded — the dynamic linker does
not look there. Every Linux run fell back to the CPU in silence, because engine.py catches the
failure. It went unnoticed for the life of the project. Nothing in the suite would have caught it,
so this is that test.
"""

from __future__ import annotations

import pytest

from dito.platform.linux_x11 import cuda_libs
from dito.stt import engine


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("linux", "linux"), ("win32", "windows"), ("darwin", "linux")],
)
def test_each_platform_gets_its_own_adapter(monkeypatch, platform, expected):
    called = []
    monkeypatch.setattr(engine.sys, "platform", platform)
    monkeypatch.setattr(cuda_libs, "register", lambda: (called.append("linux"), [], [])[1:])

    import dito.platform.windows.cuda_dlls as win

    monkeypatch.setattr(win, "register", lambda: called.append("windows"))

    engine.register_cuda_dlls()

    assert called == [expected]


def test_the_allowlist_leaves_out_the_blas_hijacker():
    """libnvblas exports sgemm_ and exists to be LD_PRELOADed over BLAS: it is not ours to load."""
    assert not any("nvblas" in pattern for pattern in cuda_libs.WANTED)
    assert any("cublas" in pattern for pattern in cuda_libs.WANTED)
    assert any("cudnn" in pattern for pattern in cuda_libs.WANTED)


def test_register_reports_what_failed(monkeypatch, tmp_path):
    """Zero loaded is the silent-CPU case: the count is the only way anyone can tell."""
    lib = tmp_path / "nvidia" / "cublas" / "lib"
    lib.mkdir(parents=True)
    (lib / "libcublas.so.12").write_bytes(b"")

    def boom(*_a, **_k):
        raise OSError("not a shared object")

    monkeypatch.setattr(cuda_libs, "_roots", lambda: [str(tmp_path)])
    monkeypatch.setattr(cuda_libs.ctypes, "CDLL", boom)

    loaded, failed = cuda_libs.register()

    assert loaded == []
    assert failed == ["libcublas.so.12"]


def test_blocking_sync_is_attempted_before_the_context_exists():
    """CU_CTX_SCHED_BLOCKING_SYNC is refused once CTranslate2 has created the context."""
    assert cuda_libs.CU_CTX_SCHED_BLOCKING_SYNC == 0x04


def test_a_machine_without_libcuda_just_says_no(monkeypatch):
    """No driver is not an error: the engine falls back to the CPU on its own."""
    def boom(*_a, **_k):
        raise OSError("libcuda.so.1: cannot open shared object file")

    monkeypatch.setattr(cuda_libs.ctypes, "CDLL", boom)

    assert cuda_libs.prefer_blocking_sync() is False


def test_openblas_is_pinned_before_numpy_loads():
    """The pool spins after a 3 ms matmul; OpenBLAS reads this once, at import time."""
    import os

    import dito

    assert dito is not None
    assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
    assert os.environ["OMP_NUM_THREADS"] == "1"
