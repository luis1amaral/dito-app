# Dito no Linux — estado real

Documento honesto do que **funciona**, do que é **stub** e do que **precisa de máquina Linux**
para validar. O Windows continua sendo a verdade do produto; nada aqui regride o Windows.

## Resumo

O alvo Linux do Flutter existe (`linux/`) e a base de código já isola as partes específicas de
plataforma atrás de interfaces, com implementação Windows real e **stub** Linux. Isso deixa o app
**compilar e bootar** no Linux (janela principal), mas **sem atalho global, sem bandeja e sem os
alertas nativos** — esses são os próximos passos.

> ⚠️ Não validei um build Linux nesta sessão: o ambiente de build (Flutter + GTK) não estava
> disponível. O que está aqui é a abstração + os stubs, revisados por leitura. Buildar/validar exige
> uma máquina Linux com `clang cmake ninja-build libgtk-3-dev` e `flutter config --enable-linux-desktop`.

## O que já está abstraído (Windows real + Linux stub)

| Seam | Interface | Windows | Linux (hoje) |
|------|-----------|---------|--------------|
| Atalho global | `HotkeyService` (`lib/keys/hotkey_service.dart`) | `WindowsHotkeyService` (hook `WH_KEYBOARD_LL` via `dito_win32`) | `LinuxHotkeyService` — **stub**, `hookInstalled=false` |
| Alertas (balão + som) | `AlertService` (`lib/output/alert_service.dart`) | `WindowsAlertService` (`DitoWin32`) | `LinuxAlertService` — só loga |

A escolha é feita por `Platform.isWindows` nas factories `createHotkeyService()` /
`createAlertService()`. O `boot.dart` nunca nomeia plataforma.

Além disso, no `boot.dart`/`main.dart` os pontos Win32 diretos (bandeja, `adoptAsPanel`) ficaram
guardados por `Platform.isWindows`, então o boot no Linux não estoura neles.

## O que ainda é específico de Windows (precisa de impl Linux)

1. **Atalho global (o mais importante).** O push-to-talk depende de capturar tecla física mesmo
   sem foco. No Linux não há equivalente único: as opções são **evdev** (`/dev/input`, precisa de
   permissão/grupo `input`), **X11 XGrabKey** (só X11, quebra no Wayland) ou o **portal XDG
   GlobalShortcuts** (Wayland/Flatpak, o caminho mais moderno). Sem isso, `dead`/`quiet` não têm
   como serem exercitados porque não há como iniciar a gravação por tecla.
2. **Bandeja (tray).** `TrayController` é Win32. No Linux: `libappindicator`/`StatusNotifierItem`
   (via um pacote como `tray_manager`, que suporta Linux).
3. **Colagem nativa.** `NativePasteBackend`/`dito_win32` usam `SendInput`. No Linux: `xdotool`/
   `ydotool` (Wayland) ou libs de input.
4. **Alertas nativos.** Notificação via `libnotify`/`notify-send`; som via `canberra`/`paplay`.
5. **Janela sem foco (HUD) e panel.** O fork `desktop_multi_window` e o `WS_EX_NOACTIVATE` são
   Windows. No Linux o HUD precisa de layer-shell (wlr-layer-shell no Wayland) ou override-redirect
   no X11. Hoje `_openSubWindows()` já falha graciosamente (try/catch) — o app roda sem HUD/cartão.
6. **O motor (`dito-engine`).** A captura de áudio em si é do sidecar Python (`../dito-app`), que usa
   `sounddevice`/PortAudio (cross-platform). Para o Linux é preciso empacotar o engine para Linux
   (PyInstaller no Linux) e ajustar `defaultEngineCandidates()` (hoje monta caminhos com `\`).

## Próximos passos sugeridos (ordem)

1. Empacotar `dito-engine` para Linux e apontar `EngineClient` para ele.
2. `LinuxHotkeyService` real via portal XDG GlobalShortcuts (Wayland-first) com fallback evdev.
3. Bandeja via `tray_manager` (tem Linux).
4. Alertas via `notify-send` + `paplay`.
5. HUD sem foco via layer-shell.

Cada passo é isolado atrás da interface já criada, então dá para entregar um de cada vez sem tocar
no Windows.
