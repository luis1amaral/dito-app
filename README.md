# Dito

Ditado por voz **offline**. Segure uma tecla, fale, solte: o texto aparece onde o cursor estiver.
Nada sai da máquina — o Whisper roda local.

E, o mais importante: **quando ele não está te ouvindo, ele grita.**

## O problema que este projeto existe para resolver

A versão anterior gravou 99 segundos de fala com o microfone mudo e não avisou nada:

```
transcrevendo 99.2s... (pico=0.0000 rms=0.0000)
  (nada reconhecido)  ← microfone MUDO, nao chegou audio
```

A causa raiz não é um bug de tratamento de erro — é que **não existe erro para tratar**. O
PortAudio não levanta exceção quando a captura morre; ele continua chamando o callback e
entregando zeros. Nenhum `try/except` pega isso. Só o nível do sinal pega.

Daí as duas garantias do Dito:

1. **O alarme é ao vivo, não post-mortem.** Silêncio digital dispara em ~1 s, na tela, com som.
2. **O áudio vai para o disco desde o primeiro bloco.** Se a transcrição falhar, se o modelo não
   carregar, se a colagem falhar — o `.wav` está lá, íntegro e tocável, inclusive depois de um
   `kill -9`.

## Estado

Em construção. O que já está de pé e provado:

| | |
|---|---|
| `dito doctor` | microfone, mute e volume via `pactl`, modelo em cache, configuração |
| `dito selftest` | grava e prova o alarme — `--source zeros` simula o mic mudo sem microfone |
| Watchdog de nível | 16 testes, sem hardware |
| Gravação em disco | WAV válido a qualquer instante, tamanho corrigido a cada fsync |

## Usar em desenvolvimento

```bash
sudo apt install --no-install-recommends \
  python3-pyside6.qtwidgets python3-pyside6.qtsvg python3-tomli-w \
  python3-numpy python3-av python3-onnxruntime python3-pynput python3-pyperclip \
  libportaudio2 pulseaudio-utils xclip

python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/dito doctor
.venv/bin/python -m pytest
```

O `--system-site-packages` não é detalhe: é o que faz o `pip` reaproveitar o Qt, o numpy e o
onnxruntime do apt em vez de baixar ~250 MB de wheels — e é o mesmo arranjo que o `.deb` usa, para
que o que roda aqui seja o que roda instalado.

⚠️ **A venv não é relocável.** O `pyvenv.cfg` e todos os shebangs em `bin/` gravam o caminho
absoluto. Mudou a pasta de lugar, recrie a venv; não adianta mover.

## Os números, e de onde vieram

Nada aqui é chute — tudo foi medido nesta máquina (Ryzen 5 3500X, 6 núcleos, LMDE 7, X11):

| Medida | Valor | Como |
|---|---|---|
| Pico da fala | 0,036 – 0,272 | logs da versão anterior |
| Piso de ruído (H510, sala em silêncio) | 0,0038 | `dito selftest --source mic` |
| Limiar de "sem áudio" | 1e-4 | inalcançável por microfone vivo |
| Limiar de "muito baixo" | 8e-3 | acima do piso, 4,5× abaixo da fala mais fraca |
| `faster-whisper small`, CPU int8 | RTF 0,35–0,45 | 30 s → 10,35 s; 120 s → 53,70 s |

O RTF abaixo de 0,5 é o que torna possível transcrever uma reunião **enquanto** ela é gravada,
em vez de esperar ~25 minutos no fim de uma reunião de uma hora.

## Histórico

Este projeto saiu de `voice_type.py`, um arquivo único de 1136 linhas que vivia em
`~/dev/claude/tools/`. O código foi reestruturado, mas o **conhecimento** foi preservado: cada
correção difícil migrou junto com o comentário que explica por que ela existe (auto-repeat do X11,
release fantasma de teclado sem fio, `Xlib` não ser thread-safe, `malloc_trim` depois do unload).
Está reunido em [`docs/armadilhas.md`](docs/armadilhas.md).

O original permanece recuperável no histórico do repositório `dev`:

```bash
git -C ~/dev show 462877b:claude/tools/voice_type.py
```
