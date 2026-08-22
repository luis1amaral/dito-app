# Descobertas dos agentes — port Linux do Dito (2026-08-21 e 22)

Consolidado do que **sete agentes de investigação** trouxeram, com arquivo:linha. Tudo aqui é
evidência lida no código ou medida em execução — hipótese não confirmada está marcada como tal.

Regra de leitura: **o que já foi corrigido** está marcado ✅ com a versão; **o que continua aberto**
está marcado ⬜ e é o insumo do plano de resolução.

---

## 0. O contexto que explica tudo

O Dito era um app **Python** (`sounddevice`/PortAudio + faster-whisper) e foi portado para
**Flutter + C++** (miniaudio + whisper.cpp). No Windows funciona; **só o Linux acumulou defeitos**.

O código Python foi recuperado da Lixeira (`~/.local/share/Trash/files/dito/`) e contém um
`docs/armadilhas.md` documentando armadilhas já pagas — **o port não trouxe esse arquivo**, e metade
dos defeitos de 2026-08-21/22 foi reaprender o que ele já sabia.

O padrão de erro que se repete: **traduzir a chamada, não o significado**.

| conceito | Windows | Linux | consequência |
|---|---|---|---|
| "não roube foco" | `WS_EX_NOACTIVATE` (fraco: `SetForegroundWindow` ainda funciona) | `accept_focus=FALSE` → `WM_HINTS.input=False` (**definitivo**: o WM recusa foco para sempre) | Enter ia para o terminal |
| hook de teclado | `WH_KEYBOARD_LL` (**não exclusivo**) | `XGrabKey` (**exclusivo**) | 3 janelas do mesmo app brigando pela tecla |
| callback de áudio | WASAPI eleva a thread a "Pro Audio" (MMCSS) | PulseAudio não eleva nada, e é a mesma thread que drena o protocolo | overrun e descarte de amostras |

---

## 1. Teclas globais F9/F10 (agentes 1–3, 2026-08-21)

### ✅ 1.1 Um hook por JANELA em vez de por processo — corrigido em 1.4.7
`dito_win32_plugin.cc:1305` (registrar) roda **uma vez por janela** (main + HUD + review) e cada
registro criava `new PluginState()` (`:530`) e chamava `StartKeyHook` → **`XOpenDisplay` próprio**.
Conexões X distintas são **clientes X distintos**, e `XGrabKey` é exclusivo: as três janelas do mesmo
Dito disputavam F9/F10. Quem vencia podia ser o HUD ou a Review — cujo canal **ninguém escuta**
(`native_key_source.dart:10` é assinatura única, só na janela principal). App mudo, com
`grab: true` no snapshot e contador de eventos congelado.

### ✅ 1.2 `XGrabKey` falhando em silêncio — corrigido em 1.4.6
`X11ErrorHandler` (`:248-250`) devolvia `0` sem logar; `keys.bind` respondia `TRUE` fixo (`:564`).

### ✅ 1.3 Sem instância única — corrigido em 1.4.6
`my_application.cc:173` usava `G_APPLICATION_NON_UNIQUE`, enquanto o Windows sempre teve mutex +
`FindWindow` (`windows/runner/main.cpp:35-37`). Evidência: `app.log` com **80 `boot completo` para 8
`encerrando`**, e linhas fora de ordem (dois processos escrevendo no mesmo arquivo).

### ✅ 1.4 `_awaitingRelease` sem teto e `_begin` não exception-safe — corrigido em 1.4.6
`hotkey_machine.dart:99-102,132` (toggle preso para sempre se o release nunca chegar) e `:117-126`
(uma exceção em `onStart` travava `_active`).

---

## 2. Máquina de estado da gravação (agente 2, 2026-08-21)

### ✅ 2.1 Gravação fantasma — corrigido em 1.4.6
Timeout de 5 s devolvia a fase para `idle` **sem mandar `StopCommand`**
(`dito_controller.dart:192-201`); a tecla era solta sem parar nada (`:159-170`); o `StartedEvent`
atrasado cravava a fase de volta (`:232-246`). Resultado: motor gravando, ninguém podia parar, toda
tecla recusada. O único self-heal só rodava em `transcribing` (`:111-114`).

### ✅ 2.2 O fix 1.4.5 cobria só metade — corrigido em 1.4.6
`live = state.isRecording && event.sessionId != _activeSessionId` (`:318`) protegia a sessão nova só
enquanto ela **capturava**; transcrevendo, o `finished` da velha idlava a fase, cancelava o watchdog
e virava `pendingReview` da errada.

### ✅ 2.3 `Isolate.spawn` sem `onExit`/`onError` — corrigido em 1.4.6
`whisper_worker.dart:39-44`: isolate morto = `await` eterno em `native_engine.dart:288`.

### ✅ 2.4 Detecção de motor morto era código morto — corrigido em 1.4.6
`engine_client.dart:27,30`: `_exits` nunca recebia `add(...)`, então `EngineSupervisor._onDeath()`
nunca rodava (resíduo da era do sidecar Python).

---

## 3. Áudio (agentes 4–6, 2026-08-21)

### ✅ 3.1 Callback de tempo real fazendo I/O de disco — corrigido em 1.4.9
`dito_whisper.cpp:82-125` fazia, **dentro do callback do driver**: `push_back` num vetor sem
`reserve()`, conversão float→int16, `ofstream::write` por bloco e **`flush()` síncrono a cada
segundo**, tudo sob o mesmo mutex do medidor de nível de 20 Hz.
No backend PulseAudio, `pa_stream_drop()` — o "já consumi" que o servidor espera — só acontece
**depois** que o callback retorna (`miniaudio.h:31757-31771`). Callback preso = buffer cheio =
`pipewire-pulse: [com.defalt.dito_app] overrun recover ... skip:4082`.
O Python já sabia: `src/dito/audio/capture.py:58` — *"Realtime thread: slow work here drops blocks"*,
com a escrita numa thread consumidora (`core/session.py:158-159,255`) e bloco de **50 ms explícito**
(`BLOCKSIZE = 800`). O C++ herdava 10 ms × 3 do miniaudio (`miniaudio.h:12217-12222`).

### ✅ 3.2 Sem salvaguarda contra ALSA cru — corrigido em 1.4.9
`ma_context_init(NULL, 0, ...)` aceitava PulseAudio → ALSA → JACK sem registrar qual abriu. O Python
**proibia** ALSA cru (`armadilhas.md` 1.7/1.12) porque nesta máquina os `hw:` **rejeitam 16 kHz**
(`PaErrorCode -9997`) e o "default" do ALSA é a entrada da placa-mãe, sem nada plugado.

### ✅ 3.3 Alarme sem histerese e aquecimento por amostras — corrigido em 1.4.8
`silence_alarm.dart:34-53` alternava `dead`↔`quiet` **a cada tick de 50 ms**; o aquecimento
(`warmUpSeconds = 0.05`) era medido em **amostras** (800), e um burst do driver liberava o gate no
primeiro instante.

### ✅ 3.4 Sinal fraco intermitente do headset — mitigado em 1.5.4
**Não é defeito do app.** Medição simultânea: `pw-record` 306 RMS × Dito 310 RMS no mesmo instante;
outra hora, 806 com a mesma voz. Ganho no ALSA e no PipeWire a 100%. Mitigação: ganho automático
(até 20×) antes do Whisper, nunca sobre ruído de fundo (`native_engine.dart`, `gainFor`).
Hipótese **não confirmada** para a origem: link do headset wireless H510-PRO.

---

## 4. Janelas, foco e interface (agentes 7–10, 2026-08-21/22)

### ✅ 4.1 Sub-janela nascia sem contexto GL — corrigido em 1.6.0
O `FlView` só consegue contexto GL sobre uma janela **realmente mapeada**; o fork criava a view com a
janela apenas realizada. Sem contexto, o engine nunca desenha um frame — e **sem frame o `initState`
do Dart nunca roda**: a janela existia com o tamanho de fábrica e o que ficava na tela era um quadro
congelado que não respondia a nada ("modal preso").
Correção: `gtk_widget_show_all` **antes** de criar a view, com recorte vazio; e **uma sub-janela só**
(pílula + cartões juntos), porque cada janela extra é mais uma chance de nascer morta.
**Testado e rejeitado:** atrasar a criação, esperar `endOfFrame`, `LIBGL_ALWAYS_SOFTWARE`,
`GDK_GL=gles`, `glx-legacy`, criar sem foco, realizar antes.

### ✅ 4.2 `accept_focus=FALSE` permanente — corrigido em 1.6.1
`hud_window.dart:26` chamava `adoptAsHud()` sempre que a sobreposição subia →
`gtk_window_set_accept_focus(FALSE)` → `WM_HINTS.input = False`. Para o Mutter/Muffin isso é
**incapacidade estrutural**, não preferência: o WM recusa foco para sempre, e nem `XSetInputFocus`
contorna (ele devolve o foco na interação seguinte). **Não existia nenhuma chamada que voltasse o
hint para `TRUE`** — e a API correta (`adoptAsPanel`, que não desliga foco) existia e estava **morta**
(nenhuma chamada em `lib/`).
Correção: `window.setFocusable(bool)` novo, ligado quando há cartão e desligado quando resta só a
pílula. Prova: `xprop WM_HINTS` passou a mostrar `input focus: True` com cartão na tela.

### ✅ 4.3 `FlView` da sub-janela sem `gtk_widget_grab_focus` — corrigido em 1.6.1
O runner principal faz isso (`my_application.cc`); o fork do multi-window não fazia. Sem isso o
teclado não chega ao motor mesmo com a janela focada.

### ✅ 4.4 Alvo do foco anterior era esquecido — corrigido em 1.6.1
`focus.take` (`dito_win32_plugin.cc:901`) **zerava** `saved_focus_target` quando a sobreposição já
era a janela ativa (2º cartão seguido). O `giveBack` virava no-op silencioso → **o foco do X ficava
preso na sobreposição** e as teclas do sistema sumiam. É a explicação de "a interface trava até eu
apertar F9/F10": as teclas globais usam `XGrabKey` na raiz e funcionam **independente de foco**, e ao
disparar refazem o ciclo de foco.

### ✅ 4.5 Foco devolvido cedo demais — corrigido em 1.6.1
`_fecharCartao` devolvia o foco mesmo com outro cartão na tela, deixando os seguintes sem teclado.

### ✅ 4.6 Tecla sintética por subprocesso síncrono — corrigido em 1.6.1
`RunXdotoolKey` (`dito_win32_plugin.cc:672-686`) usava `g_spawn_sync`: fork + exec + espera **na
thread do GTK**, 20–150 ms de interface congelada **por tecla**, em toda colagem (Ctrl+V e Enter).
Correção: `XTestFakeKeyEvent` via `libXtst`, com `xdotool` como último recurso.

### ✅ 4.7 Reentrância do laço principal com mutex global — corrigido em 1.6.1
`desktop_multi_window_plugin.cc:199` tinha `while (gtk_events_pending()) gtk_main_iteration();`
**dentro do escopo de `g_plugin_mutex`** — se qualquer chamada do mesmo canal estivesse na fila,
o processo travaria **para sempre** (mutex não recursivo). Além do congelamento no boot.

### ⬜ 4.8 `clipboard.get` bloqueia a thread do GTK — ABERTO
`dito_win32_plugin.cc:830-838` usa `gtk_clipboard_wait_for_text`, que roda um **laço de eventos
aninhado** na thread principal — a mesma que atende todos os canais de todas as janelas. Roda em
**toda** colagem, porque `restore_clipboard = true` é o default e está ativo no `config.toml` do dono.
Candidato forte para o congelamento que **ainda resta**.

### ⬜ 4.9 Captura de áudio abrindo/fechando no isolate principal — ABERTO
`native_engine.dart:218` (`startCapture`), `:309` e `:413` (`stopCapture`) chamam FFI direto no
isolate principal; do lado C++, `ma_device_init`/`ma_device_start` (`dito_whisper.cpp:427-434`) e
`ma_device_stop`/`ma_device_uninit` (`:472-473`) são bloqueantes por design do miniaudio
(10–100 ms). Isso trava a interface **a cada F9/F10**.

### ⬜ 4.10 `window.focus` com busy-wait de até 300 ms — ABERTO
`dito_win32_plugin.cc:1029-1041`: 2 tentativas × 20 iterações × `g_usleep(5000)` na thread de
plataforma, a cada cartão que aparece.

### ✅ 4.11 20 Hz no isolate principal — o custo real era o `HudState` morto do `boot.dart`, removido em 1.6.3
`native_engine.dart:246-261`: chamada FFI a cada 50 ms disputando o isolate que desenha a UI.

### ✅ 4.12 Falhas silenciosas na colagem — corrigido em 1.6.3
- `paste_service.dart:76` — retorno de `restoreFocus()` **descartado**: o Ctrl+V é disparado sem
  confirmação de que o foco voltou.
- `paste_service.dart:87` — retorno de `pressEnter()` descartado.
- `dito_win32_plugin.cc:849` (`clipboard.set`) — responde `TRUE` **incondicional**, sem checar posse
  do seletor.
- `focus.giveBack` (`:908-921`) — fire-and-forget, **sem `XSync` nem confirmação**, ao contrário de
  `window.focus`, que confirma (o próprio código comenta: *"Ask, then confirm: answering TRUE without
  checking is what hid this bug for a whole day"* — a lição não foi aplicada aqui).
- `dito_controller.dart:463-482` — um envio bem-sucedido **não gera confirmação visual nenhuma**, o
  que torna sucesso e falha indistinguíveis para o dono.
- `g_warning` do plugin vai para **stderr**, não para os `.log` do Dito — invisível quando o app roda
  pela bandeja/autostart.

### ✅ 4.13 Sem type hint na sobreposição — corrigido em 1.6.3 (`UTILITY`, antes do `show_all`)
Nenhum `gtk_window_set_type_hint`/`set_transient_for` no código: a janela nasce
`GDK_WINDOW_TYPE_HINT_NORMAL`, a categoria com o tratamento de foco/stacking mais pesado do EWMH —
o oposto do indicado para uma sobreposição (`UTILITY`/`NOTIFICATION`).

### ✅ 4.14 Toast "descartado" não some — corrigido em 1.6.2 (era pixel fantasma do compositor)
O toast tem 1,2 s configurado, mas fica na tela. Provável: `_exitTimer`/`_toastTimer` cancelado por
outro estado no meio do caminho (`hud_state.dart`).

---

## 5. O que o Python fazia e o port não trouxe

| item | Python (na Lixeira) | port C++/Flutter |
|---|---|---|
| callback de áudio | só mede nível e enfileira (`capture.py:57-76`) | fazia disco + flush + realloc (corrigido em 1.4.9) |
| bloco de captura | 50 ms explícito (`capture.py:13`) | default 10 ms (corrigido em 1.4.9) |
| escrita do WAV | thread consumidora (`session.py:158-159,255`) | dentro do callback (corrigido em 1.4.9) |
| validação de taxa | `check_input_settings(16000)` antes de abrir (`devices.py:52-60`) | **nada** ⬜ |
| proibição de ALSA cru | documentada e testada (`armadilhas.md` 1.7/1.12) | corrigido em 1.4.9 |
| `docs/armadilhas.md` | existia | **não veio no port** — recriado em 2026-08-21 |

---

## 6. Versões publicadas nesta investigação

| versão | o que fechou |
|---|---|
| 1.4.6 | fase presa, gravação fantasma, isolate sem `onExit`, instância única, grab verificado |
| 1.4.7 | um hook de teclado por processo (F9/F10 paravam de responder) |
| 1.4.8 | histerese do alarme, aquecimento por tempo, log do nível |
| 1.4.9 | captura reescrita com a arquitetura do Python |
| 1.5.0 | HUD "Gravando" aparecendo (6/6) |
| 1.5.1 | fila de revisões (várias falas esperando) |
| 1.5.2–1.5.3 | clique seleciona, cantos redondos, pilha em leque |
| 1.5.4 | ganho automático; máscara de cliques que ficava vazia |
| 1.6.0 | sub-janela nasce mapeada; uma sobreposição só |
| 1.6.1 | foco (o Enter ia para o terminal), XTEST, reentrância removida |
