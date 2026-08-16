# Windows — como se instala

São dois caminhos, e os dois estão em uso: **instalação por script** (`instalar.ps1`, para quem tem
Python e o repositório) e o **instalador de distribuição** (`dito-<versão>-setup.exe`, para máquina
sem Python) — montado por `construir.ps1` e descrito no fim.

## Instalar nesta máquina

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\instalar.ps1
```

| flag | o quê |
|---|---|
| *(nenhuma)* | roda o portão, cria a venv, instala, põe `dito` no PATH e o atalho no Menu Iniciar |
| `-ComWindows` | liga o "iniciar com o Windows" — **desligado por padrão** aqui, ver a nota abaixo |
| `-SemPortao` | pula `ruff` e `pytest` |
| `-Desinstalar` | remove atalhos, PATH e venv — **nunca** as gravações |

O que ele deixa na máquina:

| onde | o quê |
|---|---|
| `%LOCALAPPDATA%\dito\venv` | a venv própria, para o app não depender de onde o repositório está |
| `%LOCALAPPDATA%\dito\bin\dito.cmd` | o shim no PATH do usuário |
| `%LOCALAPPDATA%\dito\state` | estado, `selftest.wav`, marcador da GPU |
| `%APPDATA%\dito\config.toml` | a configuração (roaming: acompanha o usuário) |
| `Documents\Dito` | a biblioteca de gravações — pasta comum de propósito |
| Menu Iniciar → `Dito.lnk` | chama `ditow.exe ui` |

`ditow.exe` é o gêmeo sem console de `dito.exe` (`[project.gui-scripts]` no `pyproject.toml`). O
atalho e o autostart chamam ele, para que nada pisque na tela no login.

**Sobre o padrão do autostart.** Quem roda este script na mão recebe ele **desligado** — instalar um
programa não é autorizá-lo a subir sozinho, e essa é a promessa feita a quem instala. Nas máquinas
do dono é o contrário: o `bootstrap/install.ps1` do repo `dev` passa `-ComWindows`, porque lá o
autostart do Linux já está ligado e um login tem que chegar ditando nos dois sistemas.

**O arquivo `.ps1` é UTF-8 com BOM, e precisa continuar sendo.** Sem o BOM, o Windows PowerShell 5.1
lê como ANSI e todo acento vira lixo na tela — o `pwsh` 7 não mostra o problema.

## O que o desinstalador NÃO apaga

As gravações em `%LOCALAPPDATA%\dito\state` e a biblioteca em `Documents\Dito`, igual ao que o
`postrm` do `.deb` faz questão de preservar no Linux.

## O instalador de distribuição

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1
```

Sai em `build\windows\installer\dito-<versão>-setup.exe`, com o `SHA256SUMS.txt` ao lado — esse
arquivo **não é enfeite**: `src/dito/update.py` se recusa a rodar um instalador sem hash publicado.
`-SemPortao` pula `ruff`/`pytest`, `-SoBundle` para no PyInstaller.

Aqui o raciocínio se inverte em relação ao Linux. No `.deb` o pacote é fino porque o apt entrega o
Qt e o teto do Cloudflare Pages é de 25 MiB. No Windows não há apt: o instalador carrega tudo — mas
**não CUDA**, ver abaixo.

**PyInstaller** (`dito.spec`) — o que não sai de graça:

- dois `.exe` sobre a MESMA análise: `dito.exe` com console (para o terminal) e `ditow.exe` sem
  (para o atalho e o autostart), com ícone `.ico` de verdade (não um `.png` renomeado);
- *hidden imports*: `faster_whisper`, `ctranslate2`, `av` e `onnxruntime` carregam coisa por nome em
  tempo de execução — `onnxruntime` é importado **dentro de uma função** e a análise estática não
  acha. `PySide6.QtSvg` também: sem o plugin não há ícone de bandeja nenhum (armadilha 6.5);
- *data files*: `tokenizers` e `huggingface_hub` levam arquivos que não são `.py`. **E os `.mo` de
  `src/dito/locales`** — ver a armadilha do `package-data` abaixo;
- **o modelo NÃO entra no bundle**: são ~486 MB no `small`, baixado no primeiro uso.

**Inno Setup** (`dito.iss`):

- atalho no Menu Iniciar e (opcional) na Área de Trabalho, cada um com `AppUserModelID` — sem ele a
  notificação do Windows se apresenta como "Python";
- **"iniciar com o Windows" MARCADO** aqui, ao contrário do `instalar.ps1`: quem roda este `.exe` é
  o dono da máquina, e um login tem que chegar já ditando;
- **a caixa da GPU, desmarcada** — ver a seção seguinte;
- imagens do assistente (`WizardImageFile`) em `wizard/`, geradas por `tools/gen_icons.py` dos
  mesmos SVG da marca. **São geradas, não versionadas à mão**: mexeu no SVG, rode o script;
- desinstalador que **não** apaga `%LOCALAPPDATA%\dito` nem `Documents\Dito` — e não apaga arquivo
  nenhum, o que `tests/test_packaging.py` prende.

## A GPU não vem no `.exe`, e é escolha na instalação

O bundle é **CPU-only por construção**: não tem CUDA e não tem `pip` para buscá-lo. Isso não se
conserta com um build melhor — o porquê inteiro está em `docs/armadilhas.md` **3.11**.

A caixa *"Baixar a aceleração por placa de vídeo (1,3 GB)"* roda `ditow.exe gpu --install --window`,
que baixa os wheels do PyPI, confere o `sha256` publicado e extrai só `nvidia/*/bin` para
`%LOCALAPPDATA%\dito\cuda` — **fora do `{app}`**, para sobreviver ao upgrade seguinte.

| comando | o quê |
|---|---|
| `dito gpu` | diz se está instalada e onde |
| `dito gpu --install` | baixa (1,3 GB) e extrai (1,9 GB em disco) |
| `dito gpu --remove` | devolve os 1,9 GB |
| `dito gpu --force` | baixa mesmo sem `nvidia-smi` detectar placa |

Falhar aqui **não reprova a instalação**: aceleração é bônus, e o Dito funciona na CPU.

## A armadilha que a primeira instalação de verdade revelou

`[tool.setuptools.package-data]` listava só `ui/assets/**/*`. Num `pip install .` os catálogos
`locales/**/*.mo` **não iam junto**, e a interface inteira saía em inglês. O `.deb` nunca viu isso
porque `make-deb.sh` copia `src/dito` inteiro com `cp -a`. Corrigido, e travado em
`tests/test_packaging.py` — qualquer empacotamento novo (PyInstaller incluído) tem que levar os
`.mo`.
