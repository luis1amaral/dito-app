# Depuração (Linux) — qual ferramenta abrir primeiro

Roteiro de consulta rápida: dado um sintoma, qual sonda usar e o que o número dela quer dizer.
Detalhe de *por que* cada armadilha existe está em `docs/armadilhas.md` — este arquivo não repete
a causa, só aponta a ferramenta.

## Regra de ouro

**Toda sonda nova passa por um controle conhecido antes de valer como prova, e nenhuma conclusão
vira correção depois de uma medição só — repita.** Um instrumento sem controle mente com cara de
dado. Três vezes em 2026-08-22 (armadilha 5.3):

- **(a) canvas** — "encolher o canvas de 900×900 resolve a lentidão" era artefato: a pílula saía
  para fora da janela encolhida e não havia frame nenhum sendo desenhado.
- **(b) toast** — "o toast some certo" media 0,8 s depois de esconder, o momento errado; com a
  régua certa a base real era 20/20 determinística.
- **(c) janela viva** — a sonda de "nasce morta" (redimensionar e olhar pixel) deu **MORTA também
  para o `xed`**, um editor que sabidamente estava vivo. A sonda é que estava quebrada, não a app.

Antes de confiar num número: rode a mesma sonda contra algo cuja resposta você já sabe (outra
janela comum, um estado que você acabou de forçar) e confira se ela acerta.

## Sintoma → ferramenta

| Sintoma | Ferramenta | Comando |
|---|---|---|
| Interface parada/congelada, sem interação nenhuma | `medir_travamento.py` (modo `observar`) | `python3 tool/medir_travamento.py observar --segundos 30` |
| Suspeita de trava momentânea (some por um instante ao apertar F9 ou fechar o cartão) | `medir_travamento.py` (modo `f9`/`cartao`) | `python3 tool/medir_travamento.py f9 --voltas 10 --pausa 8` |
| Janela abre e fica "congelada" logo no boot (quadro parado, não responde clique) | `medir_nasce_viva.py` — **rode um controle junto** (outra janela) antes de confiar no veredito | `python3 tool/medir_nasce_viva.py build/linux/x64/release/bundle/dito_app 5` |
| Pixel/pílula que fica na tela depois de o app esconder (fantasma) | `pega_fantasma.py` (tocaia ao vivo) ou `repro_toast.py` (reproduz sob controle) | `python3 tool/pega_fantasma.py` |
| App não capta áudio / grava silêncio | `native_engine.log` (rms, "ouviu voz") + reproduzir com `repro_ditado.py` | `tail -f ~/.local/share/dito/logs/native_engine.log` |
| Ditado inteiro para testar sem precisar falar | `repro_ditado.py` (mic virtual + WAV real) | `python3 tool/repro_ditado.py --voltas 3 --tecla alterna` |
| Boot lento | `medir_boot.py` | `python3 tool/medir_boot.py build/linux/x64/release/bundle/dito_app 25` |
| Janela existe mas não recebe clique (ou rouba clique da outra) | `medir_abertura.py` (Bounding × Input, quem ganha o clique) | `python3 tool/medir_abertura.py build/linux/x64/release/bundle/dito_app 25` |
| Foco indo para a janela errada (Enter/Tab escapando do cartão) | `medir_travamento.py` (coluna `ativa`/`_NET_ACTIVE_WINDOW`) + `native.log` (`focus.giveBack`) | `grep focus ~/.local/share/dito/logs/native.log` |
| Antes de publicar qualquer coisa | `regressao.py` (portão único, 10 critérios) | `python3 tool/regressao.py` |
| Suspeita de travamento dentro do próprio Dart (isolate preso, stack de transcrição) | `vmservice.py` — quando existir; fala com o Dart VM Service de um build `profile` (`isolates`, `stack`, `eval`, `frames`, `timeline`) | *(em construção)* |

`medir_travamento.py` aceita `--csv arquivo.csv` em qualquer modo para levar os pings e amostras
brutas para fora e conferir com calma.

## Números de referência (o que é normal)

| Medida | Valor normal |
|---|---|
| Laço GTK parado (ping `_NET_WM_PING`) | ≈ 1,2 ms, p95 1,3 ms |
| Laço GTK gravando (durante captura de áudio) | 58–63 ms |
| Janelas existem após o `exec` (boot) | ≈ 0,7–0,9 s |
| Pílula (HUD mínimo) | 340×56 px |
| Sobreposição (janela cheia, cartão) | 900×900 em `+510+140` |
| Brilho médio do conteúdo — janela principal em tema escuro | ≈ 30 |
| Brilho médio do conteúdo — tela de boot | ≈ 240 |

Fora dessas faixas por uma margem grande é sinal; dentro delas, mesmo que "pareça lento" a olho,
não é — meça de novo antes de investigar.

## Restaurar o ambiente do dono depois de medir

Toda sonda de fora (as que usam `subprocess.Popen` para lançar o app, ou o `MicVirtual`) deixa
rastro. Sempre fechar assim, nesta ordem:

1. **Matar o app pelo PID, nunca por padrão de comando:**
   ```
   pgrep -x dito_app
   kill <pid>
   ```
   **Nunca `pkill -f dito_app`** — o padrão casa com a própria linha de comando do shell/script
   que está rodando a medição e mata o processo errado (ou o próprio terminal).

2. **Devolver a fonte de áudio padrão** (o `MicVirtual` de `repro_ditado.py`/`regressao.py` já faz
   isso sozinho ao sair do `with`; só fazer à mão se o script foi interrompido no meio):
   ```
   pactl set-default-source <fonte-original-do-dono>
   ```

3. **Remover o `null-sink` de teste**, se `pactl list short modules | grep dito_teste` ainda achar
   algo:
   ```
   pactl unload-module <id-do-modulo>
   ```

4. **Conferir que nada de medição ficou vivo:**
   ```
   pgrep -x dito_app; pgrep -f 'tool/medir_\|tool/repro_\|tool/pega_fantasma'
   ```
   Ambos devem voltar vazios (tirando o processo que você queria deixar rodando de propósito).
   `regressao.py` já mata o app sozinho ao final; as sondas de `medir_*`/`pega_fantasma`/
   `repro_*` **não matam** — elas imprimem `pid=... segue rodando` de propósito, para você poder
   inspecionar antes de fechar.

## Onde ficam os logs

`~/.local/share/dito/logs/` — um arquivo por área, todos com timestamp ISO:

| Arquivo | Responde a |
|---|---|
| `app.log` | eventos gerais do app (boot, paste em alto nível) |
| `controller.log` | máquina de estado da gravação — `start aceito`, `stop`, `review descartado` |
| `engine.log` | ciclo de vida do motor Whisper nativo — `motor nativo pronto`, reinícios |
| `native_engine.log` | o que a captura/transcrição viu de verdade — amostras, rms médio/pico, `ouviu voz`, ganho aplicado, texto transcrito |
| `hotkeys.log` | hook de teclado global — tecla desceu/subiu, contagem de eventos do hook X11 |
| `hud_window.log` | sub-janela/HUD — cartão recebido, focado, enviado |
| `crash.log` | stack trace de exceção não tratada no Dart |
| `paste.log` | falha ao colar ou pressionar Enter na janela alvo |
| `native.log` | **novo** — `g_warning`/`g_critical` do plugin C++/GTK, que antes sumia no stderr (ex.: `focus.giveBack: foco nao voltou para o alvo salvo`) |

`grep`/`tail -f` direto nesses arquivos resolve a maioria das dúvidas antes de abrir qualquer sonda
X11 — comece por aqui quando o sintoma já aponta uma área (áudio → `native_engine.log`, foco →
`native.log`, teclas → `hotkeys.log`).
