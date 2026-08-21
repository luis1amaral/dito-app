# Dito no Linux — estado real

Documento honesto do que **funciona**, do que é **stub** e do que **precisa de máquina Linux**
para validar. O Windows continua sendo a verdade do produto; nada aqui regride o Windows.

O app é **X11 only** — nada de Wayland/layer-shell/portal XDG. Todo o mecanismo nativo (atalho
global, janela flutuante, colagem) usa GTK+X11 direto via `packages/dito_win32/linux/`.

## O que funciona de verdade hoje

| Área | Mecanismo | Onde |
|------|-----------|------|
| Atalho global (F9/F10) | `XGrabKey` real, tick-based (nunca confia em key-up) | `dito_win32_plugin.cc` — `StartKeyHook`/`X11ThreadMain` |
| HUD flutuante, sem foco | `gtk_window_set_accept_focus(FALSE)` + `keep_above` + `decorated(FALSE)` + `skip_taskbar_hint`, setado na criação da janela (`focusable: false`) | `desktop_multi_window/linux/desktop_multi_window_plugin.cc` + `window.adoptAsHud` |
| Review flutuante, focável | mesmos hints, sem `accept_focus(FALSE)` — a janela pode receber foco de teclado de propósito | `window.adoptAsPanel` |
| Bandeja (tray) | `libayatana-appindicator3`/`libappindicator3` via `dlopen` | `dito_win32_plugin.cc` — `tray.*` |
| Colagem/Enter/chord | shell-out `xdotool` | `dito_win32_plugin.cc` — `input.*` |
| Restaurar foco antes de colar | EWMH `_NET_ACTIVE_WINDOW` (ler antes, mandar client message pra restaurar) | `dito_win32_plugin.cc` — `focus.take`/`focus.giveBack` |
| Clique-através no canvas transparente | `gtk_widget_shape_combine_region` | `dito_win32_plugin.cc` — `window.setHitRect` |

`HotkeyService.createHotkeyService()` (`lib/keys/hotkey_service.dart`) devolve
`WindowsHotkeyService` em qualquer plataforma — o nome é herdado do Windows, mas a classe já é
cross-platform (fala com `dito_win32` via `DitoWin32.keys`, e cada plataforma implementa o hook
nativo por trás). Não existe mais `LinuxHotkeyService` no código.

## O que ainda é stub/pendente

1. **Alertas nativos** (`lib/output/alert_service.dart`, `LinuxAlertService`) — só loga, sem
   `notify-send`/`libnotify` nem som via `canberra`/`paplay`.
2. **`test.*` do `dito_win32`** (`createEditTarget`/`readEditTarget`/`destroyEditTarget`/
   `ownsForeground`) — sem implementação no Linux, usados só por ferramentas de teste, retornam
   `not_implemented` (nada na produção chama isso).

## Próximos passos sugeridos (ordem)

1. Alertas via `notify-send` + `paplay`/`canberra`.
2. `test.*` do `dito_win32` no Linux, se algum dia existir um espinho tipo `spike_focus.dart`
   equivalente pra rodar em CI Linux.

Cada passo é isolado atrás da interface já criada, então dá para entregar um de cada vez sem tocar
no Windows.
