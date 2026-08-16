# Windows — o que falta

Ainda **não existe** build para Windows. Este arquivo é o mapa de quem for fazer: o que já está
pronto no código, o que precisa ser escrito, e as três armadilhas que já custaram depuração e vão
custar de novo se forem ignoradas.

## Estado real, hoje

| | |
|---|---|
| `src/dito/platform/windows/__init__.py` | existe e está **vazio** (0 bytes) — nada portado |
| `src/dito/platform/linux_x11/` | atalhos, `pactl`, `amixer` — tudo específico de Linux |
| `stt/engine.py` | **já se protege**: o `malloc_trim(0)` do unload é pulado quando `sys.platform == "win32"` |
| `pyproject.toml` | **já se protege**: `python-xlib` só é dependência fora do `win32` |
| Trava de instância única | **não existe ainda** em nenhuma das duas plataformas |

Ou seja: o núcleo (áudio, watchdog de nível, writer de WAV, chunker, motor Whisper, colagem) é
portável e não tem nada de X11 dentro. O que falta é uma pasta `platform/windows/` com os mesmos
contratos que `platform/linux_x11/` cumpre.

## O que precisa ser escrito

| Módulo | Contrato a cumprir | Como no Windows |
|---|---|---|
| `hotkeys.py` | `HotkeyManager(on_start, on_stop, grab)` com `HOLD` e `TOGGLE` | `pynput` com `suppress_event` — que **existe** aqui (no X11 não, daí o `XGrabKey`) |
| `audio_system.py` | mute/volume da entrada padrão | não há `pactl`. Ou `pycaw`, ou aceitar que não dá e reportar "não sei" |
| `alsa_mixer.py` | ganho de hardware | não existe equivalente. O watchdog de nível passa a ser o **único** detector |
| trava de instância | um app por vez | mutex nomeado — leia a armadilha abaixo antes de escolher o nome |

O `doctor` e a interface precisam degradar bem quando esses diagnósticos não existem: dizer "não
sei" é correto, inventar não é.

## Empacotar: PyInstaller + Inno Setup

Aqui o raciocínio se inverte em relação ao Linux. No `.deb` o pacote é fino porque o apt entrega o
Qt e o teto do Cloudflare Pages é de 25 MiB. No Windows não há apt: o instalador carrega tudo, fica
na casa das centenas de MB e é distribuído fora do repositório apt — então o teto do Pages não se
aplica, e tentar reproduzir o bootstrap de venv seria complicar de graça.

**PyInstaller** — pontos que não saem de graça:

- `--noconsole` (o app é gráfico), `--name dito`, ícone `.ico` de verdade (não um `.png` renomeado).
- *Hidden imports*: `faster_whisper`, `ctranslate2` e `av` carregam coisa por nome em tempo de
  execução; conte com `--collect-all faster_whisper` e `--collect-binaries ctranslate2`.
- *Data files*: `tokenizers` e `huggingface_hub` levam arquivos que não são `.py`.
- **O modelo NÃO entra no bundle.** São ~486 MB no `small`, ele é baixado no primeiro uso e mora no
  cache do HuggingFace. Empacotá-lo faria um instalador que ninguém baixa.
- Teste o `.exe` numa máquina **sem Python** — é o único teste que vale.

**Inno Setup** — o instalador:

- atalho no Menu Iniciar e (opcional) na Área de Trabalho;
- **"iniciar com o Windows" desmarcado por padrão**, e implementado como valor em
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` ou atalho na pasta `Startup`. O equivalente
  do `.desktop` de autostart do Linux: sobe o daemon **calado**, sem janela. É requisito explícito
  do dono, não detalhe de gosto;
- desinstalador que **não** apague `%LOCALAPPDATA%\dito` — lá estão as gravações e as transcrições,
  igual ao que o `postrm` do `.deb` faz questão de preservar;
- `%APPDATA%`/`%LOCALAPPDATA%` como raiz de config/dados: o `paths.py` hoje é 100% XDG e vai
  precisar de um ramo por plataforma.

## Armadilhas conhecidas

### 1. O mutex `Local\defalt-voice-input` é contrato entre repositórios — não renomeie

O nome é **compartilhado de propósito** com o projeto irmão `defalt` (no Linux é o mesmo nome, como
socket UNIX abstrato). Ele existe para que os dois programas nunca rodem ao mesmo tempo. Renomear de
um lado só faz os dois subirem juntos, brigando pelo microfone e colando cada frase **duas vezes** —
exatamente o bug que a trava existe para impedir.

Parece lixo de código legado. Não é. Ver `docs/armadilhas.md` 5.1.

> Nota honesta: a versão antiga tinha um teste que quebrava se alguém "limpasse" esse nome. **Esse
> teste ainda não foi migrado para este repositório**, e a trava também não. Quem implementar a
> trava traz o teste junto — sem ele, a próxima pessoa a "arrumar" o nome não vai encontrar
> resistência nenhuma.

### 2. As DLLs de cuBLAS: `add_dll_directory` não basta, tem que prefixar o `PATH`

O pip instala as bibliotecas CUDA em `site-packages/nvidia/*/bin` — um lugar onde o Windows não
procura DLL sozinho. E `os.add_dll_directory()` **não resolve**: ele só afeta `LoadLibraryEx` com as
flags de diretório de busca, e o `ctranslate2` resolve o cuBLAS com um `LoadLibrary` simples, que lê
o `PATH` do processo e nada mais.

Então são as duas coisas, antes de importar o `ctranslate2`/`faster_whisper`:

```python
os.add_dll_directory(str(d))
os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]
```

Ver `docs/armadilhas.md` 3.3.

### 3. O erro de cuBLAS só estoura no primeiro encode

Construir o `WhisperModel(device="cuda")` **não toca** em cuBLAS/cuDNN. Com a DLL faltando, o
construtor passa limpo e o erro aparece só na primeira transcrição — quando o fallback para CPU já
não roda mais e a fala do usuário já foi gravada.

O `stt/engine.py` já faz o certo no Linux: força um encode de 1 segundo de zeros logo depois de
construir, dentro do `try`. Esse caminho **precisa continuar valendo** no build do Windows, que é
onde ele foi descoberto. Ver `docs/armadilhas.md` 3.2.

### 4. Nunca transcrever dentro do callback do teclado

O hook de baixo nível fica bloqueado enquanto o callback roda, e o Windows **remove** um listener
que demora a retornar — o atalho simplesmente para de funcionar, sem erro. Todo trabalho pesado vai
para uma fila. Ver `docs/armadilhas.md` 2.7.
