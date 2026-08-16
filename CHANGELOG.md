# CHANGELOG — Dito

## 2026-08-15 — projeto próprio, e o alarme de microfone mudo funcionando

Primeiro corte do refactor. O ditado sai de um arquivo único de 1136 linhas dentro do repo `dev` e
passa a ser projeto com casa própria.

### O quê

1. **Base do projeto**: pacote `dito` em `src/`, `pyproject.toml`, venv com
   `--system-site-packages` (reaproveita Qt/numpy/onnxruntime do apt em vez de baixar ~250 MB).
2. **`paths.py`** — todo caminho decidido num lugar só, com fallback XDG de verdade. As variáveis
   `XDG_*` nesta máquina estão **definidas e vazias**, e `os.environ.get(var, padrao)` devolveria
   `""` nesse caso: `Path("") / "dito"` é caminho **relativo**, criado dentro do diretório de
   trabalho de quem chamou. `_xdg` trata vazio como ausente.
3. **`config.py`** — dataclasses tipadas ↔ TOML em `~/.config/dito/config.toml`. Escrita atômica
   (`os.replace`), chave desconhecida preservada em vez de apagada, `schema` versionado, e
   configuração ilegível não impede o app de subir (vira `.toml.broken` e os padrões valem).
4. **`audio/level.py` — o alarme.** Watchdog puro, sem thread e sem relógio próprio.
5. **`audio/writer.py`** — WAV escrito desde o primeiro bloco.
6. **`audio/capture.py`** — stream do PortAudio que **lê a flag `status`** (a versão anterior a
   descartava, e todo overflow sumia).
7. **`dito doctor`** e **`dito selftest`** — diagnóstico e prova do alarme.
8. **`platform/linux_x11/audio_system.py`** — mute e volume por `pactl`, sem levantar exceção.

### Por quê

A versão anterior perdeu 99 segundos de fala em silêncio (`pico=0.0000 rms=0.0000`) e só avisou
depois de soltar a tecla. A causa raiz **não é** tratamento de erro faltando: o PortAudio não
levanta exceção quando a captura morre, ele entrega zeros. Não existe exceção para capturar — só o
nível do sinal denuncia. Por isso o watchdog não é um extra, é o motivo do projeto.

### Decisões de projeto que valem registro

- **Dois alarmes, não um.** `DEAD` (silêncio digital, peak < 1e-4) fica **sempre armado**: zeros
  depois de fala real significam dispositivo que morreu no meio da frase. `QUIET` (peak < 8e-3) só
  vale **enquanto nunca chegou som** — depois disso, silêncio é pausa, e avisar seria mentira.
- **O `wave` da stdlib foi descartado de propósito.** Ele só grava os tamanhos no cabeçalho no
  `close()`: um `kill -9` no meio deixa o arquivo declarando **zero frames** e nenhum player abre —
  os bytes estão lá e nada os lê. O cabeçalho de 44 bytes é escrito na mão e os dois campos de
  tamanho são corrigidos a cada flush, então o arquivo é válido **a qualquer instante**.
- **`pactl` dá a mensagem certa; o nível dá a verdade.** O fone declara `HW_MUTE_CTRL`, então o
  mute pelo sistema é detectável e o botão "Desmutar" resolve. Mas fone sem fio pode mutar no
  dongle com o servidor ainda reportando `Mute: no` — que é justamente o caso que queimou. Os dois
  detectores existem; nenhum sozinho basta.

### Como foi verificado

- `pytest`: **16 testes verdes**, sem hardware — o relógio é injetado, então os limiares são
  testáveis sem dormir e sem microfone.
- `dito selftest --source zeros`: alarme **SEM ÁUDIO em 1,03 s** (carência de 300 ms + janela de
  700 ms). Antes: 99 s sem aviso nenhum.
- `dito selftest --source mic`: WAV de 4,00 s gravado; `wave.open()` confirma 64000 frames,
  1 canal, 16 bits — arquivo íntegro **mesmo no caso em que nada foi captado**.
- `dito doctor`: lista as 5 entradas, resolve o `default`, lê mute (`não`) e volume (`100%`) por
  `pactl` e encontra o modelo `small` no cache do HuggingFace.

### Corrigido durante a verificação

O limiar de "muito baixo" nasceu em 4e-3 e o teste com microfone real mostrou o piso de ruído do
H510 numa sala em silêncio em **0,0038** — colado no limiar. Duas correções guiadas pela medição:
o limiar subiu para **8e-3** (acima do piso, ainda 4,5× abaixo da fala mais fraca já registrada,
0,036) e o alarme âmbar passou a ser **condicionado a nunca ter chegado som**. Sem isso, pausar
2,5 s no meio de um ditado acusaria "áudio muito baixo" — falso positivo puro. Travado em
`test_pause_after_speech_does_not_warn`.
