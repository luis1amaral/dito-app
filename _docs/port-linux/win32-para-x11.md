# Win32 → X11: tradução API por API

O contrato do addon do Dito tem 9 funções. Esta é a tradução de cada peça, com o código que
funcionou. Vale para qualquer app que precise de tecla global, injeção de texto ou rastreio da
janela em foco.

Bibliotecas: `-lX11 -lXtst -lXi`. Headers: `libx11-dev`, `libxtst-dev`, `libxi-dev`.

---

## Tabela de tradução

| Win32 | X11 | Observação |
|---|---|---|
| `SetWindowsHookEx(WH_KEYBOARD_LL)` | `XGrabKey` no root window | Suprime a tecla, sem root |
| Retornar 1 no hook (suprimir) | `owner_events=False` no grab | Já é o padrão do grab |
| `GetAsyncKeyState` | `XQueryKeymap` | Estado físico de todas as teclas |
| `GetForegroundWindow` | `_NET_ACTIVE_WINDOW` no root | Propriedade EWMH |
| `GetClassNameW` | `XGetClassHint` (`WM_CLASS`) | `res_class` primeiro, `res_name` como fallback |
| `GetWindowTextW` | `_NET_WM_NAME` (UTF8) → `XFetchName` | O segundo é latin-1, só como fallback |
| `SetForegroundWindow` + `AttachThreadInput` | **nada** | Não existe o problema; ver README |
| `SendInput(KEYEVENTF_UNICODE)` | Remapear keysym + `XTestFakeKeyEvent` | Ver "digitar Unicode" |
| `SendInput` (tecla virtual) | `XKeysymToKeycode` + `XTestFakeKeyEvent` | |
| `OpenClipboard`/`SetClipboardData` | `clipboard.writeText` do Electron | Não reimplemente em C++ |
| `MsgWaitForMultipleObjects` | `select()` no `ConnectionNumber(dpy)` | Junta eventos + timer |
| `PostThreadMessage` para parar | `pipe()` + `select()` | Self-pipe |

---

## Tecla global com supressão

`XGrabKey` no root window entrega `KeyPress` **e** `KeyRelease` e a tecla **não** chega no cliente
em foco. É o equivalente exato de `WH_KEYBOARD_LL` com supressão, e não exige root nem grupo `input`.

A pegadinha: o grab é por **combinação exata de modificadores**. Se Caps Lock estiver ligado, o
estado é outro e o grab não pega. Registre todas as combinações de lock:

```cpp
const unsigned int kLockMasks[] = {
    0, LockMask, Mod2Mask, Mod2Mask | LockMask,
    Mod3Mask, Mod3Mask | LockMask, Mod3Mask | Mod2Mask, Mod3Mask | Mod2Mask | LockMask};

for (const unsigned int mask : kLockMasks)
  XGrabKey(dpy, keycode, mask, root, False, GrabModeAsync, GrabModeAsync);
```

`GrabModeAsync` nos dois modos: sem isso o teclado congela até você liberar o grab.

### Detectar falha do grab

`XGrabKey` não retorna erro — ele gera um `BadAccess` **assíncrono**. Instale um handler, force o
flush com `XSync`, e restaure o handler logo em seguida (o handler é global do processo, e o
Chromium tem o dele):

```cpp
std::atomic<int> g_grab_error{0};
int GrabErrorHandler(Display*, XErrorEvent* e) { g_grab_error.store(e->error_code); return 0; }

XErrorHandler previous = XSetErrorHandler(GrabErrorHandler);
for (...) XGrabKey(...);
XSync(dpy, False);              // sem isso o erro ainda nao chegou
XSetErrorHandler(previous);     // janela de interferencia minima
const bool installed = g_grab_error.load() == 0;
```

`BadAccess` significa que **outro programa já segura a tecla**. Reporte, não tente de novo.

---

## Auto-repeat: a armadilha nº 1

Por padrão o X11 forja um `KeyRelease` antes de cada `KeyPress` de repetição. Segurar F9 vira uma
metralhadora de down/up e o modo *segurar* nunca segura.

```cpp
Bool detectable = False;
XkbSetDetectableAutoRepeat(dpy, True, &detectable);  // exige <X11/XKBlib.h>
```

**Isso não basta.** Mesmo com auto-repeat detectável, ainda chegam `KeyPress` repetidos (sem o
release falso). Se o app faz *toggle* no key-down, a repetição desliga a gravação sozinha. Emita
borda só na **transição**:

```cpp
if (binding.last_down == down) continue;   // repeticao: nao e borda
binding.last_down = down;
EmitEdge(...);
```

E deixe o estado físico ser o árbitro, para um evento perdido não travar a máquina de estados:

```cpp
char keymap[32] = {};
XQueryKeymap(dpy, keymap);
const bool physical = (keymap[code / 8] & (1 << (code % 8))) != 0;
binding.last_down = physical;   // o teclado manda, nao o historico de eventos
```

---

## Loop de eventos com timer

Precisa reagir a evento X **e** fazer polling periódico do estado físico. `XNextEvent` bloqueia.
A solução é `select()` no descritor da conexão, mais um self-pipe para parar:

```cpp
while (running_.load()) {
  while (XPending(dpy) > 0) { XEvent e; XNextEvent(dpy, &e); /* ... */ }

  XQueryKeymap(dpy, keymap);   // tick de 100 ms
  /* ... */

  fd_set fds; FD_ZERO(&fds);
  FD_SET(ConnectionNumber(dpy), &fds);
  FD_SET(wake_pipe_[0], &fds);
  struct timeval timeout{}; timeout.tv_usec = 100000;
  select(std::max(x_fd, wake_pipe_[0]) + 1, &fds, nullptr, nullptr, &timeout);
}
```

Parar de outra thread: `write(wake_pipe_[1], &byte, 1)`. O `select` acorda na hora.

**Uma `Display*` por thread.** Xlib só é thread-safe com `XInitThreads()` chamado antes de qualquer
outra chamada Xlib do processo — e o Chromium já inicializou o X muito antes do seu addon carregar.
Não conte com isso: abra sua própria conexão na thread do hook.

---

## Janela em foco

```cpp
Window ActiveWindow(Display* dpy) {
  const Atom property = XInternAtom(dpy, "_NET_ACTIVE_WINDOW", True);
  if (property == None) return 0;
  Atom type; int format; unsigned long count, bytes; unsigned char* data = nullptr;
  if (XGetWindowProperty(dpy, DefaultRootWindow(dpy), property, 0, 1, False,
                         AnyPropertyType, &type, &format, &count, &bytes, &data) != Success)
    return 0;
  Window active = 0;
  if (data) { if (format == 32 && count >= 1) active = *(unsigned long*)data; XFree(data); }
  return active;
}
```

`XInternAtom(..., True)` = só devolve o átomo se já existir. Se voltar `None`, o gerenciador de
janelas não implementa EWMH (raro em desktop moderno) — degrade, não quebre.

Título: prefira `_NET_WM_NAME` (UTF-8). `XFetchName` lê `WM_NAME`, que é latin-1 e corta acento.

---

## Colar: quem faz o quê

O Windows precisa de clipboard próprio em C++ porque o `SetClipboardData` é da API. No Linux **não
reimplemente**: o Electron já é dono da seleção X11 e responde ao `SelectionRequest`. O addon só
sintetiza a tecla.

```ts
// src/main/native.ts
export function paste(text: string): boolean {
  if (!addon) return false
  if (process.platform === 'linux') clipboard.writeText(text)
  return addon.paste(text)
}
```

Menos C++, menos chance de erro, e o dono da seleção continua vivo enquanto o app estiver aberto.

### Qual atalho, por tipo de janela

| Tipo | Atalho | Por quê |
|---|---|---|
| GUI comum | `Ctrl+V` | |
| Terminal moderno (gnome-terminal, konsole, alacritty, kitty, tilix, wezterm) | `Ctrl+Shift+V` | Em terminal `Ctrl+V` é literal, não cola |
| `xterm`, `urxvt`, `rxvt` | **digitar o texto** | Não têm `Ctrl+Shift+V` |

É a mesma classe de problema do `ConsoleWindowClass` no Windows, com outra cara. Classifique por
`WM_CLASS` em minúsculas.

```cpp
XTestFakeKeyEvent(dpy, ctrl_code, True, 0);
if (shift) XTestFakeKeyEvent(dpy, shift_code, True, 0);
XTestFakeKeyEvent(dpy, key_code, True, 0);
XTestFakeKeyEvent(dpy, key_code, False, 0);
if (shift) XTestFakeKeyEvent(dpy, shift_code, False, 0);
XTestFakeKeyEvent(dpy, ctrl_code, False, 0);
XFlush(dpy);
```

---

## Digitar Unicode (acento pt-BR)

`KEYEVENTF_UNICODE` não tem equivalente. A técnica (a mesma do `xdotool`): achar um keycode **sem
keysym nenhum**, remapear para o caractere, bater a tecla, restaurar.

```cpp
// keysym: latin-1 e o proprio codepoint; acima disso, faixa Unicode do X11
KeySym symbol = cp < 0x100 ? (KeySym)cp : (KeySym)(cp | 0x01000000u);

// atalho: se o caractere ja existe no teclado, nao remapeie (evita MappingNotify a cada letra)
KeyCode existing = XKeysymToKeycode(dpy, symbol);
if (existing && XkbKeycodeToKeysym(dpy, existing, 0, 0) == symbol) { Tap(existing); continue; }

KeySym mapping[2] = {symbol, symbol};        // slot 0 e 1: estado de shift nao importa
XChangeKeyboardMapping(dpy, spare, 2, mapping, 1);
XSync(dpy, False);                           // sem sync, a tecla bate antes do mapa valer
Tap(spare);
usleep(4000);                                // xdotool usa 12 ms; 4 ms aguenta GTK e VTE
```

Achar o keycode livre — varra de cima para baixo procurando um com **todos** os slots `NoSymbol`:

```cpp
int min_code, max_code; XDisplayKeycodes(dpy, &min_code, &max_code);
int per_code; KeySym* map = XGetKeyboardMapping(dpy, min_code, max_code - min_code + 1, &per_code);
for (int code = max_code; code >= min_code; --code) { /* todos NoSymbol? -> spare = code */ }
```

**Restaure o mapa no fim** (`NoSymbol` de volta), senão você deixa o teclado do usuário sujo.

---

## `binding.gyp` para dois sistemas sem regressão

Nome do alvo por variável, fontes por condição. O código Windows não é tocado:

```python
{
  "variables": {
    "conditions": [
      ["OS=='win'",  { "dito_module%": "dito_win32" }],
      ["OS!='win'",  { "dito_module%": "dito_linux" }]
    ]
  },
  "targets": [{
    "target_name": "<(dito_module)",
    "include_dirs": ["<!@(node -p \"require('node-addon-api').include\")", "src"],
    "defines": ["NAPI_DISABLE_CPP_EXCEPTIONS"],
    "conditions": [
      ["OS=='win'",   { "sources": ["src/addon.cc", "src/input.cc", "src/key_hook.cpp"],
                        "libraries": ["user32.lib"] }],
      ["OS=='linux'", { "sources": ["src/addon_x11.cc", "src/input_x11.cc", "src/key_hook_x11.cpp"],
                        "libraries": ["-lX11", "-lXtst", "-lXi"],
                        "cflags_cc": ["-std=c++17", "-fexceptions"] }]
    ]
  }]
}
```

Arquivo de bridge N-API **separado** por plataforma (`addon.cc` / `addon_x11.cc`). Tentar um só,
cheio de `#ifdef`, é o que transforma port em bagunça.

Do lado do JS, o nome do `.node` acompanha:

```ts
const file = process.platform === 'linux' ? 'dito_linux.node' : 'dito_win32.node'
```
