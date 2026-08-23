# dito-flutter

Dito (ditado por voz offline) em Flutter, para **Windows e Linux**. Não existe mais sidecar
Python: o motor é C++ nativo **in-process** via FFI (`packages/dito_whisper`, whisper.cpp + ggml +
miniaudio), carregado num isolate dedicado (`lib/engine/whisper_worker.dart`) porque o contexto
CUDA é preso à thread. Áudio, Whisper, sessão e biblioteca vivem no Dart/C++ deste repo.
O que é específico de plataforma (teclas globais, janelas, foco, colagem, notificação) fica atrás
do plugin `packages/dito_win32` — nome herdado do Windows, mas serve as duas plataformas
(`windows/` e `linux/`).

**Single-engine, uma janela só.** Não existe mais `desktop_multi_window`: há **um** Flutter Engine
e **uma** janela nativa que troca de papel (`AppWindowMode.hidden | overlay | mainWindow`, em
`lib/ui/window_orchestrator.dart`). Três engines disputando contexto de GPU eram a causa da tela
preta fantasma. **Não crie sub-janela** — o preço disso já foi pago uma vez.

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
  retroage. `window.adoptAsHud`, que fazia isso, está **morto**: declarado na fachada Dart
  (`packages/dito_win32/lib/dito_win32.dart`) e chamado por ninguém desde a migração single-engine.
  Armadilha 4.14 em `docs/armadilhas.md`.
- **Janela escondida que é redimensionada precisa de `DitoWin32.forceRepaint()` antes de mostrar** —
  senão o swapchain do Flutter deixa uma faixa preta parada. E `SetWindowRgn` conta a partir da
  **janela**, não do **cliente**: converter com `ClientToScreen` + `GetWindowRect` antes de montar
  a região, senão o recorte (pílula, cartão) fica uma barra de título alto. Armadilhas 4.13 e 4.14.
- **Janela `HWND_MESSAGE` não recebe broadcast do Explorer** — se o host precisa reagir a
  `TaskbarCreated` (reconstruir o ícone da bandeja após o Explorer reiniciar), tem de ser uma janela
  top-level oculta (`WS_POPUP` + `WS_EX_TOOLWINDOW`), nunca `HWND_MESSAGE`. Armadilha 4.15.
- **Refatoração que apaga um arquivo leva junto as chamadas nativas dele.** A migração
  single-engine apagou `lib/ui/hud/hud_window.dart` e com ele o único `DitoWin32.takeFocus` do app;
  sem ele o foco nunca voltava e a colagem no conhost morria calada. Ao apagar um arquivo, procure
  o que ele chamava no nativo antes de apagar. Travado por `test/focus_target_test.dart`.
- **`started` com `session_id == "engine_ready"` é handshake, não gravação.** Separado no parsing.
- Sessões no disco são `<lib>/YYYY/MM/DD/<HH-MM-SS>.json`, **não** `session.json`.
- **CUDA `CUDA_ARCHITECTURES` nunca só `-virtual` (PTX).** Faz o driver compilar (JIT) cada
  kernel na primeira transcrição real, travando minutos — testar `using CUDA0 backend` só
  prova que o *init* foi rápido, não prova nada sobre inferência de verdade. Usar código real
  (`"61;75;86;89"`, sem sufixo `-virtual`) e só então testar uma transcrição ponta a ponta.

## Portão

```
flutter analyze && flutter test --exclude-tags live
```

Golden é portão **local**, nunca de CI (fonte renderiza diferente entre Windows e Linux, e o
compare cross-OS dá falso positivo):

```
flutter test --tags golden
```

Prova que exit code não dá: ditar com F9 dentro de um `cmd.exe` rodando Claude Code e ver o texto
inteiro chegar **antes** do Enter. É o único teste do caminho conhost em modo cru.
