# Empacotamento `.deb`

Gera `dist/dito_<versão>_all.deb` — o pacote que vai para o `apt.defaltm.com`.

```bash
./packaging/deb/make-deb.sh
```

Medido na última rodada: **48 KB** de `.deb`, **312 kB** instalados (ainda sem ícones — quando os
PNGs chegarem em `src/dito/ui/assets/` sobe alguns KB). O teto é 25 MiB e o script **falha** se
passar disso; o porquê está lá embaixo.

O script não pede nada além do que já existe numa máquina Debian: `python3` (3.11+, por causa do
`tomllib`), `dpkg-deb`, `file`. Se o `desktop-file-validate` estiver instalado, ele valida os dois
`.desktop` e aborta se algum estiver malformado.

---

## O tradeoff do pacote fino, com todas as letras

**O Dito não cabe num `.deb` auto-contido, e isso não é preferência — é aritmética.**

O `apt.defaltm.com` é hospedado no Cloudflare Pages, que **recusa servir qualquer arquivo acima de
25 MiB**. Um `.deb` que carregasse o `faster-whisper`, o `ctranslate2` e o Qt passaria de 400 MB:
instalaria bem na sua máquina e **nunca chegaria** a quem baixasse pelo apt. Os três `.deb` que já
estão publicados têm 8–16 MB.

Então o pacote leva **só o código-fonte** e resolve o resto em dois lugares:

| O quê | De onde vem | Quando |
|---|---|---|
| numpy, av, pynput, pyperclip, xlib, tomli-w | `Depends:` do pacote — apt do Debian | na instalação |
| Qt (PySide6), onnxruntime, `faster-whisper`, `sounddevice` | venv em `~/.local/share/dito/venv` | na **primeira execução**, como usuário |
| modelo Whisper (~486 MB no `small`) | HuggingFace, para `~/.cache/huggingface` | no primeiro ditado |

**O que se ganha:** o `.deb` cabe no Pages, atualiza junto com o sistema pelo `apt upgrade`, e o
Qt/numpy/onnxruntime é **um** por máquina em vez de uma cópia por app.

**O que se perde, e vale dizer em voz alta:**

1. **A primeira execução precisa de internet** e demora — pip baixando `ctranslate2` e companhia.
   Depois disso o app é 100% offline, como prometido.
2. **O app depende da versão que o Debian empacota** para numpy e av — hoje numpy 2.2.4. Por isso
   os pisos desses dois no `pyproject.toml` continuam frouxos: apertar faz o pip sombrear o pacote
   do sistema com um wheel do PyPI, e aí o que roda em desenvolvimento deixa de ser o que roda
   instalado. PySide6 e onnxruntime não têm mais esse risco — vêm do PyPI em toda máquina, sempre
   a mesma versão que o `pyproject.toml` pede.
3. **`apt remove` não leva a venv junto.** Ela é dado do usuário, mora no `$HOME` e o dpkg não a
   conhece. O `postrm` avisa e diz o comando.
4. **O bootstrap gráfico perde a janela.** `_run_with_window()` importa `PySide6` no python do
   sistema, que não tem mais Qt instalado por padrão — cai sempre no bootstrap de terminal
   (funciona, só não tem barra de progresso bonita). Sem isso, `python3-pyside6.qtwidgets` e
   `qt6-svg-plugins` simplesmente não existem em nenhuma distro-alvo com base Ubuntu Noble (24.04)
   ou anterior — incluindo Mint 22.x — só chegaram ao apt do Ubuntu no 25.10.

**Se um dia o pacote precisar mesmo ser grande**, o caminho não é espremer o Pages: é publicar num
bucket R2 público, que não tem esse teto. Aí o repositório apt muda de host, não de formato.

### Por que o `pip` não roda no `postinst`

Está proibido, e por três motivos independentes:

- escreve em `/usr` fora do controle do dpkg — o `apt` passa a ter uma visão falsa do disco;
- contraria a política do Debian (script de mantenedor não acessa a rede);
- um `postinst` que falha deixa o pacote **meio-configurado** e o apt travado, sem nenhuma
  interface para explicar o que houve. Numa venv de usuário, a mesma falha é só uma janela com
  mensagem de erro e um botão de tentar de novo.

---

## O que o pacote instala

| Caminho | O quê |
|---|---|
| `/usr/lib/dito/dito/` | o pacote Python inteiro (sem `__pycache__`) |
| `/usr/lib/dito/requirements.lock` | o que a venv precisa instalar — **gerado** do `pyproject.toml` |
| `/usr/bin/dito` | lançador `sh` (não é symlink) |
| `/usr/share/applications/com.defalt.dito.desktop` | item do menu — abre a **janela** |
| `/etc/xdg/autostart/com.defalt.dito-autostart.desktop` | login — sobe o **daemon calado** |
| `/usr/share/icons/hicolor/<n>x<n>/apps/com.defalt.dito.png` | ícone, se houver arte |
| `/usr/share/doc/dito/copyright` | licença |

O código fica em `/usr/lib/dito/dito/` (e não direto em `/usr/lib/dito/`) porque assim
`PYTHONPATH=/usr/lib/dito` basta para o `import dito` funcionar — é tudo o que o lançador faz.

### O lançador `/usr/bin/dito`

É um wrapper e não um symlink porque ele precisa escolher **qual interpretador** roda: o código é
do dpkg, os wheels são do usuário, e alguém tem que costurar os dois.

```
venv existe?  -> exec ~/.local/share/dito/venv/bin/python -m dito "$@"
venv não existe:
   DITO_BOOTSTRAP=never  -> avisa e sai com 0    (é o que o autostart faz)
   existe dito.bootstrap -> python3 -m dito.bootstrap   (janela de progresso)
   senão                 -> venv + pip no terminal      (rede de segurança)
```

O bootstrap gráfico **tenta** rodar no python do sistema: como o Qt agora vem do pip (não mais do
apt), o sistema não tem `PySide6` antes da venv existir, então `_run_with_window()` levanta
`ModuleNotFoundError` e `dito.bootstrap.main()` — que já envolve essa chamada num `except Exception`
— cai sozinho para o bootstrap de terminal, sem janela. Funciona igual, só sem a barra de
progresso gráfica; é o preço direto de tirar o Qt do `Depends:` (ver "o que se perde" acima).

`XDG_DATA_HOME` é lido com `${...:-}` e não `${...-}` de propósito — nesta máquina as variáveis
`XDG_*` estão **definidas e vazias**, e com `-` a venv iria parar num caminho *relativo*, criado
dentro de qualquer pasta em que o lançador tenha sido chamado (a mesma armadilha do
`src/dito/paths.py`, item 5.4 do `docs/armadilhas.md`).

### Contrato com quem está escrevendo a interface

Três nomes que o pacote já assume. Se mudarem, mude junto:

| Nome | Quem usa | O que acontece se não existir |
|---|---|---|
| `dito ui` | `Exec=` do item de menu | o `make-deb.sh` **avisa em toda build**; o menu não abre nada |
| `python3 -m dito.bootstrap` | lançador, quando a venv falta | cai no bootstrap de terminal (funciona, mas sem janela) |
| `DITO_BOOTSTRAP=never` | `Exec=` do autostart | o daemon tentaria baixar wheels no login — o que não pode |

O bootstrap gráfico só precisa fazer duas coisas e sair com 0:
`python3 -m venv --system-site-packages ~/.local/share/dito/venv` e
`<venv>/bin/python -m pip install -r /usr/lib/dito/requirements.lock`. Quem chama de novo o app é
o lançador.

### Menu × autostart

O item do **menu** abre a janela. O de **autostart** roda `dito listen`, que é o daemon sem
interface nenhuma — pedido explícito do dono: *"não quero que quando eu ligo o PC ele já fica
aparecendo"*. Nada é desenhado no login.

O arquivo de autostart **não** tem `NoDisplay=true`: ele mora em `/etc/xdg/autostart`, que nenhum
menu de aplicativos lê, então esconder não ganharia nada — e esconderia a entrada da tela de
"Aplicativos de sessão", que é justamente onde o usuário desliga o daemon sem mexer em `/etc` como
root. Ele está declarado em `conffiles`, então uma edição manual sobrevive ao `apt upgrade`.

Se algum dia o daemon subir antes do PipeWire e perder o microfone, o remendo é
`X-GNOME-Autostart-Delay=5` nesse arquivo. Não foi colocado porque não houve medição que
justificasse.

---

## Dependências, e por que cada uma

Todas conferidas com `apt-cache policy` no Debian 13 (trixie / LMDE 7) antes de entrar no
`control.in`.

| Pacote | Para quê |
|---|---|
| `python3 (>= 3.11)` | o código usa `X \| None`, `tomllib` e `from __future__` novo |
| `python3-venv` | o bootstrap cria a venv (traz `python3-pip-whl`, então a venv já nasce com pip) |
| `python3-numpy` | todo o caminho de áudio |
| `python3-av` | dependência do `faster-whisper` que o apt já tem — evita uma fatia do wheel |
| `python3-pynput` | atalho global |
| `python3-pyperclip`, `xclip \| xsel` | colagem; sem o `xclip` o `pyperclip` levanta exceção e o texto se perde (armadilha 4.4) |
| `python3-xlib` | `query_keymap`, `XGrabKey` — o auto-repeat do X11 (armadilha 2.1) |
| `python3-tomli-w` | grava o `config.toml` |
| `libportaudio2` | o `sounddevice` carrega essa `.so` em tempo de execução |
| `libxcb-cursor0` | o plugin `xcb` do Qt precisa dela pra abrir janela — vinha de graça via `libqt6gui6` enquanto o PySide6 era `Depends:`; virou explícita quando o Qt foi pro pip (armadilha nova: sem ela, "could not load the Qt platform plugin xcb" e o app aborta) |
| `pulseaudio-utils` | `pactl` — mute e volume no `doctor` |
| `alsa-utils` (**Recommends**) | `amixer`, para o ponto cego do ganho de hardware (armadilha 1.2). Sem ele o app funciona e só perde um diagnóstico — por isso não é `Depends` |

Não há `dpkg-shlibdeps` aqui: o pacote é `Architecture: all` e não tem um único ELF para analisar.

O `requirements.lock` é **gerado**, nunca editado à mão: o `make-deb.sh` lê
`[project.dependencies]` do `pyproject.toml` e tira o que os `Depends` já garantem. Hoje sobram
duas linhas (`faster-whisper`, `sounddevice`). Dependência nova cai no lock por padrão — o lado
seguro do erro.

---

## Ícones

O `make-deb.sh` procura em `src/dito/ui/assets/` por `com.defalt.dito*.png`, `icon*.png` e
`dito*.png` (e um `.svg` para `hicolor/scalable`), lê o tamanho de cada um com `file` e instala em
`hicolor/<n>x<n>/apps/`. Nenhum arquivo? Ele **avisa e segue** — o pacote sai sem ícone.

Casar o nome importa: qualquer outro PNG em `assets/` é arte de interface, e promover um glifo
qualquer a ícone do aplicativo seria uma resposta errada dita com confiança.

**O clamp é 512, e não é arredondamento:** o `index.theme` do hicolor declara tamanhos só até
512x512 e o GTK **ignora** diretório que ele não declara. Um PNG de 1024 é instalado e nunca
aparece no menu. Isso já queimou dois projetos desta casa. Arte de 1024 entra como 512 e o GTK
reduz na hora de desenhar.

O script não redimensiona (esta máquina não tem ImageMagick nem rsvg). Para ter as cinco resoluções
de verdade, gere os PNGs já nos tamanhos 48, 64, 128, 256 e 512.

---

## Instalar

```bash
sudo apt install ./dist/dito_0.1.0_all.deb
```

`apt install` e não `dpkg -i`: o `dpkg` não resolve os `Depends` e deixaria o pacote quebrado.

Para conferir antes:

```bash
dpkg-deb -I dist/dito_*.deb     # control, tamanho, scripts
dpkg-deb -c dist/dito_*.deb     # tudo o que vai para o disco
apt-get install -s ./dist/dito_*.deb   # simula, sem instalar nada
```

## Publicar no `apt.defaltm.com`

```bash
~/dev/claude/tools/apt-repo.sh publish
```

Ele varre `~/Desktop/Projetos/**/dist/*.deb`, pega a **maior versão** de cada pacote, assina o
repositório com a chave GPG local e sobe para o Cloudflare Pages. É por isso que o `.deb` tem que
sair em `dist/` na raiz do projeto — e é por isso que o `make-deb.sh` **apaga** um `.deb` que
estoure 25 MiB em vez de só reclamar: deixá-lo ali seria entregá-lo ao próximo `publish`.

Subir versão nova = mudar `version` no `pyproject.toml`, rodar o `make-deb.sh` e publicar. A versão
tem uma fonte só.

## Remover

```bash
sudo apt remove dito     # tira /usr/lib/dito, /usr/bin/dito, .desktop e ícones
sudo apt purge dito      # o mesmo + o autostart em /etc
```

Nenhum dos dois toca em `~/.config/dito`, `~/.local/share/dito` (venv + gravações) ou
`~/.local/state/dito`. O `postrm` imprime o `rm -rf` completo para quem quiser apagar de verdade.
Um daemon que já estava rodando **sobrevive** ao `apt remove` — segue rodando de inodes apagados,
ainda com a tecla capturada; o `prerm` avisa e dá o `pkill`.

## O que ainda não foi provado

- **A instalação de verdade.** O pacote foi construído, inspecionado e a resolução de dependências
  foi simulada (`apt-get -s`, exit 0, 34 pacotes), mas nada foi instalado nesta máquina.
- **O bootstrap baixando os wheels de verdade.** Os quatro caminhos do lançador foram exercitados
  com um `python3` falso (venv presente, `XDG_DATA_HOME` vazia, `DITO_BOOTSTRAP=never`, bootstrap
  ausente/presente/falhando), o que prova o fluxo — não prova o `pip install`.
- **`dito ui`.** O subcomando ainda não existe no `cli.py`; o `make-deb.sh` avisa em toda build.
