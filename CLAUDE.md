# dito-flutter

Dito (ditado por voz offline) em Flutter, para **Windows e Linux**. Não existe mais sidecar
Python: o motor é C++ nativo **in-process** via FFI (`packages/dito_whisper`, whisper.cpp + ggml +
miniaudio), carregado num isolate dedicado (`lib/engine/whisper_worker.dart`) porque o contexto
CUDA é preso à thread. Áudio, Whisper, sessão e biblioteca vivem no Dart/C++ deste repo.
O que é específico de plataforma (teclas globais, janelas, foco, colagem, notificação) fica atrás
do plugin `packages/dito_win32` — nome herdado do Windows, mas serve as duas plataformas
(`windows/` e `linux/`).

## Regras de código — sem exceção

- **Comentário só em INGLÊS, e no máximo 1 LINHA.** Vale para `//`, `///` e docstring. Se o porquê
  não cabe numa linha, ele não é comentário: vai para `CHANGELOG.md` ou `docs/`, e o comentário
  vira um ponteiro de uma linha para lá.
- **Comentário só quando carrega um *porquê*** que o código não diz sozinho. Nada de narrar a linha.
- `CHANGELOG.md`, `README.md` e documentação: **pt-BR**.
- Nada de cor, espaçamento, raio ou duração cru em `lib/ui/**` — só de `ui/tokens.dart` e
  `ui/palette.dart`. Há teste que varre isso.

## As 4 garantias inegociáveis (herdadas do dito-app)

1. **O áudio NÃO vai para o disco.** Revogada pelo dono em 2026-08-22 (1.6.4): o WAV era seguro
   contra queda no meio da gravação e custava **99,9% da biblioteca** (158,7 MB contra 129 KB de
   JSON, em 6 dias). O que se guarda é o texto. `DITO_SALVAR_WAV=1` liga o WAV de volta só para
   depurar. **Não recoloque o WAV** achando que está restaurando uma garantia.
2. Quando não capta, **avisa em ~1 s** — forma + cor no pill são obrigatórias e sempre ligadas;
   som e notificação são canais opcionais (`audio.alerts.sound`/`notify`), desligados por escolha
   do dono em 2026-08-21 por serem ruído: com o pill vermelho funcionando, bastam forma + cor.
3. **A gravação não tem limite de tempo.** O F10 é modo alternador (toggle) para ditar sem precisar
   segurar a tecla (andando, em pé ou afastado do teclado). **O conceito de "modo reunião" foi
   abandonado pelo dono:** o Dito é estritamente um ditador rápido de comandos e textos para colar.
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
