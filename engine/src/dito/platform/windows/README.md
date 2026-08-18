# Adaptador do Windows

Escrito e **exercitado numa máquina Windows de verdade** (10 Pro 19045, Python 3.13.3). O que não
foi exercitado está dito na lista do fim — e em `docs/porte-windows.md`.

## Os módulos

| Arquivo | O que faz |
|---|---|
| `hotkeys.py` | atalho global pelo hook de baixo nível do pynput, com `suppress_event()` |
| `instance.py` | mutex nomeado para a trava, e **pipe nomeado** para o canal de controle |
| `audio_system.py` | mudo e volume da entrada padrão por WASAPI, em COM cru por `ctypes` |
| `alsa_mixer.py` | não existe camada equivalente aqui: responde "não dá para checar", honesto |
| `notify.py` | som pelo `winsound`; o toast sai pela bandeja, que `app.py` pluga |
| `focus.py` | `SetForegroundWindow`, com o `AttachThreadInput` que o Windows exige |
| `cuda_dlls.py` | põe as DLLs de cuBLAS onde o Windows procura (armadilha 3.3) |

A máquina de estados hold/toggle **não** está aqui: mora em `platform/hotkeys_core.py`, junto com a
do Linux. Aqui só entra o que muda de plataforma.

## As armadilhas, todas medidas

### 1. `suppress_event()` aborta a conversão do próprio pynput

Ela levanta exceção de dentro do `_convert()`, então o `post` que entregaria o evento ao `on_press`
nunca roda: **suprimir e receber são exclusivos**. Por isso o `win32_event_filter` despacha ele
mesmo — enfileira e só então suprime. Ver `docs/armadilhas.md` 2.12.

### 2. A tecla que você engole SOME do `GetAsyncKeyState`

Medido: F7 engolida pelo nosso hook responde `False` no `GetAsyncKeyState` durante todo o hold; F6
deixada passar responde `True`. No X11 o `XGrabKey` redireciona sem apagar do keymap; no Windows
capturar **é** apagar. Por isso `KeyState.note()` grava o que o hook viu e é ele quem manda.
Ver `docs/armadilhas.md` 2.13.

### 3. Nunca transcrever dentro do callback do teclado

O hook fica bloqueado enquanto o callback roda, e o Windows **remove** um listener lento — o atalho
para de funcionar, sem erro. O filtro só faz um lookup e um `put` na fila. Ver 2.7.

### 4. As DLLs de cuBLAS: `add_dll_directory` não basta

O pip as instala em `site-packages/nvidia/*/bin`, onde o Windows não procura. E
`os.add_dll_directory()` só cobre `LoadLibraryEx` com flags de diretório; o ctranslate2 resolve
cuBLAS com um `LoadLibrary` simples, que lê o `PATH`. São as duas coisas. Ver 3.3.

### 5. O erro de cuBLAS só estoura no primeiro encode

Construir `WhisperModel(device="cuda")` não toca na biblioteca. Sem forçar um encode de 1 s dentro
do `try`, o construtor passa e o erro aparece na primeira transcrição de verdade — quando o
fallback para CPU já não roda mais. Resolvido em `stt/engine.py`, e o fallback foi visto funcionando
aqui (`GPU indisponível (RuntimeError), usando CPU`). Ver 3.2.

### 6. O mutex `Local\defalt-voice-input` é contrato entre repositórios

Compartilhado de propósito com o projeto irmão `defalt`, para que os dois nunca rodem ao mesmo
tempo. Renomear de um lado só faz os dois subirem juntos, brigando pelo microfone e colando cada
frase **duas vezes**. `tests/test_instance_windows.py` trava o nome — o teste que faltava, e que o
README antigo prometia trazer. Ver 5.1 e 5.1b.

### 7. Os wheels já não exigem Python ≤ 3.12

Isto era verdade quando o briefing foi escrito. Hoje `ctranslate2` 4.8.1 e `onnxruntime` 1.28.0 têm
wheel até `cp314`, e `PySide6` 6.11.1 declara `<3.15`. A instalação aqui roda em **3.13.3**.

## O que este diretório ainda não provou

- O **toast** (`notify.py`) não foi visto na tela.
- **`focus.py`** não foi exercitado: devolver o foco depois do cartão de revisão.
- A cadeia inteira com **fala humana**, do F9 até o texto colado.
