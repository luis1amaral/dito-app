# Plano de resolução — a interface travando no Linux

Insumo: `achados-dos-agentes.md`. Sintoma do dono: **trava ao entrar numa gravação e trava depois de
gravar**. Os itens 4.1–4.7 já estão corrigidos (1.4.6 → 1.6.1). Este plano cobre só o que está ⬜.

Os números de linha abaixo foram reconferidos no código em disco (o documento de achados tem alguns
levemente defasados por mudanças posteriores).

## O achado que muda a prioridade

**4.8, 4.9 e 4.10 bloqueiam a MESMA thread** — a thread de plataforma do GTK, que no embedder Flutter
Linux também desenha (`FlView`) e despacha os canais de **todas** as janelas.

Está provado em código: `EngineClient.send()` (`lib/engine/engine_client.dart:72`) chama
`unawaited(_engine.handleCommand(command))` **sem isolate**, e `HotkeyMachine._begin`
(`lib/keys/hotkey_machine.dart:122`) dispara isso de forma síncrona a partir da tecla física.

Ou seja: **"trava quando entro" e "trava depois que gravo" são o mesmo defeito estrutural** — chamada
bloqueante na thread errada — e não três bugs distintos.

E não são casos raros: `output.confirm = true` e `output.restoreClipboard = true` são os padrões do
app (`lib/config/config_model.dart:201,202`), então o cartão de revisão (4.10) e o `clipboard.get`
bloqueante (4.8) disparam em **toda** ditada.

---

## 1. Áudio e nível fora do isolate principal — 4.9 + 4.11

**Prioridade #1 — é o "trava quando eu entro".**

**Causa.** `lib/engine/native_engine.dart:218` (`startCapture`), `:309` e `:413` (`stopCapture`) fazem
FFI síncrona no isolate principal — o mesmo que desenha a UI. Do lado C, `ma_device_init`/
`ma_device_start` (`dito_whisper.cpp:427,432`) e `ma_device_stop`/`ma_device_uninit` (`:472-473`) são
bloqueantes por design do miniaudio (10–100 ms de round-trip com o PipeWire). Junto vai o
`getLevel()` a cada 50 ms (`native_engine.dart:246-261`), também no isolate principal.

**Correção.** Isolate dedicada de áudio, no mesmo padrão já testado de
`lib/engine/whisper_worker.dart` (spawn + portas, **com `onExit`/`onError` desde o primeiro commit** —
não repetir a armadilha 2.3). Migrar `startCapture`, `stopCapture` e `getLevel`. Não reusar a isolate
do whisper (aquela é presa ao contexto CUDA e serializaria o controle atrás de uma transcrição).

**Risco.** Maior escopo do plano. `g_capture_device`/`g_audio_buffer`/`g_wav_file` são globais do
processo **sem mutex nesse nível**: a regra passa a ser *só a isolate de áudio chama essas FFI*.
Some latência de IPC (baixa). E reintroduz a classe da armadilha 2.3 se `onExit`/`onError` faltarem.

**Prova.**
1. Heartbeat de 16 ms logando timestamp desde o boot (`tool/spike_freeze_watch.dart`): **gap > 100 ms
   entre ticks é trava medida em ms**, não impressão.
2. 20 ciclos de F9 via `xdotool` com pausas aleatórias, contando gaps > 100 ms ao redor de cada tecla.
   Meta: zero.
3. Comparar o timestamp do log nativo (`dito_whisper.cpp:440-441`, que já registra backend/device/
   taxa) com o tick mais próximo — hoje coincidem; depois o heartbeat não pode parar.

**Teste.** `test/native_engine_test.dart`: backend falso cujo `startCapture` dorme, verificando que um
`Timer.periodic` concorrente continua tiquetaqueando. Hoje **falha** (prova que pega o defeito).

---

## 2. `clipboard.get` assíncrono — 4.8

**Prioridade #2 — é o "depois que gravo".**

**Causa.** `dito_win32_plugin.cc:869-877` usa `gtk_clipboard_wait_for_text`, que roda um **laço de
eventos aninhado** na thread que atende os canais de todas as janelas. Roda em toda colagem porque
`restoreClipboard = true` é o padrão (`config_model.dart:202`, usado em `paste_service.dart:53-60`).

**Correção.** Trocar por `gtk_clipboard_request_text()` (callback), respondendo o `FlMethodCall`
dentro do callback. Criar um helper `RespondLater(...)` — o item 3 precisa do mesmo padrão.

**Risco.** Baixo-médio: se a janela morrer entre a chamada e o callback, responder um `method_call`
morto vira crash. Checar validade do plugin no callback — trocar freeze por crash não é aceitável.

**Prova.** 20 colagens seguidas com o heartbeat ligado: gap > 50 ms durante a colagem = ainda
bloqueia. E medir o intervalo entre `cartao enviado` (`hud_window.dart:281`, log já existe) e o tick
seguinte.

**Teste.** Não há como cobrir GTK nativo em `flutter test`. **Não inventar teste de mentira** —
registrar a prova manual no CHANGELOG, como já foi feito para 4.1–4.7.

---

## 3. `window.focus` sem busy-wait — 4.10

**Prioridade #3 — dispara em quase toda gravação (`confirm=true` é padrão).**

**Causa.** `dito_win32_plugin.cc:1090-1102`: 2 × 20 iterações de `g_usleep(5000)` = **200 ms
garantidos** de sono na thread de plataforma, mais os round-trips por tentativa.

**Correção.** Sinal em vez de polling: conectar `focus-in-event` (ou `notify::has-toplevel-focus`) e
responder de dentro do handler; `g_timeout_add(300, ...)` como teto, respondendo `false` sem nunca
segurar a thread. Reusar o helper do item 2.

**Risco.** Médio — é o código que resolveu o "Enter ia para o terminal". **Não responder `true`
otimista antes do sinal**: reintroduziria o bug 4.6 (o próprio comentário do código avisa: *"Ask,
then confirm: answering TRUE without checking is what hid this bug for a whole day"*). O fallback
`XSetInputFocus` (`:1104-1112`) precisa continuar funcionando quando o WM recusa.

**Prova.** `xprop WM_HINTS` com `input focus: True` no cartão (armadilha 4.6) **não pode regredir**;
e o intervalo entre `cartao recebido` (`hud_window.dart:110`) e `cartao no ar: focado=true` (`:263`)
deve cair dos 200–300 ms atuais para o tempo real do WM (< 20 ms típico).

---

## 4. Falhas silenciosas na colagem — 4.12

**Prioridade #4 — não trava, mas mina a confiança.** Cinco correções independentes; **não juntar numa
reforma só**, para isolar regressão.

- **a)** `paste_service.dart:76` — capturar o retorno de `restoreFocus()` e logar quando `false`. Não
  abortar o Ctrl+V só por isso (falso negativo é conhecido). Teste em `paste_sequence_test.dart`.
- **b)** `paste_service.dart:87` — mesmo para `pressEnter()`.
- **c)** `dito_win32_plugin.cc:879-891` (`clipboard.set`) — responde `TRUE` incondicional porque
  `gtk_clipboard_set_text` é `void`. Trocar por `gtk_clipboard_set_with_data()`, que retorna
  `gboolean`. Prova: `xclip -o -selection clipboard` após um set forçado.
- **d)** `focus.giveBack` (`:951-964`) — fire-and-forget. Fazer **um** `XSync` + **uma** leitura de
  `ReadNetActiveWindow` e logar se não bateu. **Sem laço** — copiar o busy-wait do item 3 para cá
  trocaria uma trava por outra.
- **e)** `dito_controller.dart:419-433` — sucesso não gera confirmação visual: o toast só aparece
  quando `result.fallback != null`. Adicionar o `HudToast.pasted` no caminho de sucesso (o mesmo que
  já existe em `:478`). Teste em `controller_test.dart`, que já captura `hudLog`.
- **f)** `g_warning` do plugin vai para stderr e some quando o app roda pela bandeja. Instalar
  `g_log_set_default_handler` em `linux/runner/my_application.cc` mandando para o log do Dito.
  **Fazer isto primeiro** — melhora o diagnóstico dos itens 1–3.

---

## 5. Type hint da sobreposição — 4.13

**Causa.** `desktop_multi_window_plugin.cc:163` cria com `gtk_window_new(GTK_WINDOW_TOPLEVEL)` e nunca
chama `gtk_window_set_type_hint` — a janela nasce `NORMAL`, a categoria EWMH com o tratamento de
foco/stacking mais pesado.

**Correção.** `gtk_window_set_type_hint(win, GDK_WINDOW_TYPE_HINT_UTILITY)` logo após a criação e
**antes** do `show_all` (mesma regra da armadilha 4.6: hint aplicado depois não retroage).
`UTILITY`, não `NOTIFICATION`, porque a sobreposição **precisa** de foco quando há cartão.

**Risco.** Médio: `UTILITY` + `keep_above` + `accept_focus` dinâmico nunca foi validado nesta base.
**Não** usar `transient_for` agora. Se a prova da armadilha 4.6 quebrar, reverter.

**Prova.** `xprop | grep _NET_WM_WINDOW_TYPE` antes e depois; e reexecutar a prova de foco de 4.6.

---

## 6. Toast "descartado" que não some — 4.14

**Por último, de propósito: a causa NÃO está confirmada.**

Li o código e **não achei bug na lógica do timer**: `hud_state.dart:92-101` e `:171-188` estão
corretos na leitura estática, e existe teste verde cobrindo esse caminho
(`test/hud_state_test.dart:127-131`). Isso desloca a suspeita para `hud_window.dart:_applyOnce`
(`:205-245`), que é quem esconde a janela via `setHitRect(Rect.zero)` — **e esse código não tem teste
nenhum hoje**.

**Hipótese mais forte** (não confirmada): o toast viaja cartão → janela principal → HUD, passando pela
**mesma thread** que os itens 1–3 bloqueiam. Se o `setHitRect` ficar enfileirado atrás de um
`clipboard.get`, o toast fica preso na tela — seria mais um sintoma do mesmo problema central, e os
itens 1–3 já o resolveriam.

**Como proceder:** instrumentar (`dismiss()` e o callback do `_toastTimer` com timestamp; log de
sucesso no `_tryNative('esconder')`, hoje ausente) → reproduzir 10 descartes → **só então** corrigir,
sabendo se foi thread ocupada ou lógica. É a regra 5.2 do `armadilhas.md`.

**Achado colateral:** `boot.dart:40` declara um `HudState` que é alimentado em todo `_toHud()`
(`:303`) e **nunca é lido** — código morto rodando um timer duplicado. Remover, mas **em mudança
separada**, para não misturar limpeza com correção.

**Teste.** Criar `test/hud_window_test.dart` (não existe): `review` → `reviewDiscard` → toast,
travando que `shouldShow` cai para `false` no tempo esperado. É a lacuna real de cobertura aqui.

---

## O que NÃO fazer agora

- **Não** copiar o busy-wait do item 3 para o `focus.giveBack` — trocaria uma trava por outra.
- **Não** mexer em `hud_state.dart` (4.14) sem reproduzir: o teste atual passa; mexer às cegas quebra
  o que funciona.
- **Não** trazer agora a validação de taxa que o Python tinha (`check_input_settings`) — é qualidade
  de áudio, não interface. Frente separada.
- **Não** criar sub-janela nova nem reabrir a arquitetura "uma sobreposição só" (4.4, resolvida).
- **Não** mexer em `RunXdotoolKey` (4.6, já resolvido com XTEST).
- **Não** fazer as cinco correções de 4.12 numa mudança única.
- **Não** usar o DevTools Timeline como prova no CHANGELOG: o ambiente real é o app em release. A
  prova que vale é log com timestamp + `xdotool`/`xprop`, como em 4.1–4.7.

---

## Ordem de execução

| # | item | por quê | esforço |
|---|---|---|---|
| 0 | 4.12.f (log do GLib no arquivo) | melhora o diagnóstico de tudo abaixo | baixo |
| 1 | 4.9 + 4.11 (áudio fora do isolate principal) | o "trava ao entrar" | médio-alto |
| 2 | 4.8 (`clipboard.get` assíncrono) | o "trava depois que grava" | médio |
| 3 | 4.10 (`window.focus` sem busy-wait) | dispara em quase toda gravação | médio |
| 4 | 4.12.a–e (confirmações da colagem) | confiança; risco baixo | baixo |
| 5 | 4.13 (type hint) | estrutural | baixo, risco médio |
| 6 | 4.14 (toast) | pode se resolver com 1–3; instrumentar antes | investigação |
