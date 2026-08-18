# Fork de `desktop_multi_window` 0.3.0

Cópia do pacote da Mixin (Apache-2.0), só com a plataforma Windows. Existe por um motivo só:
**a janela do HUD não pode roubar o foco.**

## O problema, medido

O Dito mostra uma pílula flutuante toda vez que você segura F9 — enquanto você está escrevendo
dentro de outro programa. Se essa janela tomar o foco, o texto é colado nela em vez de no seu campo,
e o Ctrl+V se perde.

Com o pacote original, o espinho da Fase 0.5 mediu:

```
WS_EX_NOACTIVATE ............ OK
WS_EX_TOOLWINDOW ............ OK
WS_EX_TOPMOST ............... OK
foco preservado ............. FALHOU (a janela roubou o foco)
```

Os estilos aplicavam e mesmo assim o foreground mudava. Aplicar `WS_EX_NOACTIVATE` depois, pelo
Dart, **chega tarde**: quando o primeiro código Dart roda, a janela já existe e o foco já foi levado.

## Causa raiz

Duas linhas do pacote original, ambas durante a criação da janela:

1. `win32_window.cpp` — `CreateWindow(...)` sem estilos estendidos. `WS_EX_NOACTIVATE` só tem efeito
   quando informado no `CreateWindowEx`; via `SetWindowLongPtr` depois, não retroage.
2. `win32_window.cpp:262` — `SetChildContent()` chamava `SetFocus(child_content_)`
   incondicionalmente, dentro do `OnCreate`. É o template padrão do Flutter, e é o que puxava o
   foreground.

## O que mudou

| arquivo | mudança |
|---|---|
| `windows/window_configuration.h` | campo `focusable` (padrão `true`) |
| `windows/win32_window.h` | `SetFocusable()` e o membro `focusable_` |
| `windows/win32_window.cpp` | `CreateWindow` → `CreateWindowEx`; janela não-focável nasce `WS_POPUP` + `WS_EX_NOACTIVATE\|TOOLWINDOW\|TOPMOST` |
| `windows/win32_window.cpp` | `SetFocus` só quando `focusable_` |
| `windows/win32_window.cpp` | `Show()` de janela não-focável usa `SetWindowPos(SWP_SHOWWINDOW\|SWP_NOACTIVATE)` |
| `windows/multi_window_manager.cc` | aplica `SetFocusable(config.focusable)` **antes** do `Create` |
| `lib/src/window_configuration.dart` | expõe `focusable` |

`macos/`, `linux/` e `example/` foram removidos — o Dito é só Windows.

## Como usar

```dart
// HUD: nunca toma foco.
WindowController.create(const WindowConfiguration(arguments: 'hud', focusable: false));

// Cartão de revisão: toma foco de propósito, e o devolve antes de colar.
WindowController.create(const WindowConfiguration(arguments: 'review'));
```

## A prova

`tool/spike_focus.dart` abre o Bloco de Notas, dá o foco a ele, mostra o HUD e confere três coisas:
o HUD apareceu, o HUD **não** é o foreground, e o foco continua no Bloco de Notas.

```bash
flutter build windows --debug --target=tool/spike_focus.dart && ./build/windows/x64/runner/Debug/dito_app.exe
```

O veredito sai em `spike_result.txt` e o processo devolve exit code 0 quando passa. Medido, 4/4:

```
foreground antes ............ 985934 [pid 17580] classe="Notepad" titulo="Sem título - Bloco de Notas"
exstyle ..................... 0x8000088
WS_EX_NOACTIVATE ............ OK
WS_EX_TOOLWINDOW ............ OK
WS_EX_TOPMOST ............... OK
HUD visivel ................. OK
HUD fora do foreground ...... OK
foco continua no notepad .... OK
VEREDITO .................... PASSA
```

Duas armadilhas do teste, que custaram duas rodadas erradas:

- **Não** assertar "o foreground não mudou": ele muda por conta do ambiente, sem o HUD ter culpa.
  O que se assere é que o **HUD nunca é o foreground**.
- Achar a janela do Bloco de Notas **pelo PID** do processo lançado. `FindWindow` por classe pega
  uma janela de execução anterior e o teste passa a mentir.

## Ao atualizar o pacote de origem

Reaplicar as mudanças acima e **rodar de novo o espinho**. `VEREDITO ... PASSA` é a única prova
que vale.

## Correção 2026-08-17: a sub-janela nascia invisível (preta) em release

Duas causas, ambas na criação da janela:

1. **`DwmEnableBlurBehindWindow` com região vazia** (o truque de alfa por pixel) não compõe com o
   swapchain do Flutter em release: a janela inteira fica com alfa zero — invisível ao olho e preta
   no `PrintWindow(PW_RENDERFULLCONTENT)`, mesmo com `IsWindowVisible = TRUE`. O bloco foi removido
   de `win32_window.cpp`; a forma do overlay vem de `SetWindowRgn` (`window.setHitRect` do
   dito_win32, com raio de canto).
2. **`FlutterWindow::OnCreate` não chamava `flutter_controller_->ForceRedraw()`** (o runner
   principal chama). Sem isso a primeira frame nunca é apresentada e a superfície fica preta para
   sempre. Além do `ForceRedraw`, a swapchain só passa a apresentar depois de um **resize real com
   a janela visível** — o `window.showNoActivate` do dito_win32 faz um jiggle de 1px após mostrar.

Prova: captura de tela real (GDI `CopyFromScreen`) com a pílula "Gravando", "Transcrevendo",
"SEM ÁUDIO" e o cartão de revisão compostos na tela — o espinho antigo só validava
`IsWindowVisible`, que era verdadeiro mesmo com a janela invisível.
