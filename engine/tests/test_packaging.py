"""What has to travel with the code when it is packaged, and is easy to forget.

The `.deb` never catches these: `make-deb.sh` copies `src/dito` wholesale, so anything the tree
contains arrives whether or not it was declared. A `pip install .` and a PyInstaller bundle ship
only what is declared, and silently drop the rest — the interface came out entirely in English
once for exactly this reason.

The second half of the file guards the Windows installer's two promises: the shortcuts carry the
app's identity, and uninstalling never takes a recording with it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import dito
from dito import i18n

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "windows" / "dito.spec"
ISS = ROOT / "packaging" / "windows" / "dito.iss"


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


# ---- o instalador de distribuição do Windows ---------------------------------------------


def _iss_section(name: str) -> list[str]:
    """As linhas úteis de uma seção do .iss, sem comentário nem linha vazia."""
    lines: list[str] = []
    inside = False
    for raw in ISS.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            inside = line.lower() == f"[{name.lower()}]"
            continue
        if inside and line and not line.startswith(";"):
            lines.append(line)
    return lines


def test_the_pyinstaller_bundle_ships_the_compiled_catalogues():
    """O mesmo defeito do `package-data`, uma camada mais fora: bundle sem `.mo` roda a interface
    inteira em inglês, e nada falha enquanto isso acontece."""
    spec = SPEC.read_text(encoding="utf-8")
    assert '"locales"' in spec and '"dito/locales"' in spec, (
        "o .spec não declara src/dito/locales -> dito/locales: o .exe sai em inglês"
    )


def test_the_bundle_has_a_windowed_twin_and_a_console_one():
    """`ditow.exe` sem console é o que o atalho e o autostart chamam — nada pisca no login."""
    spec = SPEC.read_text(encoding="utf-8")
    assert 'name="ditow"' in spec and "console=False" in spec
    assert 'name="dito"' in spec and "console=True" in spec


def test_the_model_is_not_baked_into_the_bundle():
    """486 MB no `small`: ele é baixado no primeiro uso, e o instalador não pode carregá-lo."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "huggingface/hub" not in spec and "models--" not in spec


def test_every_shortcut_carries_the_app_identity():
    """Sem `System.AppUserModel.ID` no atalho a notificação do Windows se apresenta como
    «Python» — o id no processo sozinho não resolve, o shell lê o do atalho."""
    icons = _iss_section("Icons")
    assert icons, "o .iss não tem seção [Icons]"
    for line in icons:
        assert "AppUserModelID:" in line, f"atalho sem identidade: {line}"


def test_starting_with_windows_comes_checked():
    """É a máquina do dono: um login tem que chegar já ditando. O `instalar.ps1` faz o contrário
    de propósito, e o README explica por que os dois padrões divergem."""
    startup = [t for t in _iss_section("Tasks") if t.startswith("Name: \"startup\"")]
    assert len(startup) == 1, "a tarefa «startup» sumiu do instalador"
    assert "unchecked" not in startup[0]


def test_the_gpu_download_is_offered_but_never_assumed():
    """1,3 GB não se baixa por padrão: quem não tem placa NVIDIA não ganha nada com eles, e o
    .exe é CPU-only por construção — o download é a ÚNICA forma de ter GPU (armadilhas 3.11)."""
    gpu = [t for t in _iss_section("Tasks") if t.startswith('Name: "gpu"')]

    assert len(gpu) == 1, "a tarefa «gpu» sumiu do instalador"
    assert "unchecked" in gpu[0], "a tarefa da GPU vem marcada: 1,3 GB para quem não pediu"
    assert "NVIDIA" in gpu[0], "a caixa não diz para quem serve"


def test_the_download_happens_while_the_wizard_is_still_on_screen():
    """Sem `waituntilterminated` o assistente fecha e o download morre junto, sem avisar ninguém."""
    runs = [r for r in _iss_section("Run") if "gpu --install" in r]

    assert len(runs) == 1, "o instalador não chama «dito gpu --install»"
    assert "waituntilterminated" in runs[0]
    assert "Tasks: gpu" in runs[0], "o download roda mesmo para quem não marcou a caixa"
    # ditow, não dito: um console piscando no meio da instalação é defeito, não diagnóstico.
    assert "ditow.exe" in runs[0]


def test_the_wizard_wears_the_brand():
    """A promessa mais barata de quebrar: renomear um BMP e só descobrir no instalador publicado."""
    text = ISS.read_text(encoding="utf-8-sig")

    assert "WizardImageFile=" in text and "WizardSmallImageFile=" in text
    art = re.findall(r"wizard\\[\w.-]+\.bmp", text)
    assert art, "o .iss não aponta nenhuma imagem de assistente"
    for name in art:
        assert (ISS.parent / name.replace("\\", "/")).exists(), (
            f"{name} não existe — rode python tools/gen_icons.py"
        )


def test_the_wizard_art_stays_out_of_the_bundle():
    """`ui/assets` é copiada inteira para dentro do .exe: um BMP sem compressão lá é peso morto."""
    assert not list((ROOT / "src" / "dito" / "ui" / "assets").rglob("*.bmp"))


def test_the_uninstaller_cannot_delete_a_recording():
    """A única perda irreversível deste programa. O `postrm` do .deb preserva o mesmo no Linux."""
    text = ISS.read_text(encoding="utf-8-sig")
    assert "[UninstallDelete]" not in text, "seção que apagaria arquivo fora do {app}"
    for destructive in ("DelTree", "DeleteFile", "RemoveDir"):
        assert destructive not in text, f"{destructive} no instalador: nada aqui apaga arquivo"
