# CHANGELOG — Dito

## 2026-08-15 — interface, marca, reunião no Obsidian e pacote `.deb`

### O quê

1. **Sistema visual** (`ui/theme.py`) — toda cor, espaço, raio, tamanho e duração saem de um lugar
   só. Cor nomeada por PAPEL, então claro e escuro atravessam **sem um `if`** em nenhum widget.
2. **Movimento com mola de verdade** (`ui/spring.py`) — `QPropertyAnimation` interpola entre dois
   pontos num tempo fixo; re-mirar no meio faz ela reiniciar do que ela achar que era o começo,
   que é o salto visível das interfaces desleixadas. Mola só tem valor atual, velocidade e alvo.
3. **A pílula flutuante** (`ui/overlay.py`) — nunca toma foco (o texto vai para o campo onde você
   estava). O alarme é alto em **três canais independentes**: a onda vira linha reta (forma), a
   pílula enche de vermelho (cor) e ela treme uma vez (movimento, que pega visão periférica).
4. **Bandeja, janela e captura de tecla** — nada abre no login; a janela vem do menu ou da
   bandeja, e uma segunda execução do binário fala com a que já roda em vez de criar outra.
5. **Reunião completa** — corta em trechos e transcreve durante, salva texto + Opus em
   `~/Documentos/Dito` e escreve a nota no cofre no formato da skill `reuniao`.
6. **Marca própria** — balão de fala com a onda dentro, e três ícones de bandeja.
7. **Pacote `.deb`** de 111 KB, publicável no `apt.defaltm.com`.

### Decisões de projeto que valem registro

- **`pip install` no `postinst` está fora.** Como root, escreve fora do controle do dpkg, contraria
  a política do Debian, e um `postinst` que falha trava o apt sem nenhuma janela para explicar.
  O bootstrap roda na primeira execução, como usuário, com barra e botão de tentar de novo. E não
  é exigência nova: o app já precisa baixar o modelo de 464 MB no primeiro uso.
- **O `.deb` tem que ser fino** — o Cloudflare Pages, onde o `apt.defaltm.com` mora, **não serve
  arquivo acima de 25 MiB**. Não é preferência, é a hospedagem.
- **Reunião não cola.** Ditado cola onde o cursor está; despejar uma hora de transcrição no campo
  em foco seria uma pequena catástrofe.
- **O Dito não resume.** A nota sai com a transcrição e as seções prontas para preencher.
- **O áudio não entra no cofre por padrão** — é repo git com auto-commit.
- **Reunião não tem limite de tempo** (`max_horas = 0`). No lugar de um teto existe aviso de disco
  cheio, que avisa e nunca interrompe.

### Como foi verificado

**140 testes verdes**, `ruff` limpo. Os que provam algo que não daria para afirmar de outro jeito:

- Contraste **por papel** nos dois temas (4.5 conteúdo, 3.0 dica e contorno de controle).
- O alarme desenha uma **forma diferente**, medido renderizando os dois estados fora da tela.
- Os três ícones de bandeja se distinguem **só pela silhueta a 22 px** (idle×recording 22,5%,
  idle×alert 49,6%, recording×alert 36,2%).
- O chunker empurrando **3 horas** de fala contínua nunca segura mais que 45 s de áudio, e todo
  sample que entra sai exatamente uma vez.
- Cofre inexistente não é criado e a reunião não se perde; biblioteca sem permissão de escrita cai
  na pasta da sessão; assunto `../../etc/passwd` não escapa da pasta.
- Opus medido: WAV 5,7 MB → 519 kB; 3 h ≈ 31 MB. O WAV só é apagado depois de o Opus ser
  **decodificado de volta** e conferido.

### Defeitos encontrados pela própria verificação, antes de sair

- **A trava de instância única do código antigo nunca funcionou.** `voice_type.py:1120` chamava
  `claim_single_instance()` e **descartava o retorno**, então o CPython fechava o socket na hora.
  Provado: o Dito tomou a mesma trava com o ditado antigo rodando, e `ss -x -l` não mostrava o
  nome. Dois ditados sempre puderam rodar juntos colando tudo em dobro.
- **No tema escuro, branco sobre o `danger` media 2,77** — ilegível, no único estado que justifica
  o produto existir. A pílula agora tem superfície própria, igual nos dois temas, medida em 5,18.
- O contorno de controle media 1,95 contra os 3,0 que a WCAG 1.4.11 pede; o cartão media 1,079
  contra a página e não lia como outro plano.
- O `QScrollArea` não herda o fundo da janela e pintava **faixas brancas** entre os cartões.
- Um teste falhava pelo motivo errado: o XTest injeta no servidor X, não num processo, então duas
  execuções simultâneas apertam as teclas uma da outra. Agora há trava entre processos.

### Corrigido no meio do caminho, por medição

Um teste meu estava errado, não o código: âmbar e vermelho diferem **0,19** em razão de contraste,
o que não prova nada — razão de contraste mede só luminância, e matiz não pontua. O teste passou a
medir matiz, e a garantia não-colorida é a onda virando linha reta.

## 2026-08-15 — ditado de ponta a ponta sem interface, com atalho configurável

### O quê

1. **`platform/linux_x11/hotkeys.py`** — segurar-para-falar e alternar-para-reunião.
2. **`core/session.py`** — uma gravação inteira: pré-checagem → captura → disco → alarme →
   transcrição → texto. Ditado transcreve uma vez no fim (beam 5, precisão); reunião corta em
   trechos e transcreve durante (beam 1, sem limite de tempo).
3. **`core/events.py`** — eventos tipados no lugar de tuplas `("preview", str)`.
4. **`output/paste.py`** — clipboard + Ctrl+V com os três tempos que importam.
5. **`dito listen`** — ditado funcionando **sem interface nenhuma**.

### Decisões de projeto que valem registro

- **Disco antes de tudo.** No consumidor de áudio, a primeira coisa que acontece com cada bloco é
  ser escrito. Só depois vêm nível, alarme e transcrição. É o que garante que modelo que não
  carrega, colagem que falha ou processo morto não custem a fala.
- **Contrapressão sem descartar áudio.** Se a transcrição atrasa, o trecho espera na fila e a
  gravação continua. Descartar trecho para acompanhar perderia fala — a única coisa proibida.
- **`transcript.jsonl` cresce durante a reunião.** Morrer no minuto 50 preserva 0–49 em ordem.
- **A tecla de reunião não para no release.** Ela para na **próxima batida** — reunião não tem
  limite de tempo, foi pedido explícito.
- **Colar que falha devolve resultado, não exceção.** Antes, `paste()` estourando (falta de
  `xclip`) perdia o texto e deixava uma linha num log que ninguém lê.

### Como foi verificado

- **Atalhos, contra um servidor X de verdade, com teclas injetadas por XTest:** segurar 1,5 s
  dura 1,81 s (1,5 + 0,30 de carência); toque de 0,15 s dura 0,46 s; o toggle **ignora o release**;
  gerente pausado fica mudo. 29 testes verdes.
- **Cadeia completa headless:** `dito listen --key f7` + F7 sintético segurado por 2 s →
  gravação, transcrição, `session.json` com `state: done` e `audio.wav` com 32000 frames / 2,00 s
  legível por `wave.open()`.
- **Motor:** carga do modelo em 1,07 s do cache, fallback GPU→CPU disparando como projetado,
  **RTF 0,41 com beam=5** (áudio sintético, VAD desligado).

### O que ainda NÃO foi provado

Palavras de verdade saindo certas. A máquina não tem sintetizador de voz, então o último elo
depende de uma voz humana. Tudo antes dele está provado; isso não.

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
