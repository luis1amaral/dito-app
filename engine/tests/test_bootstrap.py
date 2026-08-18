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
    monkeypatch.setattr(bootstrap, "CUDA_DIR", root / "cuda")
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


def test_the_marker_decides_between_files_that_exist(venv, monkeypatch):
    """A .so truncated by two concurrent pips passes an existence test and never retries."""
    _cublas_where_pip_puts_it(venv).write_bytes(b"truncated")
    monkeypatch.setattr(bootstrap, "_adopt_preexisting", lambda: False)
    assert bootstrap.gpu_extras_ready() is False

    bootstrap.GPU_MARK.write_text("ok\n")
    assert bootstrap.gpu_extras_ready() is True


def test_a_marker_that_outlived_its_venv_does_not_pin_the_cpu(venv):
    """Uninstalling keeps the state directory — that is where the recordings are — so the marker
    survived the venv it described. It answered "GPU ready" with no cuBLAS anywhere, the install
    was never retried, and every dictation fell back to the CPU in silence. Seen for real while
    testing a clean reinstall on Windows. See docs/armadilhas.md 3.10."""
    bootstrap.GPU_MARK.write_text("ok\n")

    assert bootstrap.gpu_extras_ready() is False
    assert not bootstrap.GPU_MARK.exists(), "o marcador vencido tem que sair, senão mente de novo"


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
    # Ready means both halves: the library on disk AND the marker that says it loaded (3.10).
    _cublas_where_pip_puts_it(venv).write_bytes(b"")
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


# ---- o caminho do .exe: CUDA sem pip, numa pasta própria ------------------------------

windows_only = pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="o caminho do instalador de Windows"
)


def _pack_where_the_installer_puts_it(root):
    """A pasta que o instalador enche — o mesmo desenho `nvidia/*/bin` que o pip usa no Windows."""
    lib = root / "cuda" / "nvidia" / "cublas" / "bin"
    lib.mkdir(parents=True)
    return lib / "cublas64_12.dll"


@windows_only
def test_the_downloaded_pack_counts_as_cublas_on_disk(venv):
    """Sem isto o marcador seria apagado a cada subida e o instalador rebaixaria 1,3 GB."""
    _pack_where_the_installer_puts_it(venv).write_bytes(b"")

    assert bootstrap.cublas_paths()
    assert bootstrap._cublas_on_disk() is True


@windows_only
def test_the_exe_never_erases_the_marker_the_venv_install_wrote(venv, monkeypatch):
    """`sys.prefix` do .exe é o bundle, que nunca tem cuBLAS: sem esta guarda o .exe apagava o
    marcador da instalação por venv que divide com ele a mesma pasta de estado (3.10)."""
    bootstrap.GPU_MARK.write_text("ok\n")
    monkeypatch.setattr(bootstrap, "frozen", lambda: True)

    assert bootstrap.gpu_extras_ready() is False
    assert bootstrap.GPU_MARK.exists(), "o .exe apagou um marcador que não era dele"


@windows_only
def test_the_pack_marker_is_written_only_after_the_library_proves_it_loads(venv, monkeypatch):
    """«Arquivos chegaram» não é «GPU funciona»: o marcador só vale depois do CDLL passar."""
    from dito.platform.windows import cuda_pack

    monkeypatch.setattr(cuda_pack, "install", lambda *a, **k: [venv / "cuda" / "x.dll"])

    ok, _msg = bootstrap.install_gpu_pack(lambda _m: None)

    assert ok is True
    assert bootstrap.GPU_MARK.exists()


@windows_only
def test_a_pack_that_fails_leaves_no_marker_so_it_retries(venv, monkeypatch):
    from dito.platform.windows import cuda_pack

    def boom(*_a, **_k):
        raise cuda_pack.PackError("o PyPI não respondeu")

    monkeypatch.setattr(cuda_pack, "install", boom)

    ok, message = bootstrap.install_gpu_pack(lambda _m: None)

    assert ok is False
    assert "PyPI" in message
    assert not bootstrap.GPU_MARK.exists()
    assert not bootstrap.GPU_LOCK.exists(), "o lock ficou preso e a próxima tentativa não roda"


@windows_only
def test_two_pack_installs_cannot_run_at_once(venv, monkeypatch):
    """O instalador e um «dito gpu --install» no terminal escrevem na mesma pasta."""
    from dito.platform.windows import cuda_pack

    bootstrap.GPU_LOCK.write_text("")
    monkeypatch.setattr(cuda_pack, "install", lambda *a, **k: pytest.fail("rodou duas vezes"))

    ok, _msg = bootstrap.install_gpu_pack(lambda _m: None)

    assert ok is False


@windows_only
def test_a_full_disk_stops_the_pack_before_the_first_byte(venv, monkeypatch):
    from dito.platform.windows import cuda_pack

    monkeypatch.setattr(bootstrap, "_enough_disk", lambda _where=None: False)
    monkeypatch.setattr(cuda_pack, "install", lambda *a, **k: pytest.fail("começou"))

    ok, message = bootstrap.install_gpu_pack(lambda _m: None)

    assert ok is False
    assert "disk" in message.lower() or "disco" in message.lower()


@windows_only
def test_removing_the_pack_takes_the_marker_with_it(venv):
    """Marcador sem biblioteca é a armadilha 3.10 de novo: responderia «pronto» sobre o nada."""
    _pack_where_the_installer_puts_it(venv).write_bytes(b"")
    bootstrap.GPU_MARK.write_text("ok\n")

    assert bootstrap.remove_gpu_pack() is True
    assert not bootstrap.CUDA_DIR.exists()
    assert not bootstrap.GPU_MARK.exists()


def test_pip_and_the_standalone_pack_ask_for_the_same_cuda():
    """Duas listas de pacotes divergiriam em silêncio, e o .exe rodaria com cuDNN de outra era."""
    assert bootstrap.CUDA_PACKAGES == ("nvidia-cublas-cu12>=12,<13", "nvidia-cudnn-cu12>=9,<10")
    assert [name for name, _major in bootstrap.CUDA_LIBRARIES] == [
        spec.split(">=")[0] for spec in bootstrap.CUDA_PACKAGES
    ]


def test_the_gpu_marker_never_lands_inside_a_repository(tmp_path, monkeypatch):
    """On Windows VENV_DIR is wherever the app runs from, which may be a checkout: the marker
    belongs in the state directory, not next to the source."""
    import sys

    from dito import bootstrap as b

    if sys.platform != "win32":
        pytest.skip("o caminho de Windows")
    assert "state" in b.GPU_MARK.parts
    assert b.GPU_MARK.parent == b.GPU_LOCK.parent
