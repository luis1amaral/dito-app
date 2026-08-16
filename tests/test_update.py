"""Auto-update: comparar versões, ler o release e recusar o que não tem hash publicado.

A atualização é a única coisa no Dito que baixa um arquivo e depois o EXECUTA. Dois jeitos de isso
dar errado são baratos de prender aqui e caros de descobrir na máquina: comparar versão como
STRING (aí `0.3.10` nunca supera `0.3.9` e a máquina para de atualizar, em silêncio) e rodar um
instalador cujo hash ninguém conferiu.

Nada aqui toca a rede: o `opener` é injetado, então o parsing e a verificação são testáveis sem
depender do GitHub estar de pé.
"""

from __future__ import annotations

import hashlib
import io

import pytest

from dito import update

INSTALLER = "dito-0.4.0-setup.exe"
BASE = "https://example.invalid"


class _Answer:
    def __init__(self, body: bytes) -> None:
        self._body = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body))}

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc) -> bool:
        return False


def opener_for(routes: dict[str, bytes]):
    def opener(request, timeout=None):
        return _Answer(routes[request.full_url])

    return opener


def release_payload(**overrides) -> dict:
    payload = {
        "tag_name": "v0.4.0",
        "name": "Dito 0.4.0",
        "html_url": f"https://github.com/{update.REPO}/releases/tag/v0.4.0",
        "body": "o que mudou",
        "assets": [
            {
                "name": INSTALLER,
                "browser_download_url": f"{BASE}/{INSTALLER}",
                "digest": "sha256:" + "ab" * 32,
            },
            {"name": "SHA256SUMS.txt", "browser_download_url": f"{BASE}/SHA256SUMS.txt"},
        ],
    }
    payload.update(overrides)
    return payload


# ---- comparação de versão ---------------------------------------------------------------


def test_ten_comes_after_nine():
    """O defeito exato: comparar as strings diz que 0.3.10 é MENOR, e a máquina nunca atualiza."""
    assert "0.3.10" < "0.3.9", "se isto mudar, a armadilha sumiu e o teste perdeu a razão de ser"
    assert update.is_newer("0.3.10", "0.3.9")
    assert not update.is_newer("0.3.9", "0.3.10")


def test_the_same_version_is_not_an_update():
    assert not update.is_newer("0.3.10", "0.3.10")


def test_the_v_of_a_git_tag_is_not_part_of_the_version():
    """O release vem taggeado `v0.4.0`; o `dito.__version__` é `0.4.0`. São a mesma coisa."""
    assert not update.is_newer("v0.3.10", "0.3.10")
    assert update.is_newer("v0.4.0", "0.3.10")


def test_a_missing_component_counts_as_zero():
    assert update.is_newer("0.4", "0.3.10")
    assert not update.is_newer("0.4", "0.4.0")


# ---- leitura do release -----------------------------------------------------------------


def test_the_release_gives_the_installer_and_the_hash_it_published():
    release = update.parse_release(release_payload())
    assert release.version == "0.4.0"
    assert release.asset == INSTALLER
    assert release.asset_url == f"{BASE}/{INSTALLER}"
    assert release.sha256 == "ab" * 32


def test_a_release_with_no_installer_says_so_instead_of_guessing():
    """Um release só de código-fonte não é um release de Windows, e baixar o .zip seria pior."""
    release = update.parse_release(release_payload(assets=[]))
    assert release.asset is None and release.asset_url is None


def test_a_digest_that_is_not_sha256_is_thrown_away():
    """Aceitar `md5:` como se fosse sha256 daria um hash que nunca bate — ou pior, que bate."""
    payload = release_payload()
    payload["assets"][0]["digest"] = "md5:" + "ab" * 16
    assert update.parse_release(payload).sha256 is None


def test_check_answers_none_when_this_dito_is_already_the_newest():
    routes = {update.API.format(repo=update.REPO): b'{"tag_name": "v0.1.0", "assets": []}'}
    assert update.check("0.3.10", opener=opener_for(routes)) is None


def test_check_hands_back_the_release_when_there_is_a_newer_one():
    import json

    routes = {update.API.format(repo=update.REPO): json.dumps(release_payload()).encode()}
    release = update.check("0.3.10", opener=opener_for(routes))
    assert release is not None and release.tag == "v0.4.0"


# ---- o hash antes de executar -----------------------------------------------------------


def test_a_download_whose_hash_does_not_match_is_discarded(tmp_path):
    """O teste que existe para não rodar um instalador trocado no caminho."""
    release = update.parse_release(release_payload())
    routes = {f"{BASE}/{INSTALLER}": b"nao sou o instalador"}

    with pytest.raises(update.UpdateError):
        update.download(release, tmp_path, opener=opener_for(routes))

    assert list(tmp_path.iterdir()) == [], "o arquivo reprovado não pode ficar no disco"


def test_a_download_that_matches_is_kept(tmp_path):
    body = b"eu sou o instalador"
    payload = release_payload()
    payload["assets"][0]["digest"] = "sha256:" + hashlib.sha256(body).hexdigest()
    release = update.parse_release(payload)

    saved = update.download(release, tmp_path, opener=opener_for({f"{BASE}/{INSTALLER}": body}))
    assert saved.read_bytes() == body
    assert saved.name == INSTALLER


def test_a_release_with_no_published_hash_is_refused(tmp_path):
    """Falhar fechado: sem hash não se executa nada, mesmo que o download tenha ido bem."""
    payload = release_payload(assets=[
        {"name": INSTALLER, "browser_download_url": f"{BASE}/{INSTALLER}"},
    ])
    release = update.parse_release(payload)

    with pytest.raises(update.UpdateError):
        update.download(release, tmp_path, opener=opener_for({f"{BASE}/{INSTALLER}": b"x"}))


def test_the_checksums_file_answers_when_the_asset_carries_no_digest(tmp_path):
    """Release publicado antes do campo `digest` existir: o SHA256SUMS.txt é o plano B."""
    body = b"eu sou o instalador"
    digest = hashlib.sha256(body).hexdigest()
    payload = release_payload()
    del payload["assets"][0]["digest"]
    release = update.parse_release(payload)

    routes = {
        f"{BASE}/{INSTALLER}": body,
        f"{BASE}/SHA256SUMS.txt": f"{digest}  {INSTALLER}\n".encode(),
    }
    assert update.download(release, tmp_path, opener=opener_for(routes)).read_bytes() == body


def test_a_stale_installer_does_not_pile_up_in_the_state_folder(tmp_path):
    body = b"eu sou o instalador"
    payload = release_payload()
    payload["assets"][0]["digest"] = "sha256:" + hashlib.sha256(body).hexdigest()
    (tmp_path / "dito-0.3.9-setup.exe").write_bytes(b"o de ontem")

    update.download(update.parse_release(payload), tmp_path,
                    opener=opener_for({f"{BASE}/{INSTALLER}": body}))
    assert [p.name for p in tmp_path.iterdir()] == [INSTALLER]


def test_a_download_that_never_ends_is_cut_and_leaves_nothing(tmp_path, monkeypatch):
    """O corte existia, mas apagava o arquivo com o handle ainda aberto: no Windows isso é
    PermissionError, então o usuário via o erro do `unlink` em vez do «parei», e o `.part` ficava
    no disco para sempre. Mesma forma de defeito em platform/windows/cuda_pack.py."""
    monkeypatch.setattr(update, "MAX_INSTALLER_BYTES", 8)
    body = b"grande demais para ser um instalador"
    payload = release_payload()
    payload["assets"][0]["digest"] = "sha256:" + hashlib.sha256(body).hexdigest()

    with pytest.raises(update.UpdateError):
        update.download(update.parse_release(payload), tmp_path,
                        opener=opener_for({f"{BASE}/{INSTALLER}": body}))

    assert list(tmp_path.iterdir()) == [], "o download recusado ficou no disco"


def test_a_pip_install_never_lets_the_installer_run_over_it():
    """`sys.frozen` só existe no .exe; sobre um `pip install` o instalador brigaria com a venv."""
    assert not update.can_apply()
