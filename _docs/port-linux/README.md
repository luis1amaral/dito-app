# Playbook — portar um app Electron de Windows para Linux

Escrito depois de portar o **Dito 2.0.10** (Electron + TypeScript + addon nativo Win32) para
Linux/X11 em uma sessão. Não é o relato do que aconteceu: é a lista do que **quebra**, por quê, e o
que fazer, para o próximo port não custar o mesmo aprendizado.

Documentos deste diretório:

| Arquivo | O que é |
|---|---|
| `README.md` | Este playbook |
| `win32-para-x11.md` | Tabela de tradução API por API, com o código que funcionou |
| `armadilhas.md` | As 12 armadilhas, cada uma com sintoma → causa → correção |
| `gates.md` | Como provar que funciona sem depender de "deve funcionar" |

---

## A regra que mais economiza tempo

**Antes de escrever uma linha, ache a superfície de contato com o sistema operacional e meça ela.**

No Dito essa superfície eram **9 funções** num addon N-API. Fluxo de ditado, motor de fala, janelas,
IPC, telas — nada disso conhecia o Windows. Portar virou "escrever a outra metade de um arquivo",
não "portar um app".

Como medir isso em 5 minutos:

```bash
# 1. o que importa Win32 / é condicional de plataforma
grep -rn "process.platform\|windows.h\|win32\|\.exe\|\\\\\\\\" src/ native/ --include=*.ts --include=*.cc

# 2. qual e o contrato do addon nativo (a lista de exports e a superficie inteira)
grep -n "exports.Set" native/src/addon.cc

# 3. o que o empacotador ja assume
python3 -c "import json;print(json.dumps(json.load(open('package.json'))['build'],indent=2))"
```

Se a superfície for grande e espalhada, **pare e refatore ela para um só lugar antes de portar**.
Portar código espalhado é o que faz um port de 1 dia virar de 1 semana.

---

## Reconhecimento do ambiente — rode ANTES de decidir a arquitetura

O resultado disto **muda o desenho**, não só a configuração. Rode primeiro:

```bash
echo "sessao: $XDG_SESSION_TYPE | desktop: $XDG_CURRENT_DESKTOP | display: $DISPLAY$WAYLAND_DISPLAY"
id                                            # grupos: 'input' permite ler /dev/input
ls -l /dev/uinput                             # injecao de teclado a nivel de kernel
for c in g++ make python3 xdotool wine dpkg-deb fakeroot pkexec; do
  printf "%-12s %s\n" "$c" "$(command -v $c || echo AUSENTE)"; done
for h in Xlib.h extensions/XTest.h extensions/XInput2.h; do
  [ -f /usr/include/X11/$h ] && echo "OK  $h" || echo "FALTA $h"; done
```

**A resposta de `XDG_SESSION_TYPE` decide o projeto inteiro:**

| | X11 | Wayland |
|---|---|---|
| Tecla global com supressão | `XGrabKey` — funciona | Impossível sem portal; portal não dá *key release* |
| Hold-to-talk (segurar) | Funciona | Não funciona (só atalho de disparo) |
| Injetar texto | XTest — funciona | Só `ydotool` (uinput, precisa de udev/root) ou `wtype` (só wlroots — **não** GNOME/KDE) |
| Saber a janela em foco | `_NET_ACTIVE_WINDOW` | Não existe API para clientes |

Se o alvo for Wayland, **o desenho é outro** (evdev + uinput, com regra de udev no `postinst`).
Não descubra isso depois de escrever o addon X11.

---

## O erro conceitual que custa mais caro

> Traduzir o Windows linha a linha em vez de perguntar **por que aquele código existe**.

O Dito tinha `ForceForeground()` + `AttachThreadInput()` + `WaitForForeground()` — três funções e
uns 40 linhas. Existem porque o **Windows recusa** dar o primeiro plano a quem não o tem, e o truque
é anexar a fila de input da thread dona para "pegar emprestado" esse direito.

No X11 esse problema **não existe**. Traduzir aquilo teria criado um roubo de foco que hoje não
acontece — um defeito novo, inventado pelo port.

A decisão certa foi **não portar** e trocar por outra coisa:

```cpp
// Windows rouba o primeiro plano de volta; o X11 nao precisa, entao foco movido = colagem recusada.
if (!TargetIsForeground()) return false;
```

Se o foco mudou no meio do ditado, a colagem é **recusada** e o texto vai para a área de
transferência. Comportamento melhor que o do Windows, e menos código.

**Pergunta a fazer em cada função antes de portar:** *que problema do Windows isso resolve, e esse
problema existe aqui?* Boa parte de um port é decidir o que **não** escrever.

---

## As 6 coisas que sempre quebram (detalhe em `armadilhas.md`)

1. **Auto-repeat do X11** — sem `XkbSetDetectableAutoRepeat`, segurar uma tecla gera
   `release/press` falsos e o modo *segurar* nunca segura. E mesmo **com** ele, ainda chegam
   `KeyPress` repetidos: deduplique por transição de estado, ou a repetição desliga a gravação
   sozinha no modo *alternar*.
2. **Xlib não é thread-safe numa conexão** — uma `Display*` por thread. Nunca compartilhe a conexão
   do Chromium.
3. **Ícone de tray `.ico` não renderiza** no StatusNotifierItem — precisa de PNG (22×22 é o tamanho
   recomendado no Linux, contra 16×16 no Windows).
4. **Nomes de pacote mudaram no Debian 13** (transição `time_t` 64-bit): `libgtk-3-0` →
   `libgtk-3-0t64`, `libasound2` → `libasound2t64`, `libatspi2.0-0` → `libatspi2.0-0t64`. Um nome
   inexistente em `deb.depends` faz o `apt install` inteiro falhar.
5. **`deb.depends` substitui o default do electron-builder inteiro** — o que você não listar, some.
   Foi assim que eu deixei `libatspi2.0-0t64` de fora na 2.0.10, mesmo com o binário linkando contra
   ela. Ver "como não errar isso" abaixo.
6. **Binário nativo dentro do `asar` não carrega** — quem abre é o `dlopen` do SO, que precisa de
   caminho real em disco. Tudo que é `.node`/`.so` vai em `asarUnpack`.

### Como não errar o `deb.depends` (o método, não a lista)

Não copie lista de lugar nenhum — **derive do binário**:

```bash
npm run pack:linux
# 1. o que o Electron realmente carrega
ldd dist/linux-unpacked/<app> | grep -oP '(?<= => )/\S+' | xargs -r dpkg -S 2>/dev/null \
  | cut -d: -f1 | sort -u
# 2. o que o SEU addon e as libs nativas carregam
readelf -d native/build/Release/*.node node_modules/<pacote-nativo>/*.so | grep NEEDED
# 3. cada nome existe na distro alvo?
for p in <lista>; do apt-cache policy "$p" | head -2; done
# 4. o pacote gerado declara o que precisa?
dpkg-deb -f dist/*.deb Depends | tr ',' '\n'
```

O passo 4 contra o passo 1 é o que pega o que faltou. **Faça isso antes de publicar**, não depois.

---

## Onde os arquivos moram (XDG) — e a armadilha do `mkdir`

No Windows tudo mora num diretório só. No Linux, não:

| | Caminho | Variável |
|---|---|---|
| Configuração | `~/.config/<app>` | `$XDG_CONFIG_HOME` — é o que `app.getPath('appData')` devolve |
| Dados (modelos, histórico) | `~/.local/share/<app>` | `$XDG_DATA_HOME` |
| Estado (log) | `~/.local/state/<app>` | `$XDG_STATE_HOME` |

Deixar 3 GB de modelo de fala em `~/.config` é errado e o usuário sente (backup de dotfiles, sync).

**A armadilha:** separar esses diretórios quebra todo código que fazia
`mkdirSync(DATA_DIR)` e logo depois escrevia em `CONFIG_FILE` — assumindo que era a mesma pasta.
No Linux não é mais, e o primeiro save falha com `ENOENT` numa máquina nova.

```ts
// No Linux config e dados sao pastas diferentes, entao as duas precisam existir.
mkdirSync(dirname(CONFIG_FILE), { recursive: true })
mkdirSync(DATA_DIR, { recursive: true })
```

Depois de mexer em caminhos, **procure todo `mkdirSync` do projeto** e confira se ele ainda cobre o
arquivo que é escrito na sequência.

---

## Auto-update de `.deb` — funciona, e como

Confirmado lendo `electron-updater` 6.8.9:

- A escolha do updater no Linux é feita por **um arquivo**: `resources/package-type`. Se contém
  `deb` → `DebUpdater`; `rpm` → `RpmUpdater`. O electron-builder escreve isso sozinho no target deb.
  Sem ele, cai no `AppImageUpdater`, que fica **inerte** — não quebra, só nunca atualiza.
- O manifesto no Linux x64 chama **`latest-linux.yml`** (`-linux` + sufixo de arch, vazio para x64).
  Não é `latest.yml`. Se o feed é um proxy próprio, ele precisa de rota por plataforma.
- Instala com `pkexec /bin/bash -c 'dpkg -i <arquivo>'`, com fallback `apt-get install -f -y`.
  **Sempre pede senha (polkit)** — isso é do sistema operacional, não da lib; instalar em `/opt`
  exige privilégio. Não prometa update silencioso no Linux.
- **Não há download incremental** para `.deb` (`.blockmap` não é gerado nem usado) — é sempre o
  pacote inteiro.
- Alvos que elevam privilégio **pulam** o install-on-quit. O fluxo certo é botão explícito chamando
  `quitAndInstall()`, não confiar em instalar ao fechar.

---

## Não dá para gerar o `.exe` no Linux sem `wine`

Se a máquina de build não tem `wine`, `electron-builder --win` não roda. Consequência prática: a
release cortada no Linux sai **só com o `.deb`**.

Duas saídas, escolha antes de publicar:

- **Anexar o `.deb` à mesma release que já tem o `.exe`** (foi o que fizemos). O feed continua
  achando as duas plataformas em `releases/latest`, e nada precisa mudar no servidor.
- Cortar release nova só-Linux — aí o resolvedor do feed precisa **varrer releases anteriores**
  atrás do asset do Windows, senão uma release só-Linux apaga o Windows do instalador.

---

## O que precisa de `sudo` (e você não tem)

Um agente normalmente não tem senha. Separe cedo o que dá para fazer e o que precisa ir para o
usuário em um bloco só, no fim:

- `apt purge` / `apt install ./pacote.deb` / `apt clean`
- qualquer `rm` em `/opt`, `/usr`, `/var`

O que **dá** para fazer sem sudo e vale muito:
- `apt-get -s install ./pacote.deb` — **simulação**, prova que as dependências resolvem
- `apt-get -s purge <pacote>` — mostra o raio de destruição antes de sugerir remoção
- `dpkg-deb -c` / `-f` / `-I` — inspecionar o pacote gerado por dentro
- `dpkg -S <caminho>` — descobrir se um diretório em `/opt` virou órfão

---

## Segurança da release: o que sai e o que fica

Varra o pacote **e** o `asar` antes de publicar:

```bash
dpkg-deb -c dist/*.deb | awk '{print $6}' | grep -Ei '\.map$|\.env|\.pem$|\.key$|secret|token'
npx asar list dist/linux-unpacked/resources/app.asar | grep -E '^/out.*\.map$'
```

- `.map` de **bibliotecas de terceiros** (electron-updater etc.) é conteúdo público do npm — não é
  vazamento.
- `.map` gerado do **seu** `out/` é: significa que você publicou seu código-fonte. É esse que
  importa.
- `.blockmap` numa release **não é sensível** (mapa de hash para download incremental) — pode sair.
- **`latest.yml` NÃO pode sair** se o updater aponta para ele. Apagar por "limpeza" mata o botão
  atualizar em todas as versões. Ele carrega o `sha512` que só o electron-builder calcula.

---

## Ordem de trabalho que funcionou

1. Reconhecimento do ambiente (a tabela X11/Wayland acima)
2. Mapear a superfície de contato com o SO
3. Escrever o addon da plataforma nova **sem tocar** no código da antiga (arquivos separados,
   condição no `binding.gyp`) — regressão zero no Windows
4. Provar o addon **isolado**, fora do app, antes de integrar
5. Ajustar caminhos, ícones e empacotamento
6. Provar o app empacotado rodando, com fala de verdade
7. Derivar `deb.depends` do binário; conferir contra o `.deb` gerado
8. Publicar; varrer segredos antes

Os passos 4 e 6 são os que impedem "deve funcionar". Detalhe em `gates.md`.
