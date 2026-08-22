# Prompt para a próxima sessão (contexto limpo)

Cole tudo abaixo da linha como primeira mensagem, com o diretório de trabalho em
`/home/luis/Desktop/Projetos/dito`.

---

Você vai continuar o port Linux do **Dito** (ditado por voz offline, Flutter + C++, em `dito-app/`).
A sessão anterior publicou da 1.4.6 até a **1.6.3**. **Não recomece a investigação.** Leia primeiro,
nesta ordem, e trate como verdade já provada:

1. `dito-app/CHANGELOG.md` — entradas de 2026-08-22 (1.6.2 e 1.6.3) explicam o porquê de cada decisão
   e trazem os números medidos.
2. `dito-app/docs/armadilhas.md` — as regras que não podem ser violadas de novo. **Leia antes de
   tocar em áudio, teclas globais, janelas ou foco.** Preste atenção especial na **5.3**.
3. `dito-app/docs/depuracao.md` — roteiro sintoma → ferramenta. É o atalho para não repetir trabalho.
4. `descobertas/achados-dos-agentes.md` — o que já foi corrigido (✅) e o que segue aberto (⬜).

## Como trabalhar aqui (não negociável)

- **Nunca chute.** Prove a causa com evidência (ler o arquivo, rodar o comando, ver o log e o exit
  code) antes de afirmar. Sem evidência: diga "ainda não sei — vou verificar".
- **Toda sonda nova passa por um controle conhecido antes de valer como prova.** Isto não é
  formalidade: em 2026-08-22, **três** instrumentos deram resposta errada e quase levaram a correções
  no lugar errado (armadilha 5.3). Um deles só foi desmascarado ao rodar a mesma sonda contra o
  `xed`, que estava vivo e recebeu o veredito "morta".
- **Nunca corrija sem número.** Naquele dia foram escritas três correções especulativas, todas
  revertidas.
- **NÃO invente problema que o dono não tem.** Isso aconteceu: uma auditoria apontou que a pílula usa
  o monitor primário em vez do monitor em foco, eu mandei corrigir sem perguntar, e o dono respondeu
  que **está do jeito que ele quer**. A mudança foi revertida. Antes de corrigir "defeito" achado por
  auditoria, **pergunte se incomoda**.
- **Portão obrigatório:** `cd dito-app && python3 tool/regressao.py` (11 critérios) e, no mínimo,
  `flutter analyze && flutter test` (219 testes hoje). Nada fecha sem isso verde.
- **Registrar:** toda mudança de comportamento entra no `dito-app/CHANGELOG.md` (o quê + por quê +
  **os números**), e toda armadilha nova em `dito-app/docs/armadilhas.md`.
- **Publicar:** `bash dito-app/packaging/linux/construir.sh` e depois
  `bash ~/dev/claude/tools/apt-repo.sh publish`. O dono atualiza com
  `sudo apt update && sudo apt upgrade` e **precisa reabrir o Dito**.
- **Subagentes:** só em `sonnet` (nunca `opus`, `fable`, `inherit` nem `fork`), **um dono por
  arquivo**, e eles **não rodam o portão** — quem orquestra roda, senão vários `flutter test`
  disputam o `.dart_tool`.
- **Nunca** `pkill -f <padrão>` nem `pkill -x bash`: casa com o próprio shell e o mata (aconteceu
  três vezes em 2026-08-22). Matar por PID: `for p in $(pgrep -x dito_app); do kill "$p"; done`.
- **Ordem importa no portão:** o critério que mede a abertura da janela roda **antes** de qualquer
  F9, porque a tecla destrava e mascara o defeito. Não reordene.
- Ao terminar de medir, **devolva o ambiente do dono**: fonte de áudio padrão, sem `null-sink` de
  teste, sem processo de medição vivo.

## Ferramentas que já existem (use, não reescreva)

Em `dito-app/tool/`. `docs/depuracao.md` diz qual usar para cada sintoma.

| ferramenta | para quê |
|---|---|
| `regressao.py` | **o portão**: 11 critérios, veredito PASSA/FALHA, exit code |
| `medir_travamento.py` | sonda `_NET_WM_PING` (laço GTK em ms), forma da janela, syscall da thread |
| `medir_abertura.py` | acha as janelas (inclusive reparenteadas), as duas formas de recorte, quem recebe o clique |
| `repro_ditado.py` | **ditado completo sem falar**: microfone virtual + WAV com fala real + cartão + Tab/Enter |
| `pega_fantasma.py` | tocaia para pixel que fica na tela depois de esconder |
| `vmservice.py` | cliente do Dart VM Service (build `profile`): `isolates`, `stack`, `eval`, `frames`, `timeline` |
| `medir_boot.py`, `medir_nasce_viva.py`, `flagra.py` | boot, janela nascendo viva, despejo de estado no flagrante |

Diagnóstico dentro do app: **`DITO_DIAG=1`** faz o `ValueListenableBuilder` do `main_window.dart`
registrar no log o que ele realmente vê. Foi ele que resolveu em uma linha o que oito sondas de pixel
não resolveram.

Números de referência: laço GTK parado ≈ **1,2 ms**; gravando **58-63 ms**; boot com janelas em
~0,7-0,9 s; pílula **340×56 px**; sobreposição **900×900 em +510+140**; conteúdo da janela principal
em tema escuro tem brilho médio ≈ **30**, a tela de boot ≈ **240**.

---

# O que fazer nesta sessão

## 1. PRIORIDADE — "abro o Dito e a interface fica congelada em Iniciando… até eu dar F9"

É o defeito mais antigo do port (já aparece no `CHANGELOG.md` da 1.6.1) e o único que ainda incomoda
o dono. **Não está resolvido.**

### O que está PROVADO (não repetir estas medições)

```
isReady = true                -> widget marcado como sujo        [log DITO_DIAG, 09:59:20.077]
janela escondida              -> Flutter nao produz frame,
                                 o rebuild fica pendurado na fila
clique na bandeja             -> o rebuild RODA de verdade       [09:59:33.389 ready=true, MESMO hash]
...mas nenhum frame sai       -> 0 pixels mudados em 600 ms
qualquer tecla global         -> 668.786 pixels mudam de uma vez [F9 e F10, ambos]
```

**A árvore de widgets está correta. O motor é que não apresenta.** Uma instância só (hash do
`ValueNotifier` idêntico nos dois lados do log).

### Hipóteses já DERRUBADAS, com o dado que as matou

| hipótese | como caiu |
|---|---|
| ciclo de vida / `framesEnabled` | o embedder Linux só emite `hidden` em `WITHDRAWN`/`ICONIFIED` (`fl_window_state_monitor.cc:51-80`); com a janela visível nunca dispara |
| `deferFirstFrame` pendente | a tela de boot já foi desenhada, logo `_firstFrameSent` já é `true` (`rendering/binding.dart:591,601`) |
| frame preso por `_hasScheduledFrame` | a timeline do VM Service mostrou **166 `Frame` + 166 `PlatformVsync` em 5 s** — o motor entregava vsync |
| desmapear (armadilha 4.3 na principal) | com `--janela`, janela sempre visível, também ficou em "Iniciando…" |
| acordar o laço GLib (`g_idle_add` + `gtk_widget_queue_draw` + `gdk_window_invalidate_rect`) | implementado como `window.wakeEngine` e medido: **5/5 ainda congeladas**. Revertido. |
| mensagem nativo→Dart genérica | clicar outro item da bandeja (mesmo `FlEventChannel` da tecla) **não** destrava; F10 logo depois destrava |
| forçar repintura pelo Dart | `markNeedsPaint`, `handleMetricsChanged`, `scheduleForcedFrame`, `reassembleApplication`, redimensionar (1/5/40 px), mover o mouse, clicar, alternar o próprio `ValueNotifier` — **nenhum** produz frame |
| tempo escondido | escondido por 2 s, 15 s e 40 s: **0/3 congelaram** |
| carga de CPU | com os 6 núcleos saturados: **0/4 congelaram** |

### AVISO CRÍTICO — o defeito é INTERMITENTE e não há gatilho confiável

No fim da sessão ele **parou de reproduzir**. As mesmas sequências que de manhã davam 5/5 congeladas
passaram a dar 0/5, 0/3 e 0/4. **Não descobri o que muda.** Consequência prática, e é séria:

> **O critério `abre com conteudo` do `tool/regressao.py` PASSA hoje. Ele NÃO é, ainda, um detector
> confiável deste defeito.** Não conclua que está resolvido porque o portão ficou verde.

Antes de qualquer correção, **a primeira tarefa é achar um gatilho reprodutível**. Sem isso, não há
como saber se uma correção funcionou — e já houve neste projeto uma correção julgada por uma
medição que passava por acidente. O dono vê o defeito em uso real, então ele existe; falta descobrir
o que o dispara.

### Por onde continuar (o candidato que sobrou)

**A sub-janela (sobreposição) desenhar.** É a diferença entre a tecla e tudo o mais: F9/F10 fazem o
HUD renderizar, e as duas engines dividem a mesma thread de plataforma. Hipótese: a apresentação do
segundo engine reativa a do primeiro.

**Teste, ~5 minutos, sem escrever código:** com a janela principal congelada, force a sobreposição a
desenhar **sem gravar** — por exemplo mandando um toast pelo barramento (`_toHud`) por um gancho de
teste, ou usando `DITO_HUD_HOLD=1`. Se a janela principal destravar junto, está provado.

Se cair também, o próximo passo é subir em `--profile` e usar `tool/vmservice.py frames 5` **antes e
depois** de um F9, comparando as contagens de `Frame`/`RASTERIZER`/`PipelineItem` — isso mostra o que
exatamente a tecla liga.

**Atenção:** em build `profile` o `eval` do VM Service **não funciona** (AOT não compila expressão
Dart, erro 113). Para ler estado vivo, use `DITO_DIAG=1`. A timeline funciona normalmente.

## 2. Enter duplo — relatado pelo dono nesta sessão, ainda não investigado

**Sintoma:** ao enviar o texto do cartão de revisão, **o primeiro Enter pula uma linha e só o segundo
envia**. O dono tem `output.enter = true` no `config.toml`.

Nada disso foi medido ainda. Comece pelo mais provável, em ordem:

- `lib/ui/review/review_card.dart:88-106` — `_onKey`: `Enter` sem Shift chama `_send()` e devolve
  `KeyEventResult.handled`. Verifique se o `TextField` do cartão **consome o Enter antes**
  (inserindo `\n`) e o `Focus` só vê o segundo. É a explicação mais provável: um `TextField`
  multilinha trata Enter como quebra de linha, e a ordem de despacho decide quem vê primeiro.
- `lib/output/paste_service.dart` — a sequência de colagem manda um Enter próprio depois de 250 ms
  (`beforeEnter`) quando `output.enter` é true. Confira se **dois** Enter estão saindo (o do cartão
  e o da colagem) ou se o primeiro se perde.
- Meça antes de corrigir: `tool/repro_ditado.py --tecla Return` já faz o ciclo completo; instrumente
  para contar quantos Enter chegam ao alvo (um editor de texto simples serve de alvo, e o conteúdo
  dele é a prova).

## 3. Limpeza de código morto — auditado, aprovado pelo dono, NÃO executado

Uma auditoria (só leitura) confirmou, com `grep` nas duas plataformas:

| # | achado | onde | risco |
|---|---|---|---|
| 1 | `WindowRole.review` — papel removido na 1.6.0, constante sobrou | `lib/app/boot.dart:31` | nenhum |
| 2 | `window.adoptAsPanel` — fachada Dart + handler Linux + ramo Windows, **zero chamadas** | `dito_win32.dart:134`, `dito_win32_plugin.cc`, `dito_win32_plugin.cpp:329` | baixo; valida com `tool/spike_focus.dart` |
| 3 | `EngineClient(candidates:)` — resíduo do sidecar Python | `lib/engine/engine_client.dart:13` (+ `test/controller_test.dart:68`) | nenhum |
| 4 | `EngineClient.executablePath` — string fixa, ninguém lê | `lib/engine/engine_client.dart:35` | nenhum |
| 5 | **54 das 174 chaves ARB sem uso** — geração anterior da tela de Configurações | `lib/l10n/app_{en,pt}.arb` | médio: apagar a chave errada é o risco real; `test/l10n_test.dart` cobre paridade, **não** cobre "chave sem uso" |

**Suspeitos, NÃO remover sem confirmar com o dono:**
- `beam_dictation`, `beam_meeting`, `idle_unload_min` (`lib/config/config_model.dart:150-163`) — são
  persistidos no `config.toml` e **nunca chegam ao motor**. Ou é trabalho pendente, ou é lixo do
  Python. **Pergunte antes.**
- `EngineHealth.model/.backend/.restarts` — alimentados, nunca lidos. São diagnóstico; remover perde
  a contagem de reinícios do motor.
- `keys.stats`, `keys.unbind`, `paste.ctrl_v`/`paste.enter`, `windowHandles`, `sendChord` — sem
  chamada do Dart. Reconferir com `grep` (foram auditados enquanto o arquivo era editado).
- `DitoWin32.setFocusable()` **não existe no plugin Windows** e é chamado sem guarda de plataforma
  (`hud_window.dart:252,273,285`). Hoje é inofensivo porque está dentro de `_tryNative`, mas se o
  cartão parar de aceitar foco no Windows, olhe aqui primeiro.

## 4. Frentes adiadas por decisão do dono (não pegar sem ele pedir)

- **`window.focus` com espera ocupada** — `dito_win32_plugin.cc`, 2 × 20 × `g_usleep(5000)`. Medido:
  `cartao recebido` → `cartao no ar` leva 114-181 ms. Traduziram `SetForegroundWindow` (síncrono no
  Windows) como polling. **Risco:** é o código que consertou o "Enter ia para o terminal"
  (armadilha 4.6).
- **`clipboard.get` com laço de eventos aninhado** — roda em toda colagem, sem timeout.
- **Latência de 58-63 ms do laço GTK enquanto grava** — apresentação de frame na thread de UI
  (`gdk_cairo_draw_from_gl` → `XSync` → `libGLX_nvidia`, 6 de 10 amostras de `gdb`).
- **Renomear `dito_win32`** — o nome é herdado do Windows mas as duas implementações nativas são
  legítimas e independentes (1600 linhas de GTK/X11 no Linux). O dono escolheu **não** renomear
  agora; o custo do nome é real (ele já induziu a uma conclusão errada), mas é cosmético.
- **A pílula seguir o monitor em foco** em vez do primário. **O dono disse explicitamente que está do
  jeito que ele quer.** Só mexer se ele pedir.

## 5. Ambiente, para não redescobrir

- Debian 13, X11, Cinnamon/Muffin, NVIDIA (GLX), PipeWire com compat PulseAudio.
- **Dois monitores**: `DP-0 1920x1080+0+0` (primário) e `HDMI-0 1920x1080+1920+0`.
- Microfone: headset USB **H510-PRO Wireless**, que **entrega silêncio de forma intermitente** — já
  provado que não é defeito do app (o Dito capta o mesmo que `pw-record` no mesmo instante).
- Disponíveis: `gdb`, `strace -k`, `xdotool`, `xwininfo`, `xprop`, `gdbus`/`busctl`, `python3` com
  `websockets`, `numpy`, `PIL` e `python3-xlib`. **`perf` e `ffmpeg` NÃO** estão instalados.
- Logs: `~/.local/share/dito/logs/` (`app`, `controller`, `engine`, `native_engine`, `hotkeys`,
  `hud_window`, `crash`, `paste`, e o `native.log`, que recebe o `g_warning` do plugin).
- Gravações: `~/Documentos/Dito/AAAA/MM/DD/`.
- A bandeja pode ser acionada por DBus, o que torna o teste de abrir a janela automatizável:
  `gdbus call --session --dest com.defalt.dito_app --object-path
  /org/ayatana/NotificationItem/dito/Menu --method com.canonical.dbusmenu.Event -- 15 clicked "<''>" 0`
  (item 15 = "Abrir Dito").

## Primeira coisa a fazer

Ler os quatro documentos citados, rodar `python3 tool/regressao.py` para ver o estado atual com os
próprios olhos, e então atacar o item 1 pelo teste da sobreposição — **medindo antes de corrigir**.
