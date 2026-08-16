# Windows — como se instala

Hoje existe **instalação por script**, que funciona e está em uso. O **instalador de distribuição**
(um `.exe` para quem não tem Python) ainda não existe — é o que falta, e está desenhado no fim.

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

## O instalador de distribuição, que falta

Aqui o raciocínio se inverte em relação ao Linux. No `.deb` o pacote é fino porque o apt entrega o
Qt e o teto do Cloudflare Pages é de 25 MiB. No Windows não há apt: o instalador carrega tudo, fica
na casa das centenas de MB e é distribuído fora do repositório apt — então o teto do Pages não se
aplica, e reproduzir o bootstrap de venv seria complicar de graça.

**PyInstaller** — o que não sai de graça:

- `--noconsole` (o app é gráfico), `--name dito`, ícone `.ico` de verdade (não um `.png` renomeado);
- *hidden imports*: `faster_whisper`, `ctranslate2` e `av` carregam coisa por nome em tempo de
  execução; conte com `--collect-all faster_whisper` e `--collect-binaries ctranslate2`;
- *data files*: `tokenizers` e `huggingface_hub` levam arquivos que não são `.py`. **E os `.mo` de
  `src/dito/locales`** — ver a armadilha do `package-data` abaixo;
- **o modelo NÃO entra no bundle**: são ~486 MB no `small`, baixado no primeiro uso;
- teste o `.exe` numa máquina **sem Python** — é o único teste que vale.

**Inno Setup** — o instalador:

- atalho no Menu Iniciar e (opcional) na Área de Trabalho;
- **"iniciar com o Windows" desmarcado por padrão**, como atalho na pasta `Startup` chamando
  `dito.exe listen`: sobe o daemon **calado**, sem janela. É requisito explícito do dono;
- desinstalador que **não** apague `%LOCALAPPDATA%\dito` nem `Documents\Dito`.

## A armadilha que a primeira instalação de verdade revelou

`[tool.setuptools.package-data]` listava só `ui/assets/**/*`. Num `pip install .` os catálogos
`locales/**/*.mo` **não iam junto**, e a interface inteira saía em inglês. O `.deb` nunca viu isso
porque `make-deb.sh` copia `src/dito` inteiro com `cp -a`. Corrigido, e travado em
`tests/test_packaging.py` — qualquer empacotamento novo (PyInstaller incluído) tem que levar os
`.mo`.
