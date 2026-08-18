"""Baixar 1,3 GB sem pip, e cada jeito de isso dar errado em silêncio.

O `.exe` não carrega CUDA nem `pip`, então o instalador desempacota os wheels do PyPI na mão
(docs/armadilhas.md 3.11). Isso é código que grava DLL a partir de um zip vindo da rede: cada teste
aqui é uma porta que precisa estar fechada — hash que não confere, zip que aponta para fora da
pasta, download que não para de crescer, wheel sem DLL nenhuma.
"""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from pathlib import Path

import pytest

from dito.platform.windows import cuda_pack


def _files(*names: str) -> list[dict]:
    return [
        {"filename": n, "url": f"https://pypi.example/{n}", "hashes": {"sha256": "a" * 64},
         "size": 10}
        for n in names
    ]


def test_the_newest_windows_wheel_of_that_major_wins():
    """`12.10.0` tem que ficar ACIMA de `12.9.2`, e comparar as duas strings inverte isso."""
    chosen = cuda_pack.pick(
        _files(
            "nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl",
            "nvidia_cublas_cu12-12.10.0.1-py3-none-win_amd64.whl",
            "nvidia_cublas_cu12-12.1.0.26-py3-none-win_amd64.whl",
        ),
        12,
    )
    assert chosen is not None
    assert "12.10.0.1" in chosen.name


def test_a_linux_wheel_is_never_picked():
    """O manylinux é maior e mais novo no índice: pegá-lo entrega .so para o Windows carregar."""
    chosen = cuda_pack.pick(
        _files(
            "nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl",
            "nvidia_cublas_cu12-13.0.0.0-py3-none-manylinux2014_x86_64.whl",
        ),
        12,
    )
    assert chosen is not None and chosen.name.endswith("win_amd64.whl")


def test_the_major_is_a_wall_not_a_preference():
    """cuDNN 10 contra este ctranslate2 falha como RuntimeError engolido — armadilhas 3.8."""
    assert cuda_pack.pick(_files("nvidia_cudnn_cu12-10.0.0.1-py3-none-win_amd64.whl"), 9) is None


def test_a_file_with_no_published_hash_is_not_a_candidate():
    """Sem hash não há como recusar um download adulterado, e instalar às cegas não é opção."""
    entry = _files("nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl")[0]
    entry["hashes"] = {}
    assert cuda_pack.pick([entry], 12) is None


# ---- o download -----------------------------------------------------------------------


class _Response:
    def __init__(self, payload: bytes):
        self._stream = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def read(self, n=-1):
        return self._stream.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _serving(payload: bytes):
    return lambda _request, timeout=None: _Response(payload)


def _wheel(payload: bytes, digest: str | None = None) -> cuda_pack.Wheel:
    return cuda_pack.Wheel(
        name="nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl",
        url="https://pypi.example/wheel.whl",
        sha256=digest or hashlib.sha256(payload).hexdigest(),
        size=len(payload),
    )


def test_a_download_that_matches_its_hash_is_kept(tmp_path):
    payload = b"conteudo do wheel"
    got = cuda_pack.fetch(_wheel(payload), tmp_path, opener=_serving(payload))

    assert got.read_bytes() == payload


def test_a_download_whose_hash_differs_is_thrown_away(tmp_path):
    """Falhar fechado: um wheel adulterado vira DLL que o processo carrega com os seus direitos."""
    with pytest.raises(cuda_pack.PackError):
        cuda_pack.fetch(_wheel(b"outra coisa", "b" * 64), tmp_path, opener=_serving(b"outra coisa"))

    assert list(tmp_path.iterdir()) == [], "o arquivo recusado ficou no disco"


def test_a_stream_that_never_ends_is_cut(tmp_path, monkeypatch):
    """Content-Length é o servidor falando; o corte tem que ser contado por nós, ao escrever."""
    monkeypatch.setattr(cuda_pack, "MAX_WHEEL_BYTES", 64)
    payload = b"x" * 4096

    with pytest.raises(cuda_pack.PackError):
        cuda_pack.fetch(_wheel(payload), tmp_path, opener=_serving(payload))

    assert list(tmp_path.iterdir()) == []


def test_the_progress_is_reported_against_the_total_of_every_wheel(tmp_path):
    """A barra atravessa os dois pacotes: reiniciar em 0 no segundo parece travamento."""
    payload = b"y" * 1024
    seen: list[tuple[int, int]] = []

    cuda_pack.fetch(
        _wheel(payload), tmp_path, on_progress=lambda d, t: seen.append((d, t)),
        opener=_serving(payload), done_before=5000, total=9000,
    )

    assert seen and seen[-1] == (5000 + len(payload), 9000)


# ---- a extração -----------------------------------------------------------------------


def _zip(tmp_path: Path, members: dict[str, bytes]) -> Path:
    archive = tmp_path / "wheel.whl"
    with zipfile.ZipFile(archive, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return archive


def test_only_the_dlls_are_unpacked(tmp_path):
    """O wheel traz header e .lib para compilar: peso morto, e mais pasta para o glob varrer."""
    archive = _zip(tmp_path, {
        "nvidia/cublas/bin/cublas64_12.dll": b"dll",
        "nvidia/cublas/include/cublas.h": b"header",
        "nvidia_cublas_cu12-12.9.2.10.dist-info/RECORD": b"meta",
    })
    target = tmp_path / "cuda"

    written = cuda_pack.extract(archive, target)

    assert [p.name for p in written] == ["cublas64_12.dll"]
    assert not (target / "nvidia" / "cublas" / "include").exists()


def test_the_layout_is_the_one_the_dll_search_expects(tmp_path):
    """`cuda_dlls.register()` varre `nvidia/*/bin`: achatar a árvore aqui apaga a aceleração."""
    archive = _zip(tmp_path, {"nvidia/cudnn/bin/cudnn64_9.dll": b"dll"})
    target = tmp_path / "cuda"

    cuda_pack.extract(archive, target)

    assert (target / "nvidia" / "cudnn" / "bin" / "cudnn64_9.dll").exists()
    assert cuda_pack.bin_dirs(target) == [target / "nvidia" / "cudnn" / "bin"]


def test_no_half_written_dll_is_left_behind(tmp_path):
    """Um `.part` sobrando não pode virar DLL: o glob acha o nome e o marcador mente (3.10)."""
    archive = _zip(tmp_path, {"nvidia/cublas/bin/cublas64_12.dll": b"dll"})
    target = tmp_path / "cuda"

    cuda_pack.extract(archive, target)

    assert not list(target.rglob("*.part"))


def test_a_member_that_escapes_the_folder_is_refused(tmp_path):
    """Zip slip: um nome com `..` grava fora da pasta que este módulo é dono de escrever."""
    archive = _zip(tmp_path, {"nvidia/cublas/bin/../../../../evil.dll": b"dll"})

    with pytest.raises(cuda_pack.PackError):
        cuda_pack.extract(archive, tmp_path / "cuda")

    assert not (tmp_path.parent / "evil.dll").exists()


def test_a_wheel_with_no_dll_is_a_failure_not_a_success(tmp_path):
    """Silencioso seria o pior desfecho: marcador escrito, nenhuma DLL, CPU para sempre."""
    archive = _zip(tmp_path, {"nvidia/cublas/include/cublas.h": b"header"})

    with pytest.raises(cuda_pack.PackError):
        cuda_pack.extract(archive, tmp_path / "cuda")


@pytest.mark.skipif(sys.platform != "win32", reason="add_dll_directory só existe no Windows")
def test_the_load_check_is_about_the_folder_it_was_given(tmp_path):
    """`loads()` registrava o caminho GLOBAL e conferia o `target`: com os dois iguais em produção
    ninguém veria, mas a resposta seria sobre outra pasta. cublas64 puxa cublasLt64 da pasta dele,
    e o Windows não olha lá sem registro — armadilhas 3.3."""
    target = tmp_path / "cuda"
    lib = target / "nvidia" / "cublas" / "bin"
    lib.mkdir(parents=True)
    (lib / "cublas64_12.dll").write_bytes(b"nao sou uma dll")

    assert cuda_pack.loads(target) is False, "um arquivo que não carrega não pode passar"
    assert str(lib) in __import__("os").environ["PATH"], "a pasta recebida não foi registrada"


def test_a_folder_with_no_cublas_never_claims_to_load(tmp_path):
    assert cuda_pack.loads(tmp_path / "vazia") is False


def test_removing_gives_the_disk_back(tmp_path):
    target = tmp_path / "cuda"
    (target / "nvidia" / "cublas" / "bin").mkdir(parents=True)
    (target / "nvidia" / "cublas" / "bin" / "cublas64_12.dll").write_bytes(b"dll")

    assert cuda_pack.remove(target) is True
    assert not target.exists()
    assert cuda_pack.remove(target) is False


@pytest.mark.skipif(sys.platform != "win32", reason="o caminho de Windows")
def test_the_pack_folder_is_beside_the_state_and_not_inside_the_install(tmp_path):
    """Instalação sem UAC não pode escrever no bundle, e o `{app}` some no upgrade seguinte."""
    from dito import paths

    assert paths.cuda_dir().parent == paths.data_dir()
    assert paths.cuda_dir().parent == paths.state_dir().parent
