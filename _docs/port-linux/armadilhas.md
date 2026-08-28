# As armadilhas — sintoma → causa → correção

Cada uma destas custou tempo real no port do Dito. Estão na ordem em que aparecem.

---

## 1. Segurar a tecla vira metralhadora

**Sintoma:** modo *segurar* nunca segura; o log mostra dezenas de down/up para um toque.
**Causa:** o X11 forja um `KeyRelease` antes de cada repetição automática.
**Correção:** `XkbSetDetectableAutoRepeat(dpy, True, &supported)` na thread do hook.

---

## 2. Segurar a tecla desliga a gravação sozinha

**Sintoma:** no modo *alternar*, segurar a tecla por mais de meio segundo liga e desliga.
**Causa:** mesmo com auto-repeat detectável, ainda chegam `KeyPress` repetidos. O debounce de
250 ms não salva: o primeiro repeat do X11 vem em ~500 ms, fora da janela.
**Correção:** emitir borda só quando o estado **muda** (`if (last_down == down) continue`).
**Como pegar:** `xdotool keydown F10; sleep 0.5; xdotool keyup F10` e contar as bordas. Tem que dar
1 down e 1 up. No primeiro teste deu 3 downs para 2 toques — foi assim que apareceu.

---

## 3. O app trava ou o teclado congela ao instalar o hook

**Causa:** `XGrabKey` com `GrabModeSync` congela o teclado até você liberar.
**Correção:** `GrabModeAsync` nos dois parâmetros.

---

## 4. A tecla não funciona com Caps/Num Lock ligado

**Causa:** o grab é por combinação **exata** de modificadores. `LockMask` e `Mod2Mask` mudam o
estado.
**Correção:** registrar o grab para todas as combinações de lock (8 no total).

---

## 5. `XGrabKey` "funciona" mas nada acontece

**Causa:** ele não retorna erro — gera `BadAccess` **assíncrono**. Outro app já segura a tecla.
**Correção:** error handler + `XSync` para forçar a entrega, e restaurar o handler anterior (é
global do processo, o Chromium tem o dele).

---

## 6. Crash aleatório dentro do Xlib

**Causa:** duas threads usando a mesma `Display*`. Xlib só é thread-safe com `XInitThreads()`
chamado antes de **qualquer** chamada Xlib do processo — e o Chromium já inicializou o X antes do
addon carregar.
**Correção:** uma conexão por thread. `XOpenDisplay(nullptr)` na thread do hook, outra para as
operações de input, com mutex.

---

## 7. Acento sai errado ou não sai

**Causa:** `XTestFakeKeyEvent` manda **keycode**, não caractere. Se o keysym não estiver no teclado
atual, não existe tecla para bater.
**Correção:** remapear temporariamente um keycode livre para o keysym do caractere e restaurar
depois. Detalhe em `win32-para-x11.md`.
**Pegadinha dentro da pegadinha:** sem `XSync` depois do `XChangeKeyboardMapping`, a tecla bate
antes do mapa valer e sai o caractere errado.

---

## 8. Colar em terminal cola lixo (ou nada)

**Causa:** em terminal Linux `Ctrl+V` não cola — é `Ctrl+Shift+V`. E `xterm`/`urxvt`/`rxvt` não têm
nem isso.
**Correção:** classificar por `WM_CLASS`; terminal moderno → `Ctrl+Shift+V`; terminal burro →
digitar o texto.

---

## 9. Ícone do tray não aparece

**Causa:** `.ico` não renderiza no StatusNotifierItem.
**Correção:** PNG. **22×22** é o tamanho recomendado no Linux (16×16 é o do Windows).
Sem ImageMagick na máquina, `icotool -x` extrai os frames do próprio `.ico` sem reamostrar.

---

## 10. `apt install` falha inteiro por um nome de pacote

**Causa:** o Debian 13 renomeou pacotes na transição `time_t` de 64 bits:

| Nome antigo | Nome no Debian 13 |
|---|---|
| `libgtk-3-0` | `libgtk-3-0t64` |
| `libasound2` | `libasound2t64` |
| `libatspi2.0-0` | `libatspi2.0-0t64` |

Um nome inexistente em `deb.depends` derruba a instalação toda.
**Correção:** `apt-cache policy <nome>` em cada item antes de fixar a lista.

---

## 11. O `.deb` instala e o app não abre

**Causa:** `deb.depends` **substitui** o default do electron-builder — não estende. O que você
esquecer, some. Foi assim que `libatspi2.0-0t64` ficou de fora da primeira release, mesmo com o
binário linkando contra `libatspi.so.0`. Na máquina de dev não aparece, porque a lib já está lá.
**Correção:** derivar a lista do binário, nunca copiar de exemplo:

```bash
ldd dist/linux-unpacked/<app> | grep -oP '(?<= => )/\S+' | xargs -r dpkg -S | cut -d: -f1 | sort -u
dpkg-deb -f dist/*.deb Depends | tr ',' '\n'   # e comparar
```

**Ainda mais direto:** `apt-get -s install ./dist/*.deb` — simulação, não precisa de root, e prova
que tudo resolve.

---

## 12. O módulo nativo não carrega no app empacotado

**Sintoma:** funciona em `npm run dev`, quebra no `.deb`.
**Causa:** quem abre `.node`/`.so` é o `dlopen` do sistema operacional, que precisa de caminho real
em disco. Dentro do `asar` não existe caminho real.
**Correção:** `asarUnpack` de tudo que é nativo, e o loader apontando para `app.asar.unpacked`:

```json
"asarUnpack": [
  "native/build/Release/*.node",
  "node_modules/sherpa-onnx-node/**/*",
  "node_modules/sherpa-onnx-linux-x64/**/*"
]
```

```ts
join(app.getAppPath().replace('app.asar', 'app.asar.unpacked'), 'native', 'build', 'Release', file)
```

Confira no pacote gerado, não no código:
`dpkg-deb -c dist/*.deb | grep -E 'app.asar.unpacked.*\.(node|so)'`

---

## 13. Primeiro save de configuração falha com ENOENT

**Sintoma:** só em máquina nova; na de dev funciona.
**Causa:** o código fazia `mkdirSync(DATA_DIR)` e escrevia em `CONFIG_FILE`, assumindo mesma pasta.
No Windows era verdade; com XDG no Linux, `~/.local/share/dito` e `~/.config/dito` são pastas
diferentes e a segunda nunca foi criada.
**Correção:** `mkdirSync(dirname(CONFIG_FILE), { recursive: true })`.
**Regra geral:** depois de mexer em caminhos, procure **todo** `mkdirSync` do projeto e confira se
ainda cobre o arquivo escrito na sequência.

---

## 14. Auto-update do `.deb` não acontece e não dá erro

**Causa:** o electron-updater escolhe a classe por `resources/package-type`. Sem esse arquivo, cai
no `AppImageUpdater`, que fica **inerte** — nunca checa, só loga um warning.
**Correção:** o electron-builder escreve o arquivo sozinho no target deb. Confira:
`dpkg-deb -c dist/*.deb | grep package-type`.

---

## 15. Update no Linux busca um arquivo que não existe

**Sintoma:** `Cannot find channel "latest-linux.yml" update info: HttpError: 404`.
**Causa:** no Linux x64 o manifesto chama **`latest-linux.yml`**, não `latest.yml`. Um feed próprio
que só serve `/update/win/` devolve 404.
**Correção:** rota por plataforma no feed, e anexar o `latest-linux.yml` à release.
**Vantagem:** esse 404 é um ótimo sinal — significa que o resto da cadeia está certa.

---

## 16. Apagar `latest.yml` da release "por limpeza" mata o update

**Causa:** ele carrega o `sha512` que só o electron-builder calcula, e é o que o feed serve.
**O que pode sair:** `.blockmap` (só acelera download incremental; o `.deb` nem usa).
**O que não pode:** `latest.yml` / `latest-linux.yml`.

---

## 17. Não dá para gerar o `.exe` na máquina Linux

**Causa:** `electron-builder --win` precisa de `wine`.
**Consequência:** a release cortada no Linux sai só com o `.deb`.
**Correção:** anexar o `.deb` à mesma release que já tem o `.exe` — o feed continua achando as duas
plataformas em `releases/latest`, e nada muda no servidor.

---

## 18. Erro de gate que parece erro de app

**Sintoma:** o teste automatizado diz que a colagem falhou, mas o app está certo.
**Causa:** `xdotool key --window <id> ctrl+s` usa `XSendEvent`, e **apps GTK ignoram evento
sintético** enviado assim.
**Correção:** `xdotool key ctrl+s` sem `--window` (usa XTest, é evento real).
**Lição:** quando o gate falha, desconfie do gate antes de desconfiar do código.
