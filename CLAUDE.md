# dito-flutter

Porte do Dito (ditado por voz offline) para Flutter/Windows. O motor Python (`../dito-app`) roda
como **sidecar** e é a verdade do produto: áudio, Whisper, watchdog, sessão e biblioteca vivem lá.
O Flutter é interface, teclas, colagem e janelas.

## Regras de código — sem exceção

- **Comentário só em INGLÊS, e no máximo 1 LINHA.** Vale para `//`, `///` e docstring. Se o porquê
  não cabe numa linha, ele não é comentário: vai para `CHANGELOG.md` ou `docs/`, e o comentário
  vira um ponteiro de uma linha para lá.
- **Comentário só quando carrega um *porquê*** que o código não diz sozinho. Nada de narrar a linha.
- `CHANGELOG.md`, `README.md` e documentação: **pt-BR**.
- Nada de cor, espaçamento, raio ou duração cru em `lib/ui/**` — só de `ui/tokens.dart` e
  `ui/palette.dart`. Há teste que varre isso.

## As 4 garantias inegociáveis (herdadas do dito-app)

1. Áudio nunca se perde — vai ao disco desde o 1º bloco, WAV válido a qualquer instante.
2. Quando não capta, **grita em ~1 s** por forma + cor + som + notificação.
3. Reunião **não tem limite de tempo** (deliberadamente não existe config para isso).
4. Nada aparece no login além do ícone da bandeja.

## Armadilhas que este porte já pagou

- **Push-to-talk não sai de `hotkey_manager`.** `RegisterHotKey`/`WM_HOTKEY` só entrega key-down;
  `keyUpHandler` é código morto no Windows. Precisa de `WH_KEYBOARD_LL` nativo.
- **Não use o evento de release da tecla.** Estado físico + 300 ms contínuos solto.
- **Tecla suprimida some do `GetAsyncKeyState`** — o hook é a autoridade, `GetAsyncKeyState` é só
  resgate para tecla que nunca passou pelo hook.
- **A janela do HUD só não rouba foco se nascer com `WS_EX_NOACTIVATE`** — aplicar depois não
  retroage. Ver `packages/desktop_multi_window/FORK.md`.
- **`started` com `session_id == "engine_ready"` é handshake, não gravação.** Separado no parsing.
- Sessões no disco são `<lib>/YYYY/MM/DD/<HH-MM-SS>.json`, **não** `session.json`.
- **CUDA `CUDA_ARCHITECTURES` nunca só `-virtual` (PTX).** Faz o driver compilar (JIT) cada
  kernel na primeira transcrição real, travando minutos — testar `using CUDA0 backend` só
  prova que o *init* foi rápido, não prova nada sobre inferência de verdade. Usar código real
  (`"61;75;86;89"`, sem sufixo `-virtual`) e só então testar uma transcrição ponta a ponta.

## Portão

```
flutter analyze && flutter test
```

Prova do fork de janela: `flutter build windows --debug --target=tool/spike_focus.dart` e rodar o
executável — `VEREDITO ... PASSA`.
