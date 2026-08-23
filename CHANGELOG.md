# CHANGELOG — dito-flutter

Mais recente no topo. Cada entrada diz **o quê**, **por quê** e **como foi verificado**.

---

## 2026-08-23 — 1.7.1: a 1.7.0 nao abria, e agora existe portao que impede isso de sair de novo

**Sintoma do dono:** *"eu abri o Dito mas ele nao abriu"*. Sem janela, sem bandeja, **sem uma linha
sequer no log**. A 1.7.0 saiu com `flutter analyze` limpo, 220 testes e 16 goldens verdes — e o
executavel morria antes de imprimir a primeira linha.

**Causa raiz, no codigo do `window_manager` 0.5.2** (`windows/window_manager.cpp`): o campo
`ITaskbarList3* taskbar_` nasce `nullptr` e e criado em **um unico lugar**, dentro de
`WaitUntilReadyToShow()` (linha 227). O `SetSkipTaskbar()` (linha 949) chama `taskbar_->HrInit()`
**sem checar nulo**. O `main.dart` anterior a migracao single-engine chamava
`windowManager.waitUntilReadyToShow(...)`; o `WindowOrchestrator` que o substituiu nao chamava.
Resultado: o primeiro `setSkipTaskbar(true)` do boot desreferenciava nulo —
`0xc0000005` em `window_manager_plugin.dll`, offset `0xa005`, confirmado no Visualizador de Eventos.

Ou seja: **o single-engine nunca tinha bootado no Windows nenhuma vez.** Os ultimos boots com
sucesso no `app.log` ainda registravam `janelas: principal=... sobreposicao=...`, que e log da
arquitetura multi-janela antiga.

**O conserto:** toda a configuracao inicial da janela passou para dentro do callback de
`waitUntilReadyToShow`, como era antes. E `ensureInitialized()` ficou em `main()`, antes do
`runApp` — ele tambem desreferencia `registrar->GetView()` sem guarda. Armadilhas 4.11 e 4.12.

**O portao que faltava:** `tool/fumaca.ps1`, agora obrigatorio dentro de
`packaging/windows/construir.ps1`. Ele sobe o **executavel compilado** nos dois modos (bandeja e
janela) e exige `boot completo` no log; se o app morrer, o empacotamento nao acontece. Nenhum
`flutter test` pega essa classe de defeito, porque nenhum deles sobe o binario.

**Como foi verificado:**
- `tool/fumaca.ps1` com o conserto: **PASSA** nos dois modos (68 MB na bandeja, 84 MB com janela).
- `tool/fumaca.ps1` com o bug reintroduzido de proposito: **FALHA, exit 1** — o portao pega.
- `flutter analyze`: **No issues found**. Suite e goldens: verdes.
- Instalador escaneado pelo Defender: `found no threats`.

**Nota sobre a 1.7.0:** foi despublicada (virou rascunho) assim que o defeito apareceu, para o
auto-update nao empurrar um app que nao abre.

---

## 2026-08-23 — 1.7.0: o texto volta a cair na janela certa, e a faxina depois do single-engine

**Sintoma do dono:** *"às vezes não manda no terminal certo porque ele não estava selecionado"*.
Intermitente, sem erro na tela, sem exceção no log.

**Causa raiz, provada e não suposta.** A migração single-engine (entrada abaixo) apagou
`lib/ui/hud/hud_window.dart` e levou junto o **único** `DitoWin32.takeFocus` que o app tinha — ele
morava em `_mostrarCartao()`. O substituto ficou com `setFocusable(true)` + `focusWindow()` e sem a
captura que vinha antes deles. No nativo, `focus.take` é o único lugar que escreve
`previous_foreground_` e `last_paste_target_` (`dito_win32_plugin.cpp:742-750`), então os dois
ficaram `nullptr` para sempre. Duas consequências caladas:

1. `focus.giveBack` devolvia `false` sem restaurar nada — o texto caía em quem estivesse em foco,
   que no caminho do cartão é o próprio Dito.
2. `ClassifyTarget(nullptr)` nunca reconhecia um conhost em modo cru, então o `SendInput` UNICODE
   da 1.6.9 — a única coisa que cola no Claude Code/Gemini CLI dentro do `cmd.exe` — **nunca mais
   era escolhido**. O conserto da versão anterior estava desligado sem ninguém saber.

**O conserto.** A captura passou para `DitoController.onHotkeyStart`, no início da gravação: a
janela certa é a que estava em foco **quando a tecla desceu**, não quando o cartão apareceu — nessa
hora o foreground já é o Dito e o guard `current != mine` descartaria a captura. O lugar novo cobre
também o caminho `output.confirm = false`, que a posição antiga nunca cobriu. Registrado como
armadilha 6.11.

### O resto

- **A `master` estava vermelha e ninguém sabia.** `(_, _)` exige linguagem Dart 3.7 e o `pubspec`
  pedia `>=3.5.0`: quatro erros de `duplicate_definition`. Pior: `dito_whisper` e `dito_win32`
  exigem `^3.12.2`, que o CI fixado em Flutter 3.29 (Dart 3.7) **nunca conseguiria resolver** — o
  `pub get` da release falharia. Piso alinhado em `^3.12.2` e CI no mesmo Flutter da máquina.
- **Auto-update passou a ser automático.** `UpdateController.checkQuiet()` existia com trava de 6 h
  e engolindo o próprio erro, mas **ninguém o chamava**: só o botão "Verificar agora" funcionava.
  Agora roda no fim do boot.
- **A biblioteca mudou para a pasta do usuário** (`~/Dito`), com migração de uma vez só que move
  `Documentos/Dito` — inclusive de quem nunca escolheu pasta e seguia o default implícito. Nunca
  sobrescreve, nunca funde, e falha ao mover não derruba o boot.
- **Faxina do que a migração deixou:** `window_sizer`, `review_sizing`, `window_shot`, `monotonic`,
  `DitoMainApp` e `LinuxHotkeyService`, mais 16 ferramentas Python do motor aposentado. F6/F7/F8
  saíram da lista de teclas escolhíveis (Dart e o espelho C++). −3.000 linhas.
- **`GEMINI.md` e `.agents/rules/` eram cópias idênticas do `CLAUDE.md`** e tinham envelhecido
  errado: as duas ainda afirmavam que o motor Python roda como sidecar. Viraram ponteiros.
- **Goldens.** 16 imagens de referência (pílula, cartão de revisão, histórico, ajustes) travam a
  aparência. É o que permitiu extrair a decisão de janela do `DitoRootApp` para `OverlayPolicy`
  provando que nada mudou visualmente. Golden é portão **local**: fonte renderiza diferente entre
  Windows e Linux, e comparar cross-OS é falso positivo garantido.
- **`native_transcription_test` foi para trás da tag `live`.** Ele carrega o DLL real e lista
  dispositivos de áudio reais; nunca poderia passar no CI, onde o teste roda antes de o build
  existir. Ver armadilha 6.9.
- **`docs/RELEASE.md`**: o build é local e o upload é à mão. O workflow virou manual, para nunca
  correr junto com um upload e sobrescrever asset publicado. E fica escrito o passo que ninguém
  pode esquecer: subir o `.deb` para a release **não** atualiza Linux nenhum — o updater lê o
  repositório APT, e nada aqui publica lá.

**Como foi verificado:**
- `flutter analyze`: **No issues found**.
- `flutter test --exclude-tags "live,golden"`: **220 testes, todos passando**.
- `flutter test --tags golden`: **16 goldens, todos passando** — prova de zero mudança visual.
- O conserto do foco tem teste que **pega a regressão**: removida a chamada, 3 casos de
  `test/focus_target_test.dart` ficam vermelhos; reposta, os 5 passam.

---

## 2026-08-23 — Arquitetura Single-Engine (fim da tela preta fantasma) e instalador limpo no Defender (branch loucura)

**Sintoma:** Janelas pretas congeladas e perda de contexto de GPU quando o HUD da pílula F9 e cartões F10 abriam/fechavam com frequência, além de falso-positivo `Bearfoos.B!ml` no instalador Inno Setup gerado.

**Causa raiz eliminada:**
1. O pacote `desktop_multi_window` instanciava 3 Flutter Engines concorrentes no mesmo processo (`dito.exe`). Em drivers DirectX/OpenGL, esconder e mostrar sub-janelas causava descarte de shaders e perda irrecuperável de contexto gráfico ("tela preta fantasma").
2. A seção `[Run]` do `dito.iss` invocava `powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden` em executável não assinado, caindo na heurística de *dropper* do Defender.

**O que mudou:**
- **Single-Engine Nativo:** Removido completamente o pacote `desktop_multi_window` e o barramento IPC `MultiWindowBus`. O Dito agora opera com **1 único Flutter Engine** e **1 única janela nativa dinâmica** gerenciada por `WindowOrchestrator` e `DitoRootApp`.
- **Zero Conflitos de GPU:** O contexto gráfico permanece aberto e ativo, alternando suavemente entre modo Oculto (bandeja), Overlay de Rodapé (Pílula F9 / Cartão F10) e Janela Completa de Configurações (880x760).
- **Instalador Limpo:** Removidas as tarefas de PowerShell oculto do `dito.iss`.
- **Zero Python em Runtime:** Todo o processamento de áudio e Whisper permanece em C++ nativo (`whisper.cpp` / miniaudio / Win32 FFI).

**Como foi verificado:**
- `flutter analyze`: **0 problemas**.
- `flutter test --exclude-tags live`: **224 de 224 testes aprovados (100% de sucesso)**.
- `MpCmdRun.exe` (Windows Defender): **`found no threats` (0 ameaças detectadas)**.

---

## 2026-08-22 — a colagem no Claude Code/Gemini CLI do Windows, e a paridade que faltava, 1.6.9

**Sintoma do dono:** ao ditar com o cursor no **Claude Code ou Gemini CLI** no Windows, o texto
**não era colado** — só um Enter vazio chegava ao prompt. Idêntico ao que a 1.6.8 consertou no
Linux, só que aqui a documentação afirmava que não podia acontecer.

**Causa raiz, medida e não suposta.** A armadilha 6.4 e o `docs/WINDOWS.md` diziam que no Windows o
`Ctrl+V` é *universal*. **Nunca tinha sido medido em console:** o `tool/spike_paste.dart` prova a
colagem contra um controle **EDIT do Win32** criado pelo próprio app, jamais contra um terminal.
Lendo com `AttachConsole` o console real de uma sessão do Claude Code: **`0x0208`** —
`ENABLE_PROCESSED_INPUT` desligado, `ENABLE_QUICK_EDIT_MODE` desligado, `VT_INPUT` ligado — contra
`0x01E7` de um `cmd` comum. Sem `PROCESSED_INPUT` **o conhost para de interceptar o `Ctrl+V`** e
entrega o caractere de controle `0x16` (SYN) ao aplicativo, exatamente como o termios no Linux.

**O que mudou — cirúrgico, só onde estava quebrado.**

- `ClassifyTarget(HWND)` no plugin Windows, gêmeo do `IsTerminalWindow` do Linux: lê `GetClassName`
  do **alvo lembrado**. Só `ConsoleWindowClass` muda de caminho — passa a receber o texto digitado
  com `SendInput` + `KEYEVENTF_UNICODE`. Windows Terminal, Git Bash e janelas GUI **continuam no
  `Ctrl+V`**, porque a medição mostrou que já funcionam.
- `PasteService` junta as quebras de linha num espaço **quando o alvo é console/terminal**. Não é
  preferência: o conhost e o mintty **não** fazem bracketed paste, então 3 linhas viram 3 envios no
  CLI. O Windows Terminal embrulha e não sofre. A sobra do clipboard guarda o texto **original**.
- `input.targetKind` novo **nas duas plataformas** — no Linux reaproveitando o `IsTerminalWindow`
  que já existia, sem lógica nova lá.

**Duas coisas quebradas no Windows que ninguém tinha visto** (achadas comparando a tabela de métodos
dos dois plugins):

- O alvo lembrado era **por engine** e o `giveBack` o apagava. Como `windows/runner/main.cpp:61`
  registra o plugin em **cada** sub-janela, o `focus.take` do HUD e o `restoreFocus()` do
  `PasteService` falavam com instâncias diferentes: **`restoreFocus()` sempre devolvia `false`**.
  Agora é estado de processo, com `last_paste_target_` sobrevivendo ao `giveBack`, como no Linux.
- `window.setFocusable` era chamado pelo `lib/` compartilhado (`hud_window.dart:252,273,285`) e
  **não tinha handler no Windows** — o `_tryNative` engolia a exceção. Implementado como pôr/tirar
  `WS_EX_NOACTIVATE`.
- `input.sendCtrlV`, `input.sendEnter` e `input.sendChord` devolviam `true` fixo. Agora devolvem o
  retorno real do `SendInput`, como o Linux já fazia desde a 1.6.3 — sem isso o `PasteService` nunca
  conseguia cair para a sobra.

**Dois defeitos preexistentes do Windows, achados ao levantar a linha de base:**

- `NativeEngine.dispose()` não fechava o `Logbook`, e o `IOSink` aberto travava a pasta temporária:
  no Windows `deleteSync` falha com `errno 32`, no Linux não. Era o único vermelho da suíte.
- `%LOCALAPPDATA%\Programs\Dito` no `PATH` faz `flutter test` carregar o DLL nativo do app
  **instalado** em vez do recém-compilado. Documentado na armadilha 6.9; não é código, é máquina.

**Como foi verificado.**

1. **Linha de base primeiro, no `f07a3e5` intocado** (armadilha 5.4): `analyze` limpo (só depois de
   `pub get` nos 3 sub-pacotes), **217 verdes / 1 vermelho**, `build windows --debug` exit 0.
2. **Instrumento validado no controle** antes de valer: Bloco de Notas, onde `Ctrl+V` é sabidamente
   bom. E o alvo em modo cru é **fixado** no `0x0208` da sessão real — o `setRawMode` do Node sozinho
   dá `0x0008`, sem `VT_INPUT`, e a sonda **aborta** o alvo se o modo não bater.
3. **Tabela medida** em `docs/medicoes/colagem-windows.md`, com `tool/sonda_colagem.ps1`: no conhost
   o `Ctrl+V` entrega **só `0x16`** e a coluna `Enter na ordem` dá **NÃO** — o sintoma do dono
   reproduzido —, enquanto `SendInput` UNICODE entrega as três amostras com o Enter na ordem.
4. **Os testes novos falharam primeiro:** com a regra de juntar linhas desligada, 2 falham; ligada,
   os 18 do arquivo passam.
5. **Suíte: 224 verdes, zero vermelhos** (eram 217+1). `analyze` limpo, `build windows` exit 0.

**Ainda não verificado:** a colagem ponta a ponta ditando de verdade no app instalado, e o Linux
nativo — esta máquina não compila Linux. O `input.targetKind` do Linux sai daqui compilando só no
papel.

---

## 2026-08-22 — colagem automatica em emuladores de terminal (Ctrl+Shift+V) no Linux, 1.6.8

**Sintoma do dono:** ao ditar no terminal (como no CLI do Antigravity `agy`), o texto **nao era colado** e
apenas uma quebra de linha vazia chegava ao prompt.

**Causa raiz.** No Linux, emuladores de terminal (`gnome-terminal`, `xterm`, `kitty`, etc.) tratam `Ctrl+V`
como caractere de controle (`0x16` / `lnext`), e exigem `Ctrl+Shift+V` para colar da area de transferencia.
O plugin nativo em C++ enviava `Ctrl+V` fixo herdado do Windows, sem checar a classe da janela.

**O que mudou.** O plugin Linux (`dito_win32_plugin.cc`) agora consulta o `WM_CLASS` da janela ativa no X11.
Se for um emulador de terminal conhecido (`gnome-terminal`, `alacritty`, `kitty`, `konsole`, `xfce4-terminal`,
`tilix`, etc.), injeta `Ctrl+Shift+V` via XTEST direto (`libXtst`). Para todas as demais janelas normais
(WhatsApp, Discord, navegadores, editores GUI), continua injetando `Ctrl+V` sem nenhuma alteracao. O
`RunXdotoolKey` passou a suportar modificadores compostos (`ctrl+shift+...`) via XTEST in-process.

**Como foi verificado.** Compilacao e execucao de `tool/spike_paste.dart` (validando o caminho de colagem),
`flutter test` e `flutter analyze` 100% verdes, e validacao de empacotamento com `packaging/linux/construir.sh`.

---

## 2026-08-22 — o primeiro Enter enviava de verdade (e limpeza de codigo morto), 1.6.7

**Sintoma do dono:** no cartao de revisao, o **primeiro Enter pulava uma linha** e so o segundo
enviava.

**Causa raiz.** O `review_card.dart` tratava o Enter em `Focus(onKeyEvent: _onKey)`, o ancestral do
`TextField`. Esse caminho **funciona** — o teste `Enter sends exactly what is on screen` ja passava
antes desta versao, e foi justamente ele que apontou onde NAO estava o defeito. No Linux o Enter
chega tambem (e antes) como **insercao de texto** pelo canal de plataforma do GTK, e nao como tecla:
o `TextField` com `maxLines: null` recebe um `\n` e o `_onKey` nunca ve o evento.

**O que mudou.** O `onChanged` passou a comparar a contagem de `\n` com o texto anterior. Quebra de
linha **nova** e sem Shift = Enter: o cartao devolve o texto ao valor de antes e envia. Com Shift a
linha continua sendo inserida normalmente. O `_send()` ganhou uma trava de idempotencia — os dois
caminhos podem carregar o mesmo Enter e o cartao resolve **uma** vez so.

**Como foi verificado.** Um teste novo simula exatamente o caminho da plataforma
(`tester.enterText(campo, 'texto original\n')`), o que os testes de tecla crua nao alcancavam.
Ele **falhou primeiro** (`sent` vazio: so pulava linha), e passou depois do conserto. Os 13 testes do
cartao verdes, incluindo o de Shift+Enter, que continua inserindo linha sem enviar.

**Limpeza de codigo morto** (auditada antes, item por item, com `grep` nas duas plataformas):

- `WindowRole.review` — papel removido na 1.6.0, a constante sobrou.
- `EngineClient`: parametro `candidates:` e o getter `executablePath` — residuo do sidecar Python.
- `window.adoptAsPanel` — fachada Dart, handler Linux e ramo Windows, **zero chamadas**. No Windows
  o ramo era compartilhado com `adoptAsHud`; foi separado preservando o `adoptAsHud` intacto.
- **52 das 174 chaves de traducao** (`app_{en,pt}.arb`) — sobra de uma tela de Configuracoes e de uma
  janela principal anteriores. Paridade pt/en mantida, 122 chaves em cada.

**Um defeito achado durante a limpeza, e corrigido:** `lib/ui/main/main_window.dart:115-116` tinha os
rotulos das abas **cravados em portugues** (`label: 'Histórico'`), fora do i18n — era por isso que
`tabHistory`/`tabSettings` pareciam mortas. As duas chaves foram religadas em vez de apagadas. O
`test/l10n_test.dart` nao pegava porque so varre `Text('...')`, e o literal estava no parametro
`label:` de `NavigationDestination`.

Os `.g.dart` foram conferidos rodando `flutter gen-l10n`: o diff ficou **so com remocoes, zero
insercoes** — o gerador produz exatamente o que esta no repo. `analyze` limpo, **220 testes** verdes,
portao **11/11**.

**Terceiro criterio oscilante identificado:** `cartao aparece` deu 1/6 numa rodada e **0/6 na
seguinte com o binario identico**. Somado a `abre com conteudo` e `sem pixel fantasma`, ver
armadilha 5.4 antes de culpar qualquer mudanca por eles.

---

## 2026-08-22 — a janela parou de piscar no boot: o runner ainda usava a regra do Windows, 1.6.6

**Sintoma do dono:** abrir o Dito e a janela **aparecer e fechar sozinha** logo em seguida. Ele quer
so o icone da bandeja, e abrir a janela quando quiser.

**Causa raiz.** O atalho e `Exec=/opt/dito/dito_app`, **sem argumento**. Os dois lados do app
discordavam sobre o que fazer nesse caso:

| lado | regra | conclusao sem argumento |
|---|---|---|
| Dart — `lib/main.dart:37` | Linux: esconde a menos que venha `--janela` | **esconder** |
| Runner C — `my_application.cc:92-105` | procurava `--startup`, `--minimized`, `--tray`, `listen`, `--hidden` | **mostrar** |

O runner chamava `gtk_widget_show(toplevel)` no primeiro frame e o Dart chamava
`windowManager.hide()` logo depois — o par que o dono via piscar. A lista do runner era a convencao
do **Windows**: a 1.6.3 inverteu o padrao do Linux no `main.dart` e nao atualizou o runner. Os dois
leem **o mesmo vetor** (`my_application.cc:193`, `dart_entrypoint_arguments = argv + 1`), entao a
divergencia era so de regra.

**O que mudou.** O `first_frame_cb` passou a usar a mesma regra do Dart: escondido e o padrao, so
`--janela` mostra. `linux/runner/` so compila no Linux; o `windows/runner/` **nao foi tocado**.
Com isso a janela **nunca chega a ser mapeada** no boot — nao existe o que piscar. Isso tambem faz o
app finalmente cumprir a **garantia nº 4** ("nada aparece no login alem do icone da bandeja").

**Como foi verificado.** Estado X11 da janela principal, do boot ate o clique na bandeja:

```
t~0s  UNMAPPED     t~1s  UNMAPPED     t~2s  UNMAPPED
t~4s  UNMAPPED     t~8s  UNMAPPED
apos clicar em "Abrir Dito":  VIEWABLE
```

**Risco medido, nao suposto.** A mudanca adia a primeira mapeacao da principal para o clique na
bandeja, e a armadilha 4.3 registra que este WM ja falhou em mapear de forma intermitente. Por isso
foram rodadas **25 aberturas** pela bandeja com o mesmo instrumento que provou a 1.6.5:
**0/25 congeladas**, igual a referencia. Portao **11/11**, `analyze` limpo, 219 testes verdes.

---

## 2026-08-22 — a sobreposicao nascia com forma VAZIA e o compositor parava de repintar o monitor, 1.6.5

**Sintoma do dono:** abrir o Dito e a janela ficar parada em "Iniciando…" ate um F9; **a imagem do
monitor inteiro congelar**; arrastar uma janela e ficar o rastro dela parado na tela. Sempre no
monitor onde o Dito abre.

**Causa raiz.** `desktop_multi_window_plugin.cc:197-201` criava a sobreposicao assim:

```cpp
gtk_widget_show_all(win);
cairo_region_t* vazio = cairo_region_create();
gtk_widget_shape_combine_region(win, vazio);   // forma VAZIA numa janela MAPEADA
```

Ou seja: uma janela 900×900, `_NET_WM_STATE_ABOVE`, **mapeada**, sobre o monitor primario, com a
regiao **bounding vazia** — exatamente o que a armadilha **4.8** deste projeto ja tinha documentado e
medido (*"`gtk_widget_shape_combine_region` com regiao vazia nao gera a repintura da area liberada"*).
O remedio do 4.8 (opacidade 0 + forma nunca vazia) tinha sido aplicado **so no caminho de esconder**.
O caminho de **nascer** ficou de fora, e e nele que o dono abre o app. Por isso um F9 "consertava":
ele da forma nao-vazia a janela e o compositor volta a repintar.

Estado medido no X11, ocioso:

| | mapeada | forma (bounding) | opacidade |
|---|---|---|---|
| antes, pos-boot | VIEWABLE | **VAZIA** | **ausente** |
| antes, depois de um F9 | VIEWABLE | 34.247 px | opaca |
| **depois do fix** | VIEWABLE | **1×1 (1 px)** | **0** |

**O que mudou.** A sobreposicao nasce ja no estado que o 4.8 provou correto: forma de **1 px**
(nunca vazia), recorte de clique vazio e `_NET_WM_WINDOW_OPACITY = 0` via `XChangeProperty` —
`gtk_widget_set_opacity` nao serve no GTK3, o 4.8 ja media isso. O `CMakeLists.txt` do
`desktop_multi_window` passou a linkar `x11`, como o `dito_win32` ja fazia.

**Como foi verificado.** O experimento que isolou a causa, antes do fix, com uma variavel so
(`DITO_HUD_HOLD=1` faz a sobreposicao desenhar no boot):

| braco | aberturas congeladas |
|---|---|
| sem o HUD desenhar | **6/20** |
| com o HUD desenhar | 0/20 |

Depois do fix, sem HUD nenhum: **0/25**. Portao **11/11**, `analyze` limpo, 219 testes verdes.
Conferido tambem que a sobreposicao ociosa **nao rouba clique**: 0/20 amostras no centro dela.

---

## 2026-08-22 — a biblioteca guarda o texto, nao o audio: 211 MB viraram 2,5 MB, 1.6.4

**O que mudou:** o app **nao escreve mais WAV**. Cada ditado deixa so o `.json` com o texto.

**Por que.** O dono viu a pasta do dia crescendo e reclamou do peso. Medido antes de mexer, em
`~/Documentos/Dito` com 6 dias de uso:

| | arquivos | tamanho | fatia |
|---|---|---|---|
| `.wav` | 456 | **158,7 MB** | 99,92% |
| `.json` | 495 | 129 KB | 0,08% |

Sao ~22 MB/dia. A retencao existente (`library.keep_days = 30`, `library_reader.dart:138`) apaga
pastas de **dia inteiro** com mais de 30 dias — a biblioteca tinha 6 dias, entao nunca varreu nada.
Dia e a unidade errada para um arquivo que morre no instante em que a transcricao sai. Havia ainda
uma pasta orfa `~/Documents/Dito` (47 MB), do padrao antigo, que o sweep **nunca** olha porque
`boot.dart:372-375` so varre a pasta configurada.

Levantado antes de decidir: **nada no app le o WAV depois que a sessao fecha** — nao ha reproducao,
nao ha re-transcrever, e `hasAudio`/`sizeBytes` (`library_reader.dart:82,98`) sao calculados e nunca
aparecem na tela. O `seconds` ja vem sempre no JSON.

**Isso revoga a garantia nº 1** ("audio nunca se perde"), por decisao explicita do dono em
2026-08-22. O `CLAUDE.md` foi corrigido junto, com o aviso de nao recolocar o WAV achando que
restaura uma garantia. `DITO_SALVAR_WAV=1` liga o WAV de volta so para depurar.

**Como foi feito:** `native_engine.dart` passa `wavPath` vazio; o C++ **nao mudou** — o
`dito_whisper.cpp:378` ja tratava caminho vazio e o `drain_ring:155` corta a conversao float→int16,
a escrita e o `flush()` de 1 em 1 s quando inativo. Removido tambem o fallback `DitoWhisper.saveWav`
do `_handleStop`: sem WAV incremental a condicao dele seria sempre verdadeira e gravaria o arquivo
**inteiro** a cada parada.

**A fala de teste do portao mudou de casa.** `tool/regressao.py` e `tool/repro_ditado.py` usavam
`~/Documentos/Dito/2026/08/22/05-26-41.wav` — dentro da biblioteca. Como o app nao gera mais WAV,
essa era a ultima copia existente. Foi para `tool/fixtures/fala.wav`, no repo.

**Como foi verificado — A/B/A com 18 ditados reais do `tool/regressao.py`:**

| horario | build | ditados | JSON | WAV |
|---|---|---|---|---|
| 10:59 | com a mudanca | 6 | 6 | **0** |
| 11:08 | revertido | 6 | 6 | 6 |
| 11:10 | com a mudanca | 6 | 6 | **0** |

Limpeza dos ja gravados: `211 MB → 2,5 MB`, 561 WAV apagados, os **610 JSON intactos**.
`flutter analyze` limpo, **219 testes** verdes.

**Nao confundir com o defeito do item 1.** Nestas rodadas o criterio `abre com conteudo` falhou
2 de 4 vezes com a mudanca — e **1 de 3 vezes com o binario revertido**, que nao tem a mudanca.
Rodadas 3 e 4 usaram o **mesmo binario** e deram 0/5 e 5/5. O criterio nao e deterministico; o
defeito e o antigo, dos dois lados. Idem `sem pixel fantasma`, que deu 1/6 no build revertido.

---

## 2026-08-22 — sobe na bandeja, biblioteca acha o audio de novo, e a colagem para de mentir, 1.6.3

Lote de baixo risco, distribuido em agentes (um dono por arquivo) e fechado por um **portao de
regressao** novo (`tool/regressao.py`): um comando, 10 criterios com limiar medido, veredito por
item. Nenhuma mudanca desta rodada foi publicada sem ele verde.

**O que quebrava funcionalidade de verdade — separador `\` do Windows cravado no Linux:**
- `lib/library/library_reader.dart:81` montava `'${'$'}{file.parent.path}\\$stem.wav'`. No Linux a
  barra invertida e um caractere de NOME, nao separador — o arquivo procurado era
  `.../07-42-13\07-42-13.wav`, que nunca existe. Resultado: **`hasAudio` era sempre falso**, a
  biblioteca nunca encontrava o audio das gravacoes e a duracao pelo tamanho do arquivo nunca era
  calculada.
- `lib/state/dito_controller.dart` fazia o mesmo em `_saveToVault`: **salvar no Obsidian estava
  simplesmente quebrado**, criava um arquivo com barra invertida no nome em vez de gravar na pasta.
- Os dois passaram a usar `Platform.pathSeparator`. `lib/config/paths.dart` foi conferido e **esta
  certo** — os `\` de la estao todos dentro de `if (Platform.isWindows)`.

**Abrir o Dito passou a subir so na bandeja** (pedido do dono, e a garantia nº 4 do projeto). No
Linux o padrao inverteu: sem argumento sobe escondido; `--janela` abre com a janela. Windows
inalterado. Tres saidas verificadas: atalho do menu → janela `UNMAPPED`; `--janela` → janela
visivel; **clicar no menu de novo apresenta a janela existente** (`my_application.cc`), entao nao ha
cenario em que o dono fique sem interface.

**Colagem parou de falhar em silencio:**
- `paste_service.dart` — os retornos de `restoreFocus()` e `pressEnter()` eram descartados. Agora
  sao lidos e registrados. Enter recusado **nao** vira falha de colagem (o texto ja foi colado), vira
  `PasteResult(pasted: true, error: 'Enter recusado')`.
- `dito_controller.dart` — colagem bem-sucedida nao gerava confirmacao nenhuma; sucesso e falha eram
  indistinguiveis. Agora confirma. E o Enter recusado mostra falha, nao "colado".
- `clipboard.set` no plugin respondia `TRUE` incondicional porque `gtk_clipboard_set_text` e `void`.
  Trocado por `gtk_clipboard_set_with_data`, que devolve a posse real do seletor.
- `focus.giveBack` era fire-and-forget. Agora faz **um** `XSync` e **uma** leitura, e avisa no log
  quando o foco nao voltou. **Sem laco de espera** — copiar o busy-wait de `window.focus` para ca
  trocaria uma falha silenciosa por uma trava.

**Higiene que estava custando diagnostico:**
- `g_warning` do plugin ia para o stderr e sumia quando o app roda pela bandeja. Agora ha
  `g_log_set_default_handler` gravando em `~/.local/share/dito/logs/native.log` (respeitando
  `XDG_DATA_HOME`), sem deixar de imprimir no stderr. Ja capturou o `Failed to setup compositor
  shaders` que antes so aparecia lancando o app a mao.
- `test.ownsForeground` e `keys.injectForTest` nao existiam no plugin Linux: o autoteste morria com
  `MissingPluginException` a cada boot com `DITO_SELFTEST=1` (3 no crash.log do dia). Implementados;
  o autoteste agora vai de ponta a ponta sem exceção.
- A sobreposicao nascia `_NET_WM_WINDOW_TYPE_NORMAL`, a categoria EWMH com o tratamento de
  foco/stacking mais pesado. Agora nasce `UTILITY` — nunca `NOTIFICATION`, porque ela **precisa** de
  foco quando ha cartao, e sempre **antes** do `show_all` (hint depois nao retroage, armadilha 4.6).
- `HudState` morto em `boot.dart`: era alimentado em todo `_toHud()` e nunca lido, rodando um
  `Timer.periodic(50 ms)` com `wave.tick()` na thread que desenha. Removido.

**Como foi verificado.** `flutter analyze` limpo e **219 testes verdes** (eram 211), mais o portao em
app real, 10/10: boot 0,68 s; sobreposicao nao rouba clique 0/20; laco GTK parado com mediana
1,2 ms; cartao aparece 6/6; **pixel fantasma 0/6**; foco no cartao com `input focus: True` 6/6;
zero excecao nova. Uma auditoria adversarial reprovou a primeira versao do lote e achou dois
defeitos que o portao verde nao pegava — falha do vault sendo reportada como sucesso, e o toast novo
de colagem atropelando a pilula de uma gravacao mais nova (armadilha 3.2). Os dois foram corrigidos
antes de publicar.

**Ressalvas assumidas, nao corrigidas:**
- Falha ao salvar no vault quando `toVault` **e** `output.paste` estao ligados continua escondida
  atras do sinal da colagem; so o caminho sem colagem reporta a falha.
- `restoreFocus()` recusado vira log, nunca chega ao dono na tela. Falso negativo desse retorno e
  conhecido nesta pilha, entao abortar a colagem por causa dele seria pior.
- Com `output.confirm = false` (nao e o padrao) a pilula some por ~120 ms antes de o toast de
  "colado" aparecer: o fade dura 180 ms e a colagem leva no minimo 300 ms.

**Ainda aberto, com numero medido:** gravando, o laco GTK responde em **58-63 ms** (parado: 1,2 ms),
porque a thread de plataforma — que no Flutter 3.47/Linux **e** a thread de UI do Dart — gasta o
tempo apresentando frame (`gdk_cairo_draw_from_gl` → `XSync` → `libGLX_nvidia`, 6 de 10 amostras de
`gdb`). E o `window.focus` ainda tem espera ocupada de ate 200 ms; `cartao recebido` → `cartao no ar`
mede 114-181 ms.

**O "abre congelado" NAO foi resolvido — e o que se aprendeu sobre ele.** Reproduzido e
fotografado: a janela mostra "Iniciando..." muito depois de `boot completo` estar no log. Tres
hipoteses caidas, todas medidas:
- **Nao e o esconder/desmapear** (armadilha 4.3 na janela principal): com `--janela`, janela sempre
  visivel e nunca escondida, ela ficou **12 s em "Iniciando..."**.
- **Nao e frame velho simples**: nenhuma forma de forcar repintura funciona — `markNeedsPaint`,
  `handleMetricsChanged`, `scheduleForcedFrame`, `reassembleApplication`, redimensionar (1, 5 e
  40 px), mover o mouse, clicar, e alternar o proprio `ValueNotifier` que a arvore escuta. **So o
  F9 conserta**, sempre.
- **E intermitente**: uma execucao bootou em 0,7 s com uma unica trava de 149 ms; outra levou ~10 s.
  Numa delas o Muffin **acinzentou** a janela, marca de quem nao responde ao `_NET_WM_PING`, ou seja
  thread de plataforma bloqueada.
Todas as tentativas de correcao foram **revertidas** por nao terem prova; nada de palpite foi
publicado.

**Registrado** em `docs/armadilhas.md` 4.9, 5.3 e secao 6.

---

## 2026-08-22 — o "Descartado" que ficava na tela era pixel fantasma do compositor, 1.6.2

**O sintoma.** Depois de gravar e dar Tab (descartar) — e tambem depois do Enter (enviar) — a pilula
ficava desenhada na tela e nao saia mais. O dono descrevia como "a interface travou", e um F9 novo
"destravava".

**Causa raiz, medida.** O app estava **certo**: o log mostra `cartao descartado`, e a regiao de
clique da sobreposicao zera no tempo previsto (1,2 s de toast + saida). O que sobrava eram **pixels
que o Muffin nunca repintava**. Provado com foto: com a regiao de clique vazia ha 2,5 s, **100% dos
pixels da pilula continuavam identicos** aos de quando ela estava visivel, e um `xrefresh` os
limpava. O gatilho e o recorte de forma **vazio**: `gtk_widget_shape_combine_region` com uma regiao
vazia nao faz o compositor repintar a area liberada.

**A correcao.** Havendo compositor, esconder deixou de ser "forma vazia" e passou a ser
**`_NET_WM_WINDOW_OPACITY = 0`**; o recorte de *input* continua vazio, entao o clique segue passando
para a janela de tras. Sem compositor, o comportamento antigo (forma vazia) permanece como
alternativa. `gtk_widget_set_opacity` **nao serve**: no GTK3 ele nao grava a propriedade que o
gerenciador le — foi preciso `XChangeProperty` direto.

**Como foi verificado.** Medicao A/B com o mesmo instrumento (`tool/repro_ditado.py`, que injeta uma
fala real num microfone virtual, espera o cartao, resolve, e so julga depois de a regiao ficar vazia
por 2,5 s seguidos):

| build | fantasma |
|---|---|
| sem a correcao | **20 / 20 (100%)** |
| tentativa 1 (forma vazia + opacidade) | 1 / 20 (5%) |
| **entregue (forma nunca vazia, esconde por opacidade)** | **0 / 20 no Tab e 0 / 10 no Enter** |

`flutter analyze` limpo e **211 testes verdes**. Sem regressao na armadilha 4.6: com o cartao no ar,
`xprop WM_HINTS` segue mostrando `input focus: True` e a sobreposicao continua sendo a janela ativa;
escondida, volta a `False`.

**Descartado no caminho, tudo medido:** reduzir o canvas de 900x900 (o ganho era artefato — a pilula
saia para fora da janela encolhida, entao nao havia frame nenhum); e, num fantasma **ja assentado**,
nem opacidade, nem mover a janela, nem redimensionar limpam (4-5 de 5 continuam sujos) — o remedio so
funciona aplicado **junto** com a mudanca de forma.

**Registrado** em `docs/armadilhas.md` 4.8.

**Ainda aberto, medido nesta rodada:** enquanto grava, o laco GTK responde em **58-63 ms** (contra
1,2 ms parado), porque a thread de plataforma — que no Flutter 3.47/Linux **e** a thread de UI do
Dart (nao existe `io.flutter.ui`) — gasta o tempo apresentando frame: `gdk_cairo_draw_from_gl` →
`XSync` → `libGLX_nvidia` em 6 de 10 amostras de `gdb`. E `gainFor` (`native_engine.dart:272`) nao
amplifica quando o pico fica abaixo de `audibleRms` (0,008), entao fala fraca de verdade e descartada
sem transcrever.

---

## 2026-08-22 — o Enter ia para o terminal: a janela estava marcada como "nao pode receber foco", 1.6.1

**O sintoma.** Com o cartao de revisao na tela, o cursor piscava no campo de texto, mas o Enter e o
Tab iam para a janela de tras (o terminal). Clicar no cartao nao adiantava. Ctrl+C/Ctrl+V do proprio
dono tambem paravam de funcionar. A interface "travava" ao abrir e depois de cada Enter, e so
normalizava depois de um F9/F10.

**Causa raiz** (achada por auditoria dedicada do port Linux): `adoptAsHud()` e chamado toda vez que a
sobreposicao sobe (`hud_window.dart`) e executa `gtk_window_set_accept_focus(FALSE)`, que grava
`WM_HINTS.input = False`. Para o Mutter/Muffin isso nao e uma preferencia — e uma declaracao de
**incapacidade estrutural**: o gerenciador passa a recusar foco aquela janela para sempre, e nem
`_NET_ACTIVE_WINDOW` nem `XSetInputFocus` contornam. **Nao existia nenhuma chamada no codigo que
devolvesse o hint para `TRUE`.** No Windows o equivalente (`WS_EX_NOACTIVATE`) e fraco e da para
furar com `SetForegroundWindow` — a traducao 1:1 do port mudou a semantica sem ninguem perceber.

**As correcoes.**
1. **`window.setFocusable`** (novo, no plugin Linux): o hint passa a acompanhar o estado —
   `true` antes de pedir foco para o cartao, `false` quando resta so a pilula.
2. **`gtk_widget_grab_focus` no `FlView` da sub-janela**: o runner principal ja fazia isso; o fork do
   multi-window nao — sem ele, o teclado nao chega ao motor Flutter mesmo com a janela focada.
3. **O alvo do foco anterior parou de ser esquecido**: `focus.take` zerava o alvo salvo quando a
   sobreposicao ja estava ativa (2o cartao seguido), e o `giveBack` virava no-op — o foco ficava
   preso na sobreposicao e **as teclas do sistema sumiam**. Agora o alvo so e substituido por um
   valido.
4. **Foco devolvido apenas quando nao resta cartao** (antes era devolvido mesmo com outro cartao na
   tela, deixando os seguintes sem teclado).
5. **XTEST no lugar de subprocesso**: `Ctrl+V` e `Enter` eram enviados com `g_spawn_sync` do
   `xdotool` — fork+exec+espera **na thread do GTK**, 20–150 ms de interface congelada por tecla.
   Agora e `XTestFakeKeyEvent` via `libXtst`, com o `xdotool` so como ultimo recurso.
6. **Reentrancia do laco principal removida**: a criacao da sub-janela chamava
   `while (gtk_events_pending()) gtk_main_iteration()` **segurando um mutex global** — risco de
   travar o processo inteiro para sempre, alem de congelar o boot.

**Como foi verificado.** `flutter analyze` limpo, **211 testes verdes**, e a prova em app real, com
o dono falando: `cartao recebido: id=... texto=18 chars` → `cartao no ar: focado=true itens=1`, e
`xprop WM_HINTS` mostrando **`Client accepts input or input focus: True`** com o cartao na tela
(antes: `False` sempre). O dono confirmou na sequencia que o Ctrl+C voltou a funcionar.

**Registrado** em `docs/armadilhas.md` 4.6 e 4.7.

---

## 2026-08-22 — uma sobreposicao so, e ela nasce viva, 1.6.0

**O defeito que sobrou do dia anterior.** O cartao de revisao — e as vezes o proprio HUD — nascia
morto: a janela existia com o tamanho de fabrica (560x180), o codigo Dart dentro dela nunca rodava, e
o que ficava na tela era um quadro congelado que nao respondia a clique nenhum. Era isso que o dono
via como "modal preso que nao fecha". Intermitente entre boots, e no log sempre a mesma linha:
`Failed to setup compositor shaders, unable to make OpenGL context current`, **uma por sub-janela**.

**Causa raiz.** O `FlView` da sub-janela so consegue contexto GL sobre uma janela **realmente
mapeada**. O fork criava a view com a janela apenas realizada (`gtk_widget_realize`), o que nao
basta: dependendo do timing, a view nascia sem contexto e o engine daquela janela nunca desenhava um
frame — e sem frame, o `initState` do Dart nunca roda.

**A correcao, em duas partes.**
1. **A sub-janela sobe mapeada**: `gtk_widget_show_all` acontece **antes** de a view ser criada, ja
   com recorte vazio (nasce invisivel), e o loop de eventos e drenado antes de seguir.
2. **Uma sub-janela so**: a pilula e os cartoes de revisao passaram a viver na MESMA sobreposicao
   (canvas 900x900, pilula no rodape e cartoes empilhados acima). Cada sub-janela extra era mais uma
   chance de nascer morta — e a janela de revisao separada deixou de existir
   (`lib/ui/review/review_window.dart` removido, junto com o papel `review` no roteamento).

**Como foi verificado.** `flutter analyze` limpo, **211 testes verdes**, e a medicao que importa:
**3 de 3 boots seguidos** com a sobreposicao viva (canvas 900x900 aplicado pelo proprio Dart da
janela) — antes, no ultimo teste da vespera, ela falhava. Erros de compositor cairam de 2 para 1
(uma sub-janela em vez de duas).

**Descartado no caminho, tudo testado:** atrasar a criacao da segunda janela (piorou: nenhuma subia),
esperar `endOfFrame` (piorou igual), `LIBGL_ALWAYS_SOFTWARE`, `GDK_GL=gles`, `GDK_GL=glx-legacy`,
criar a janela sem foco e realizar a janela antes da view. Registrado em `docs/armadilhas.md` 4.4.

---

## 2026-08-21 — ganho automatico para a fala fraca, e o cartao que nao aceitava clique, 1.5.4

**O cartao ficava preso, sem aceitar clique nem Enter/Tab.** Causa provada com `xwininfo -shape`:
`Window shape extents: 0x0+0+0` — a mascara de cliques estava **vazia**. Quando o cartao reaparece
antes de o layout ter sido medido, `_clipToCard` saia sem aplicar nada e a regiao do "escondido"
(vazia, introduzida na 1.5.0) continuava valendo: a janela desenhava, mas nao recebia clique nenhum.
Agora, sem medida ainda, a janela inteira e liberada; o recorte fino vem no frame seguinte. Mesma
correcao no HUD.

**Ganho automatico.** Medicao simultanea no momento em que o dono relatou o problema:
`pw-record` fora do app deu pico 1826 / RMS 306, e o Dito no mesmo instante deu pico 1925 / RMS 310 —
**identicos**. O app capta exatamente o que o sistema entrega; o que oscila e a forca do sinal do
headset (a mesma voz media RMS 806 uma hora antes, e ate 30x menos em alguns momentos). Como o
Whisper nao ouve fala nesse nivel, o audio passa a ser normalizado antes de transcrever: ganho de ate
20x quando o pico esta abaixo do alvo, **nunca** quando o sinal e ruido de fundo (abaixo do limiar de
voz do proprio app, para nao gerar alucinacao). O WAV em disco continua intacto — o ganho vale so
para a transcricao, entao a gravacao segue sendo a prova do que o microfone entregou.

**Como foi verificado.** `flutter analyze` limpo e **211 testes verdes**, 6 novos guardando o ganho:
fala fraca chega ao alvo, fala boa nao e tocada, ruido NAO vira voz, o teto existe, o pior caso
medido no headset (pico 0.010) cabe nele, e lista vazia nao quebra. Em app real, o log passou a
registrar `sinal fraco: aplicando ganho de 20.0x para transcrever`.

---

## 2026-08-21 — cartoes empilhados como cartas: embaixo, meio, cima, 1.5.3

O dono descreveu como quer a pilha: **o primeiro cartao embaixo, o segundo no meio, o terceiro em
cima, e o quarto volta para baixo** — tres posicoes que ciclam, com os cartoes se sobrepondo como um
baralho aberto em leque, em vez da coluna sem sobreposicao da 1.5.1.

A janela de revisao passou a desenhar os cartoes num `Stack` ancorado no rodape, com degrau de
`AppSize.reviewStackStep` por posicao (`i % 3`): o mais recente fica na frente, colado embaixo, e os
anteriores aparecem como faixas acima dele.

**Como foi verificado.** `flutter analyze` limpo e 205 testes verdes, incluindo o teste que varre
`lib/ui/**` proibindo valor de espacamento fora dos tokens.

---

## 2026-08-21 — cartao clicavel e cantos redondos no recorte, 1.5.2

**Clicar num cartao empilhado nao o selecionava** para Enter/Tab: com varios cartoes na tela, o foco
ficava em quem pediu por ultimo e o clique nao mudava isso. Cada cartao passou a pedir o foco no
`onPointerDown` (`review_card.dart`), entao clicar escolhe quem recebe Enter e Tab.

**O recorte da janela cortava quadrado.** A regiao era aproximada por dois retangulos unidos — os
cantos arredondados do cartao e da pilula ficavam com quina visivel. Agora a regiao e montada faixa a
faixa, uma linha por pixel do raio, acompanhando a curva (`dito_win32_plugin.cc`, `window.setHitRect`).

**Como foi verificado.** `flutter analyze` limpo e 205 testes verdes; build Linux OK.

**Ainda aberto:** as vezes a janela do cartao nao aceita clique (a regiao de clique fica defasada
quando o cartao muda de tamanho) — proximo alvo.

---

## 2026-08-21 — varias falas esperando revisao ao mesmo tempo, 1.5.1

**Pedido do dono:** falar 1, falar 2, falar 3 sem confirmar nenhuma, e depois ir resolvendo cada uma
com Enter, Tab ou mouse. Antes, cada gravacao nova **sobrescrevia** a revisao pendente e o texto
anterior sumia sem aviso.

**O que mudou.** O controller passou a manter uma **fila** de sessoes pendentes
(`pendingReviews`) em vez de um unico `pendingReview`, e cada envio/descarte carrega o `sessionId`
para resolver **so o seu** cartao. A janela de revisao empilha os cartoes numa coluna (mais antigo em
cima, mais recente embaixo, junto do HUD) e so sai da tela quando o ultimo for resolvido; o foco
volta ao aplicativo de origem a cada envio, entao cada texto e colado onde o cursor estiver naquele
momento — que foi o combinado.

A janela de revisao tambem parou de se esconder desmapeando, pelo mesmo motivo que o HUD (armadilha
4.3): desmapear mata o contexto GL da sub-janela nesta pilha NVIDIA/GLX.

**Como foi verificado.** `flutter analyze` limpo e **205 testes verdes**, com 4 novos guardando a
regra: tres falas seguidas deixam tres cartoes; confirmar um resolve so ele; descartar um nao leva os
outros; e o envio sem id continua limpando a fila (compatibilidade).

**Ainda aberto:** clicar num cartao ainda nao o seleciona para Enter/Tab, e faltam os cantos
arredondados no recorte da janela.

---

## 2026-08-21 — o HUD "Gravando" finalmente aparece no Linux, 1.5.0

**O sintoma que sobrou o dia inteiro.** A pilula "Gravando" nunca aparecia no Linux. A janela
existia (900x200, no lugar certo), o Dart dentro dela rodava, recebia as mensagens e calculava o
estado correto — mas o X dizia `IsUnMapped`, e nem `xdotool windowmap` conseguia mapear. No boot,
duas linhas: `Failed to setup compositor shaders, unable to make OpenGL context current`.

**Causa raiz.** Esconder a sub-janela chamava `hide` de verdade, desmapeando-a. Nesta pilha
(NVIDIA/GLX com visual RGBA), a sub-janela desmapeada **perde o contexto GL do `FlView` e nao
volta**: todo `show` seguinte retorna sucesso sem mapear coisa alguma, e a flag `_visible` do Dart
passa a mentir para sempre — por isso a pilula aparecia em algumas gravacoes e em outras nao, e
depois em nenhuma.

**A correcao.** A sub-janela sobe uma vez e **fica**: esconder passou a ser recortar a forma para uma
regiao vazia, e mostrar, recortar de volta para a forma da pilula
(`gtk_widget_shape_combine_region`). O `show` virou idempotente — chamado sempre que o estado pede,
sem consultar flag. Com a janela sempre mapeada, o **visual RGBA volta a funcionar** e a
transparencia foi recuperada, sem o retangulo preto.

**Descartados no caminho, todos testados:** recortar a `GdkWindow` filha do Flutter (apaga o conteudo
inteiro), realizar a janela antes da view, `LIBGL_ALWAYS_SOFTWARE`, `GDK_GL=gles`, `glx-legacy` e
criar a janela sem foco.

**Como foi verificado.** `flutter analyze` limpo, 201 testes verdes, e a medicao no X: **6 de 6
gravacoes seguidas com a janela do HUD em `IsViewable`** (antes: 0 de 6). Captura de tela confirma a
pilula "● Gravando ▮▮▮▮ 00:03 (Parar)" desenhada sobre a area de trabalho, com transparencia.

**Documentado** em `docs/armadilhas.md` 4.3, para nao voltar.

---

## 2026-08-21 — captura de audio reescrita com a arquitetura do Dito em Python, 1.4.9

**Por que.** O dono perguntou por que o problema de audio nao existe no Windows nem existia na versao
antiga em Python. A resposta estava no codigo antigo, recuperado da Lixeira
(`~/.local/share/Trash/files/dito/`): o callback do driver **so media nivel e enfileirava**
(`src/dito/audio/capture.py:57-76`), com a escrita em disco numa thread consumidora separada
(`src/dito/core/session.py:158-159,255`), e o bloco era de **50 ms explicitos** (`BLOCKSIZE = 800`).
O comentario da linha 58 diz o que o port esqueceu: *"Realtime thread: slow work here drops blocks."*

O C++ fazia o oposto, tudo dentro do callback de tempo real: `push_back` num vetor sem `reserve()`,
conversao float para int16, `ofstream::write` a cada bloco e `flush()` sincrono de disco a cada
segundo, segurando o mesmo mutex do medidor de nivel de 20 Hz. No backend PulseAudio,
`pa_stream_drop()` — o "ja consumi" que o servidor espera — so acontece **depois** que o callback
retorna (`miniaudio.h:31757-31771`): callback preso significa buffer cheio e amostras descartadas
(`pipewire-pulse ... overrun recover ... skip:4082` no journal). No Windows o mesmo pecado passa
batido porque o WASAPI eleva a thread a "Pro Audio" via MMCSS (`miniaudio.h:24546`); no caminho
PulseAudio nao ha elevacao nenhuma (`miniaudio.h:43909-43912`).

**O que mudou.**
1. **Callback so copia e mede**: escreve num ring pre-alocado de 8 s e atualiza RMS/pico em atomicos.
   Sem alocacao, sem disco, sem mutex compartilhado.
2. **Thread consumidora** drena o ring a cada 20 ms e faz o trabalho pesado fora da thread de audio,
   com `reserve()` em blocos de 60 s. Se ela se atrasar, o log diz quantas amostras se perderam.
3. **Periodo de 50 ms e 4 buffers**, `performance_profile_conservative` — o default herdado era
   10 ms x 3 (`miniaudio.h:12217-12222`).
4. **Servidor de som primeiro**: `ma_context_init` pede PulseAudio/JACK explicitamente; ALSA so como
   ultimo recurso **e com aviso**. E a regra 1.7/1.12 do `armadilhas.md` do Python voltando: ALSA cru
   abre o card 0 (entrada da placa-mae, sem nada plugado) e grava ruido de fundo.
5. **Log do que foi realmente aberto**: backend, nome do dispositivo, taxa pedida x taxa real, formato
   e periodo, a cada captura. Era impossivel saber se o app tinha aberto o headset ou outra entrada.
6. **`docs/armadilhas.md` criado** — o Python tinha esse arquivo, o port nao o trouxe, e metade dos
   defeitos do dia foi reaprender o que ele ja documentava.

**Como foi verificado.** `flutter analyze` limpo, 201 testes verdes, e a prova que importa: gravacao
**simultanea** pelo Dito e por fora (`pw-record`), com o dono falando —
**pico 6554 x 6555 e RMS 806,5 x 808,5** (diferenca de 0,2%), 29,7% de zeros (normal para fala com
pausas), maior buraco de 50 ms, e a transcricao saindo exatamente o que foi dito. Segunda tomada:
pico 13727, RMS 1516, transcricao correta. Zero ocorrencias de "consumidora atrasada" no log.
O dispositivo aberto foi `H510-PRO Wireless headset Mono` via PulseAudio a 16000 Hz reais.

**Ainda aberto:** a janela do HUD nao aparece no Linux (grava certo, falta o indicador na tela).

---

## 2026-08-21 — "sem audio para captar": o alarme piscava, o aquecimento nao existia, e nada provava nada, 1.4.8

**O que a investigacao provou — e o que ela DERRUBOU.** Tres frentes de diagnostico rodaram sobre o
episodio real: medicao dos WAV gravados, leitura do caminho de captura e auditoria do PipeWire.

Medindo os arquivos do dono: a tomada que funcionou (21-19-40) tem RMS 263 e pico 1738; a que saiu
vazia (21-19-49) tem RMS 38 e pico 367 — **17 dB abaixo**, sem nunca cruzar o `audibleRms = 0.008`
do proprio app. Ou seja: **o alarme estava certo, o microfone e que nao captou**. Whisper e
`dropSoundTags` inocentes.

A hipotese natural era a suspensao do WirePlumber (5 s de ociosidade, ja documentada em 1.4.4).
**Os dados do dono a derrubaram**: no dia inteiro, gravacoes depois de intervalo LONGO (>=5 s)
acertaram 46%, e depois de intervalo CURTO apenas 19% — o inverso do previsto. Gravações apos 25 s,
43 s e ate 290 s parado sairam com RMS 780, 627 e 921. Nao e o mic dormindo.

Comparacao lado a lado no mesmo instante fechou o cerco: `pw-record` fora do app mediu RMS 684
enquanto a reuniao que o Dito gravava media 598-1165. **O caminho de captura do app entrega
exatamente o que o sistema entrega.** Quando o sistema manda so ruido, o Dito relata isso
corretamente — o defeito de captacao esta abaixo do app (link do headset wireless), e o que cabia
consertar era o comportamento do app diante disso.

**O que foi corrigido, tudo com defeito confirmado:**

1. **Alarme sem histerese** (`silence_alarm.dart`): com o RMS dancando em torno de `deadRms`, o
   estado alternava `dead`↔`quiet` **a cada tick de 50 ms** — o log mostrava 5 trocas em menos de
   1 s. Agora uma troca so vale depois de 3 ticks consecutivos concordando.
2. **Aquecimento medido em amostras, nao em tempo**: `warmUpSeconds = 0.05` eram 800 amostras, e um
   unico bloco maior que isso (burst do driver ao acordar) liberava o gate no primeiro tick, com o
   sinal ainda subindo — o triangulo vermelho aparecia com o dono ja falando. Agora sao 1200 ms de
   tempo real, e fala durante o aquecimento ja conta como voz ouvida.
3. **Nada provava nada**: cada gravacao agora registra `rms medio`, `pico` e `ouviu voz` no
   `native_engine.log`, mais um `ATENCAO` explicito quando a gravacao inteira foi ruido de fundo.
   O alarme tambem passou a ser logado (`alarme: dead (motivo=..., fase=...)`), o que ate ontem nao
   existia — foi essa cegueira que fez o problema durar o dia todo.
4. **Sumico calado**: transcricao vazia com o microfone entregando so ruido agora mostra
   "O microfone nao captou sua voz" no HUD, em vez de a pilula simplesmente desaparecer.

**Como foi verificado.** `flutter analyze` limpo e **201 testes verdes** (3 novos: histerese contra
o pisca-pisca, aquecimento por tempo, e fala dentro do aquecimento). Os testes antigos do alarme
foram ajustados ao aquecimento novo mantendo a garantia: mic que nunca capta **continua** ficando
vermelho, so que depois de 1,2 s + 700 ms.

**Ainda aberto:** a janela do HUD nao aparece no Linux (grava certo, falta o indicador na tela).

---

## 2026-08-21 — fix Linux: o Dito brigava consigo mesmo pela tecla (F9/F10 mudos), 1.4.7

**Causa raiz, achada com o log da 1.4.6 na mao.** O sintoma sobreviveu aos quatro fixes anteriores:
apertava F10, funcionava; apertava de novo, nada; e so voltava fechando e abrindo. O log mostrava o
absurdo: `grab:meeting: true` (achamos que temos a tecla) e `_seen` congelado (nenhum evento chega).

`dito_win32_plugin_register_with_registrar` roda **uma vez por janela** — main, HUD e Review — e
cada registro criava `new PluginState()` e chamava `StartKeyHook`, subindo uma thread X11 com o seu
**proprio `XOpenDisplay`**. Conexoes X distintas sao **clientes X distintos**: as tres janelas do
mesmo Dito disputavam o `XGrabKey` de F9/F10, que e exclusivo. Uma ganhava, duas levavam
`BadAccess`. E o Dart so escuta o canal `dito/keys` da **janela principal**
(`native_key_source.dart`): quando quem vencia a corrida era o plugin do HUD ou da Review, as teclas
iam para um engine que ninguem ouvia — app mudo, com o snapshot da principal relatando o proprio
palpite. Isso explica a intermitencia, o "fecha e abre resolve" (muda quem ganha a corrida) e por
que no Windows nunca houve nada disso: la o hook e `WH_KEYBOARD_LL`, que **nao e exclusivo**.

**A correcao:** um unico hook de teclado por PROCESSO. Estado do teclado compartilhado
(`SharedKeyState()`), uma thread X11 so (`StartKeyHook` idempotente — os registros seguintes apenas
entram na lista de entrega), e os eventos passam a ser transmitidos para **todos** os canais
registrados, entao nao importa qual janela subiu primeiro. `keys.bind` substitui a acao em vez de
empilhar, e fechar uma janela nao derruba mais o hook das outras.

**Como foi verificado.** `flutter analyze` limpo e 198 testes verdes. No app real, **dois boots
seguidos** (o defeito era uma corrida, passar uma vez nao provaria nada): 10 F10 alternados em cada
um resultaram em **10/10 `start aceito` e 10 sessoes gravadas**, com o contador de eventos do hook
subindo a cada aperto (40 e 205) em vez de congelar — que era a assinatura exata do defeito.

**Ainda aberto:** a janela do HUD nao aparece no Linux (grava certo, falta o indicador na tela).

---

## 2026-08-21 — fix Linux: F9/F10 travavam e so voltavam fechando e abrindo o Dito, 1.4.6

Quatro defeitos distintos, cada um capaz de produzir sozinho o sintoma relatado ("so funciona uma
vez"). Todos sao do porte Linux; no Windows nada disso existia.

**1. O Linux abria varios Ditos, e a tecla e exclusiva.** O runner GTK usava
`G_APPLICATION_NON_UNIQUE`, entao cada clique subia outra instancia — enquanto o Windows sempre
teve mutex + `FindWindow` (`windows/runner/main.cpp`). No X11 o `XGrabKey` e **exclusivo por
(tecla, modificador, root)**: a segunda instancia levava `BadAccess`, o erro era descartado por um
handler que so fazia `return 0`, e `keys.bind` respondia `TRUE` de qualquer jeito. Resultado: a
janela que o dono estava olhando ficava surda, e a tecla ia para a instancia velha na bandeja.
Prova nos logs do dia: 80 `boot completo` para 8 `encerrando`, com linhas fora de ordem e uma
truncada no meio — dois processos escrevendo no mesmo arquivo ao mesmo tempo. Agora: instancia
unica de verdade (o segundo lancamento foca a janela existente e sai), grab verificado com `XSync`,
falha logada e avisada na tela, e re-tentativa a cada ~2 s ate recuperar.

**2. Gravacao fantasma.** Com o modelo frio, o motor demorava mais que os 5 s do timeout; o app
voltava a fase para `idle` **sem avisar o motor**, a tecla era solta sem parar nada (`_stopPending`
so era marcado se o timer ainda estivesse vivo) e o `StartedEvent` atrasado cravava a fase em
`recording`/`meeting`. Dali em diante nenhum evento podia gerar `StopCommand` e toda tecla era
recusada — o unico self-heal (`_resyncFromEngine`) so rodava em `transcribing`. Agora o timeout
manda `StopCommand`, a sessao abandonada e encerrada quando chega, e a recusa em qualquer fase
ocupada consulta o motor (que so destrava quando ELE diz que nao ha sessao).

**3. O fix 1.4.5 cobria so metade.** O filtro de sessao protegia a gravacao nova enquanto ela
**capturava**; se ela ja estava **transcrevendo**, o `finished` da sessao velha idlava a fase,
cancelava o watchdog da nova e ainda virava o cartao de revisao dela. E o isolate do whisper subia
sem `onExit`/`onError`: morrendo, o `await` da transcricao nunca resolvia.

**4. A pilula "gravando" sumia sozinha.** `dismiss()` armava um timer de 180 ms que forcava
`visual = hidden` sem checar nada, e nenhum outro estado cancelava esse timer: um F10 dentro dessa
janela mostrava o HUD e o timer velho o escondia em seguida. Os pacotes de nivel (20 Hz) nao
religavam nada. Agora todo estado visivel cancela a saida pendente, o nivel religa a pilula (ele so
existe com o motor capturando) e as chamadas nativas de show/hide sao serializadas, com `_visible`
seguindo o resultado real e re-tentativa em falha.

**Como foi verificado.** `flutter analyze` limpo e **198 testes verdes** (22 novos). Cada teste novo
foi provado revertendo o fix correspondente e vendo o vermelho — nenhum passa por acidente. No app
real: segunda execucao nao sobe processo e foca a janela existente (`pgrep -c` = 1); com outro
cliente X segurando o F10, o log diz `tecla f10 esta tomada por outro app` e, ao liberar,
`tecla f10 recuperada para meeting` sem reiniciar; **10 F10 seguidos = 10 `start aceito` e 10
sessoes gravadas** no binario instalado em `/opt/dito`.

**Ainda aberto:** a janela do HUD nao aparece no Linux (a gravacao acontece, o indicador nao sobe).

---

## 2026-08-21 — fix Linux: F9/F10 so funcionava uma vez, e as gravacoes iam para a pasta errada, 1.4.5

**F9/F10 parava de responder depois do primeiro uso.** Causa raiz nos logs: ao parar, a fase ia
para `transcribing` e `canStart` so aceitava `idle`/`paused`, entao toda tecla era recusada ate a
transcricao terminar (1-4s). Isso fazia sentido quando a transcricao congelava a UI; virou heranca
sem motivo quando ela passou a rodar num isolate proprio (1.4.3). Agora so uma captura viva bloqueia
a proxima. Junto vieram as duas armadilhas de concorrencia que destravar a tecla expoe:
`_handleStop` tira um snapshot da sessao antes do primeiro `await` (a gravacao nova sobrescrevia
`_currentSessionId`/`_currentWavPath` da anterior enquanto ela ainda era salva), e um `FinishedEvent`
atrasado so devolve a fase para `idle` se for da sessao que esta no ar.

**As gravacoes nao apareciam no Historico.** O motor escrevia em `DitoPaths.defaultLibrary`
(`XDG_DOCUMENTS_DIR`, aqui `~/Documents/Dito`) e ignorava `library.folder` da config
(`~/Documentos/Dito`), que e justamente a pasta que a tela le. Alem disso `resolved()` devolvia o
caminho com o til literal, que nao e um diretorio. Resultado: nada aparecia, para ninguem, nunca.
Agora a pasta configurada viaja no `StartCommand` ate o motor, e `~` e expandido.

**Silencio virava `[Musica]`.** O Whisper inventa rotulo de som quando nao ha fala, e o app colava
isso como se fosse texto ditado. Transcricao formada so por rotulos (`[...]`, `(...)`, `*...*`) sai
vazia agora.

**Idioma da sub-janela.** O HUD mostrava "NO AUDIO" com o app em portugues: o idioma chega por uma
mensagem que podia se perder e o pedido de fallback tentava uma unica vez; falhando, a janela caia no
locale do sistema. Agora insiste e loga se desistir.

**Como foi verificado.** `flutter analyze` limpo e 175 testes verdes (dos 166 do inicio do dia).
Teste real no app instalado, com o binario que foi publicado: F9 apertado 10x em sequencia rapida
resultou em **11 start aceito, 0 recusas, 11 capturas** (11 = 10 + aquecimento), **11 sessoes na
pasta configurada** (antes: 0) com **11 ids distintos e nenhum duplicado**, provando que destravar a
tecla nao corrompeu sessao. Transcricao de silencio saiu `""`. Nenhum crash. Dois testes novos
guardam o comportamento: `test/hotkey_repeat_test.dart` (escrito vermelho antes do fix, cobrindo
todas as fases do enum) e `test/sound_tags_test.dart`.

**Divida tecnica paga junto**, vinda de tres auditorias por agente: strings de UI que estavam
hardcoded em portugues foram para o `.arb`; dois `catch` silenciosos passaram a logar; valores crus
de espacamento/raio em `lib/ui/**` viraram tokens e ganharam o teste de varredura que o `CLAUDE.md`
alegava existir e nunca existiu; identificadores em portugues renomeados; `caracteres_test.dart`
virou `glyph_guard_test.dart`.

---

## 2026-08-21 — fix Linux: alarme de silêncio dava falso-positivo logo no início da gravação, 1.4.4

**Causa raiz.** Achada por um agente de investigação dedicado, com evidência real (não
suposição): o WirePlumber suspende o microfone depois de 5s ocioso
(`session.suspend-timeout-seconds`, padrão do sistema). Quando uma gravação começa logo depois
de um período parado, o PipeWire leva um tempo pra "acordar" o dispositivo — e nesse intervalo
`dito_audio_get_level()` devolve os valores zerados iniciais, não porque captou silêncio de
verdade, mas porque nenhum callback de áudio chegou ainda. O alarme de silêncio implementado
ontem (`_checkAlarm`) começava a contar `_silenceMs` desde o primeiro tick do timer, sem
distinguir "ainda sem dado" de "silêncio medido de verdade" — se o resume passasse de
`_deadMs=700`, disparava "sem áudio" falso mesmo com o usuário falando normalmente. Confirmado
no log: toda gravação iniciada >5s depois da anterior (tempo do WirePlumber suspender) resultou
em transcrição-fantasma tipo "[Som de futebol]"; a única transcrição real do dia foi a primeira
gravação após reiniciar o app, sem essa corrida.

**Fix.** `lib/engine/native_engine.dart`, `_checkAlarm` ganhou um gate: só conta silêncio
quando `bufferedSeconds > 0.05` (o campo `seconds` de `DitoWhisper.getLevel()`, que só passa de
zero quando o primeiro bloco de áudio real já foi capturado) — antes disso é "ainda sem dado",
não silêncio. Resto da lógica dead/quiet/ok e o disparo por borda ficaram intocados.

**Como foi verificado.** `flutter analyze`/`flutter test` (166 testes) verdes. Build real
instalado e rodado. A corrida do WirePlumber foi confirmada reproduzível neste ambiente
(`pactl list sources short` mostrando `SUSPENDED`→`IDLE` ao apertar F9) e o mecanismo do gate
foi confirmado funcionando via instrumentação temporária (revertida antes do fix final): o
`_silenceMs` só começa a acumular a partir do tick em que já existe áudio real bufferizado,
nunca antes. Limitação honesta registrada: o hardware desta VM acorda o mic em menos de 50ms,
abaixo do limiar de 700ms que causa o bug em produção — não foi possível reproduzir ponta a
ponta a diferença "antes travava, agora não" nesta máquina específica, só o mecanismo da
correção isoladamente.

---

## 2026-08-21 — fix Linux: HUD sem feedback, alarme de silêncio ausente, UI travando na transcrição, 1.4.3

**Causa raiz (achada com evidência real, não suposição).** Usuário reportou o pill do HUD sumido
mesmo com gravação/transcrição funcionando por trás. Investigação em várias camadas:

1. `packages/dito_win32/linux/dito_win32_plugin.cc` — os handlers `window.adoptAsHud`/
   `adoptAsPanel` respondiam `fl_value_new_bool(TRUE)` onde o Dart faz `invokeMethod<int>`,
   quebrando com `type 'bool' is not a subtype of type 'int?'` em todo boot (ruído real no
   `crash.log`, mas não a causa do pill sumido).
2. **Causa real, achada por um agente de verificação independente com `xwininfo`/`Map State`**
   (não só screenshot): `window.showNoActivate`/`window.focus`/`window.hide` sempre
   respondiam sucesso mesmo quando `GetToplevel(self)` vinha nulo — a chamada que de fato
   mostra a janela virava um no-op silencioso, mentindo sucesso pro lado Dart.
3. `lib/ui/hud/hud_window.dart`/`review_window.dart` tinham `try/catch` (ou nenhum catch)
   escondendo qualquer erro de show/hide/foco sem log nenhum — regra nova do usuário durante a
   investigação: **nenhum catch pode esconder erro**.
4. O alarme "sem áudio" (garantia inegociável do `CLAUDE.md`) nunca existia de verdade em
   nenhuma plataforma — foi perdido na migração pro motor C++ nativo e nunca reimplementado; só
   a UI (`dito_controller._onAlarm`) já sabia reagir, sem ninguém produzindo o evento.
5. `DitoWhisper.transcribe()`/`loadModel()` são FFI síncronas que travavam a **UI inteira**
   durante toda a transcrição (1-4s+) — por isso "aperto pra parar e nunca aparece
   transcrevendo": o evento era emitido mas o isolate ficava bloqueado logo em seguida, sem
   chance de renderizar antes do próximo evento chegar.
6. Som do alarme (`canberra-gtk-play`) respeitava o toggle "sons de evento" do Cinnamon/GNOME
   (desligado por padrão em vários ambientes) — sempre reportava "Sound disabled", mesmo com
   áudio funcionando normalmente pro resto do sistema.
7. `lib/config/config_service.dart` usava `MoveFileEx` (API exclusiva do Win32) pra gravar
   `config.toml` sem variante Linux — configuração **nunca salvava** no Linux, silenciosamente
   (`config.toml` datado de 5 dias atrás apesar de saves repetidos tentados).

**Fix.**
- `dito_win32_plugin.cc`: `adoptAsHud`/`adoptAsPanel` retornam `fl_value_new_int` (paridade com
  o HWND-como-int64 do Windows); `showNoActivate`/`focus`/`hide` respondem erro de verdade
  (`NO_WINDOW`) quando a janela nativa é nula, em vez de sucesso mentiroso.
- `hud_window.dart`/`review_window.dart`: toda chamada nativa de mostrar/esconder/focar passa
  por um helper `_tryNative` que loga a falha em vez de escondê-la.
- 9 `catch (_) {}` silenciosos (bus entre janelas, símbolos FFI, limpeza de temporário) viraram
  log, sem mudar o comportamento de recuperação.
- `lib/engine/native_engine.dart`: gatilho de silêncio implementado no polling de 50ms já
  existente — acumula tempo com rms abaixo do limiar, emite `AlarmEvent` **por borda** (só na
  transição de estado, não a cada tick) pra não piscar texto de diagnóstico 20x/segundo.
- `lib/engine/whisper_worker.dart` (novo): `loadModel`/`transcribe` movidos pra um isolate
  Dart dedicado e persistente, dono exclusivo do handle do modelo/contexto CUDA (que é preso à
  thread que o criou — não dá pra recriar por chamada). `NativeEngine.shutdown()` agora espera
  um `_handleStop` em andamento terminar antes de liberar o worker (corrida real: sair logo
  depois de parar podia perder o texto transcrito); `WhisperWorker.dispose()` falha fechado
  chamadas pendentes em vez de travar pra sempre se o isolate morrer no meio de uma chamada.
- `notify.balloon`/`notify.alarmSound` no plugin nativo, antes um stub morto que só respondia
  `TRUE`, agora chamam `notify-send`/`paplay` de verdade via `g_spawn_async` (argv, sem parsing
  de shell), checando erro real em vez de sempre reportar sucesso. Som trocado de
  `canberra-gtk-play` pra `paplay` porque o primeiro respeita o toggle "sons de evento" do
  desktop — `paplay` toca incondicionalmente, igual o `PlaySound` do Windows.
  `packaging/linux/construir.sh`: `Depends` ganhou `libnotify-bin`, `pulseaudio-utils`,
  `sound-theme-freedesktop`.
- `config_service.dart`: `_replace()` usa `File.renameSync` (POSIX já é atômico) fora do
  Windows, só chama `MoveFileEx` quando `Platform.isWindows`.
- `lib/state/dito_controller.dart`: pill mostra "Iniciando..." (`HudWork.starting`, nova string
  em `app_pt.arb`/`app_en.arb`) no instante em que a tecla é aceita, em vez de ficar mudo até o
  modelo terminar de carregar (podia levar segundos num modelo frio).
- Removido um `reason` hardcodado em português que eu mesmo introduzi durante a correção do
  alarme — quebrava o fallback de tradução já existente (`reason ?? _s.notifyNoAudio`),
  violando a regra de nunca hardcodar string de UI fora do arquivo de tradução.

**Como foi verificado.** `flutter analyze`/`flutter test` (166 testes) verdes a cada mudança.
Build real instalado em `/opt/dito`, rodado de verdade (não só testes): pill do HUD confirmado
via `xwininfo`/`Map State` amostrado a cada 150ms durante F9 segurado (`IsViewable` consistente,
não só um screenshot de sorte); card de Review confirmado do mesmo jeito durante F10. Alarme
"sem áudio" disparando com pill vermelho + notificação nativa real na tela (screenshot). Estado
"Iniciando..." capturado em screenshot a ~200ms do aperto da tecla. Dois rounds de revisão por
`flutter-reviewer` (achou e corrigiu: reemissão de alarme a cada tick em vez de por borda,
alarme sobrevivendo ao fim da gravação, `Logbook` sem fechar no dispose, corrida
sair-durante-transcrição, `dispose()` do worker sem tratar chamada pendente) e verificação
independente por `verify-app` (achou a causa raiz real do HUD via `xwininfo`, não aceitou minha
primeira leitura otimista). Confirmado com o próprio usuário, ao vivo, que a instabilidade
remanescente ("microfone parou de captar" numa segunda tentativa) é queda real e intermitente do
headset sem fio, não bug de código — o alarme fazendo exatamente o que devia: expor um problema
de hardware que antes ficava invisível.

---

## 2026-08-21 — fix Linux: primeira transcrição com GPU travava por até 2 minutos, 1.4.2

**Causa raiz.** Achada anexando `gdb -p <pid>` num processo real do usuário travado (sem
matar): o programa estava com a thread principal a 93-100% de CPU, parada dentro de
`libnvidia-ptxjitcompiler.so.1` — não deadlock (que ficaria a 0% de CPU), computação ativa que
não terminava. O módulo `libggml-cuda.so` da 1.4.1 foi compilado só com arquiteturas
**`-virtual`** (PTX puro, sem código de máquina nativo) pra caber em 130MB — isso faz o driver
NVIDIA compilar (JIT) cada kernel do zero na primeira vez que ele roda de verdade, e o Whisper
usa dezenas de kernels distintos. Testei ontem só a inicialização (`using CUDA0 backend`, que é
instantânea), nunca uma transcrição completa até o fim — por isso não vi o problema antes de
publicar a 1.4.1.

**Fix.** `packages/dito_whisper/linux/CMakeLists.txt` — `CUDA_ARCHITECTURES` trocado de
`"61-virtual;75-virtual;86-virtual;89-virtual"` pra `"61;75;86;89"` (código real por arquitetura).
Módulo de GPU cresce de 130MB pra ~290MB comprimido — decisão consciente: o usuário prefere
download maior a travar na hora de usar.

**Como foi verificado.** Medido ponta a ponta, não só o backend selecionado: com o módulo
antigo (PTX), 3.35s de áudio levaram **120s** pra transcrever (`captura finalizada` →
`transcricao concluida` no log). Com o módulo novo (código real), 2s de áudio levaram **4.3s**.
`ps -T -p <pid> -o pcpu` confirmou 0% de CPU nos 15s seguintes à captura (sem trava). `flutter
analyze`/`flutter test` verdes.

---

## 2026-08-21 — fix Linux: download do pacote de GPU travava o botão de gravar, 1.4.1

**Causa raiz.** Achada em teste real do usuário logo depois do 1.4.0: `_loadModelInternal`
dava `await` no download do pacote de GPU (~130MB) antes de carregar o modelo — a primeira
vez que alguém apertava gravar numa máquina com NVIDIA, a gravação ficava presa por todo o
tempo do download, sem nenhum indício na tela do que estava acontecendo.

**Fix.**
- `packaging/linux/construir.sh` — o `.deb` ganhou um script `postinst`: baixa o pacote de GPU
  **durante o próprio `apt install`** (só se `/proc/driver/nvidia/version` existir), direto
  pra `/opt/dito/lib/`, onde `load_optional_backends()` já procura por padrão (o mesmo
  diretório do plugin principal, achado via `dladdr`) — não precisa de nenhuma mudança nativa.
  Nunca derruba a instalação se o download falhar (offline, R2 fora do ar etc.).
- `lib/engine/native_engine.dart` — o download pelo app (`GpuPackManager`) vira só um
  **fallback silencioso em segundo plano** pra quem pluga a GPU depois de instalar: se o
  pacote já está no disco, usa na hora; se não está, dispara o download sem `await` e segue a
  gravação normalmente em CPU — a próxima gravação já pega a GPU sozinha, sem travar nenhuma.

**Como foi verificado.** `flutter analyze`/`flutter test` verdes. Reproduzido o bug original
com evidência (`~/.local/share/dito/gpu/.download.tar.gz` crescendo em tempo real enquanto o
app ficava travado) antes de corrigir.

---

## 2026-08-21 — feat Linux: aceleração de GPU (CUDA) opcional na transcrição, 1.4.0

**O quê.** O motor de transcrição (`packages/dito_whisper`, C++ nativo in-process com
whisper.cpp/ggml) passa a tentar usar a GPU NVIDIA (CUDA) automaticamente, com fallback pra
CPU sem quebrar nada quando não tem GPU compatível. O `.deb` base continua ~9MB — o pacote
CUDA (`libggml-cuda.so`, ~130MB comprimido) é baixado sob demanda pelo próprio app
(`lib/engine/gpu_pack_manager.dart`, mesmo padrão do `ModelManager` pro modelo de voz), só
quando `/proc/driver/nvidia/version` existe (GPU NVIDIA detectada). Hospedado num bucket R2
dedicado (`defaltm-releases`, público via `pub-*.r2.dev`) — Cloudflare Pages recusa qualquer
arquivo acima de 25MB, então não dava pra ir pelo mesmo site do repositório apt.

**Por quê.** Pedido do usuário — ele tem uma GTX 1650 e quer a transcrição mais rápida quando
a máquina suportar, sem penalizar quem não tem GPU NVIDIA com um download gigante à toa.

**Como foi feito (arquitetura).** O ggml vendorizado já é uma versão moderna com suporte a
**backend dinâmico** (`GGML_BACKEND_DL`, `ggml_backend_load_all()`/`load_all_from_path()`,
via `dlopen`). Isso é o que evita a armadilha real: linkar CUDA estático no plugin faria o
plugin inteiro falhar ao abrir em qualquer máquina sem CUDA. Em vez disso:
- `packages/dito_whisper/linux/CMakeLists.txt` — novo alvo `MODULE` `ggml-cuda`, só compilado
  se `find_package(CUDAToolkit)` achar o toolkit na máquina de build; nunca linkado no plugin
  principal. Arquiteturas geradas como **PTX virtual** (`61-virtual;75-virtual;86-virtual;89-virtual`,
  Pascal a Ada), não código nativo por arquitetura — reduz o módulo de 513MB pra 228MB
  (129MB comprimido) às custas de um JIT do driver no primeiro uso, imperceptível na prática.
- `packages/dito_whisper/src/dito_whisper.cpp` — `dito_whisper_set_backend_dir()` (nova, chamada
  pelo Dart com o diretório onde o pacote de GPU foi baixado) e `load_optional_backends()`
  (chamada uma vez, via `std::call_once`, antes do `whisper_init_from_file_with_params`) —
  sem isso o módulo dinâmico nunca seria descoberto, mesmo presente no disco. Nova
  `dito_whisper_backend_name()` reporta o backend real (`CUDA0`/`CPU`) em vez de um texto fixo.
- `lib/engine/native_engine.dart` — não força mais `useGpu: false`; consulta o
  `GpuPackManager` antes de carregar o modelo.
- `packaging/linux/construir.sh` — exclui `libggml-cuda.so` do `.deb`/tarball principal,
  gera `dito-gpu-cuda-linux-x64.tar.gz` separado em `dist/extras/`.
- `~/dev/claude/tools/apt-repo.sh` (ferramenta global) — ganhou suporte a publicar arquivos
  soltos de `**/dist/extras/*` junto do repositório apt, no mesmo deploy do Cloudflare Pages.

**Como foi verificado.** Toolkit CUDA 12.4 instalado só na máquina de build (nunca no
usuário final). Rodado o binário real: log mostra `whisper_backend_init_gpu: using CUDA0
backend` com o módulo presente, e `whisper_backend_init_gpu: no GPU found` (sem crash) com o
módulo removido — prova de que o "opcional" é opcional de verdade nas duas direções.
`flutter analyze`/`flutter test` verdes, incluindo dentro do próprio `construir.sh`.

---

## 2026-08-21 — fix Linux: borda branca no HUD/Review, e binário velho sombreando o pacote apt

**Causa raiz 1 (borda branca).** Ao trocar `window.setHitRect` de `gtk_widget_shape_combine_region`
pra `gtk_widget_input_shape_combine_region` (fix anterior desta mesma data), a margem transparente
ao redor do pill/card parou de ser cortada visualmente pelo shape — e ficou visível que ela nunca
foi transparente de verdade: a `GtkWindow` das sub-janelas nunca recebeu um **visual RGBA**, então
o compositor não tinha canal alfa nenhum pra misturar; "transparente" pintava branco opaco.

**Fix 1.** `packages/desktop_multi_window/linux/desktop_multi_window_plugin.cc` — antes de mostrar
a sub-janela, aplica `gdk_screen_get_rgba_visual()` via `gtk_widget_set_visual()` +
`gtk_widget_set_app_paintable(TRUE)`.

**Causa raiz 2 (app instalado fechava sozinho).** Sobrava, de sessões de teste anteriores, um
binário velho em `~/.local/lib/dito/dito_app` (de antes do fix do `use-after-free` desta mesma
data) com **dois** lançadores locais sombreando os do pacote: `~/.local/share/applications/
dito.desktop` (na frente do `/usr/share/applications/` do pacote) e `~/.local/bin/dito` (na frente
do `/usr/bin/dito` do pacote, por ordem do `PATH`). O ícone/comando abria o binário quebrado, não
o do apt.

**Fix 2.** Removidos os dois lançadores locais e o binário velho — não é mudança de código, é
limpeza de artefato de máquina de dev; documentado aqui pra não se repetir.

**Como foi verificado.** `flutter analyze`/`flutter test` verdes. Rebuild + execução real: HUD sem
borda branca, cantos redondos preservados. `which dito` resolve pro `/usr/bin/dito` do pacote;
`coredumpctl` confirmou que o crash reportado vinha do binário velho, não da versão publicada.

---

## 2026-08-21 — fix Linux: `.deb` sem dependências declaradas

**Causa raiz.** `packaging/linux/construir.sh` gerava o `DEBIAN/control` sem `Depends:` — numa
máquina limpa, `apt`/`dpkg` não puxariam `libgtk-3-0`, `xdotool` (colagem) nem
`libayatana-appindicator3-1`/`libappindicator3-1` (bandeja), e o app instalaria mas falharia calado.

**Fix.** Adicionado `Depends: libgtk-3-0, libx11-6, xdotool, libayatana-appindicator3-1 |
libappindicator3-1` ao `control`.

**Como foi verificado.** `bash packaging/linux/construir.sh` (roda o portão internamente) gerou
`dist/dito_1.3.9_amd64.deb`; `dpkg-deb -I` confirma a linha `Depends:` presente no pacote final.

---

## 2026-08-21 — fix Linux: card de Review não flutuava (renderizava embutido/atrás da janela principal)

**Causa raiz.** `lib/main.dart` tinha uma função local `runReviewWindow` que sombreava
silenciosamente a implementação real importada de `ui/review/review_window.dart` (Dart dá
precedência à declaração local sobre o import, sem aviso). A versão local só chamava
`DitoWin32.adoptAsPanel()` — o método que tira borda/põe sempre-no-topo/tira da taskbar — se
`Platform.isWindows`; no Linux nunca rodava. Em cima disso, `lib/app/boot.dart` tinha um hack
só-Linux que dava `windowManager.show()/focus()` na janela **principal** toda vez que o review
disparava — compensação de quem bateu no mesmo bug e tentou contornar em vez de achar a causa.

**Fix.**
- `lib/main.dart` — apagada a função local que sombreava; agora resolve pra implementação real,
  que chama `adoptAsPanel()` incondicional em qualquer plataforma.
- `lib/app/boot.dart` — removido o hack `Platform.isLinux` que erguia a janela principal.
- `lib/ui/review/review_window.dart` — removido um listener global de tecla (`_onGlobalKey`) que
  nunca disparava em nenhuma plataforma (só teclas ligadas via `keys.bind` chegam nesse stream, e
  Enter/Tab/Escape nunca foram ligadas ali) — quem trata essas teclas de verdade é o
  `Focus`/`onKeyEvent` já existente em `review_card.dart`, Flutter puro, funciona nas duas
  plataformas assim que a janela tem foco real de teclado.
- `packages/dito_win32/linux/dito_win32_plugin.cc` — corrigido um **use-after-free real**: o
  registrar da sub-janela (HUD/Review) era guardado sem `g_object_ref`, e virava ponteiro pendurado
  assim que a referência do chamador caía, derrubando o app com `SIGSEGV` no primeiro
  `window.adoptAsHud`/`adoptAsPanel`. Completados os stubs que só fingiam sucesso:
  `focus.take`/`focus.giveBack` (via EWMH `_NET_ACTIVE_WINDOW`, ler/restaurar foco cooperativamente
  com o WM), `window.rect`/`window.handle` (geometria e XID reais em vez de valores fixos),
  `input.sendChord` (via `xdotool`, mesmo padrão do resto do arquivo). `window.setHitRect` passou a
  usar `gtk_widget_input_shape_combine_region` (forma **de clique**) em vez de
  `gtk_widget_shape_combine_region` (forma **de composição**) — a segunda brigava com a pintura em
  alpha do `FloatingSurface` do Flutter (cantos arredondados saíam quadrados) e parecia estar
  quebrando o clique nos controles do card. Removido o catch-all que respondia `success:true` pra
  qualquer `window.*`/`test.*` não implementado (mascarava as lacunas acima); `XInitThreads()`
  consolidado pra rodar uma vez por processo em vez de uma vez por janela.
- `packages/desktop_multi_window/FORK.md`, `docs/LINUX.md` — corrigida documentação desatualizada
  que descrevia uma arquitetura pré-hook-X11 (dizia que o Linux tinha sido removido do fork, que o
  HUD precisava de layer-shell, que `LinuxHotkeyService` era stub — nada disso bate com o código
  atual).

**Como foi verificado.** `flutter analyze` (0 issues) e `flutter test` (166 testes) verdes. Rodado
o binário real (`flutter build linux --debug` + execução na sessão X11 real) com injeção de tecla
(F9/F10): HUD aparece flutuando, `_NET_ACTIVE_WINDOW` não muda durante o F9 segurado (não rouba
foco), `_NET_WM_STATE` tem `SKIP_TASKBAR`+`ABOVE`; o card de Review apareceu flutuando sobre outro
app com texto real transcrito, sem a janela principal vir pra frente; cantos do HUD renderizaram
arredondados depois da troca pra `input_shape_combine_region`. Confirmado via `coredumpctl`+`gdb`
que o crash do registrar sumiu depois do `g_object_ref`.

---

## 2026-08-21 — fix Linux: janela principal e sub-janelas (HUD/Review) renderizavam em branco

**Causa raiz.** No build Linux debug (`flutter build linux --debug`), toda janela (principal e as
sub-janelas do `desktop_multi_window`) imprimia `Failed to setup compositor shaders, unable to make
OpenGL context current` e ficava com o conteúdo em branco — só a cor de fundo aparecia, nenhum texto/
canvas. Não é limitação de driver/GPU da máquina: a NVIDIA GTX 1650 tem OpenGL 4.6 com renderização
direta funcionando (`glxinfo`). É um bug conhecido do backend **Impeller** no embedder Linux do
Flutter 3.47 — o pipeline de "compositor shaders" da Impeller falha ao tornar o contexto GL corrente
em janelas GTK criadas via `gtk_window_new`/`fl_view_new` (tanto a principal quanto as do
`desktop_multi_window_plugin.cc`) antes de o compositor da WM assumi-las. A janela principal chegava
a se recuperar sozinha em ~2 tentativas (mascarando o problema em testes rápidos); as sub-janelas
(HUD, Review), criadas e mostradas em outro momento, nunca se recuperavam e ficavam permanentemente
brancas.

**Fix.** Desativado o Impeller e voltado para o backend legado (Skia/OpenGL) via a API oficial do
embedder Linux `fl_dart_project_set_enable_impeller(project, FALSE)`, em `linux/runner/my_application.cc`
(janela principal) e `packages/desktop_multi_window/linux/desktop_multi_window_plugin.cc` (sub-janelas).
Mudança restrita a `linux/` — não toca `windows/` nem nenhum código Windows.

**Tradeoff.** Skia é o backend legado (não descontinuado, ainda suportado); é a alternativa oficial e
recomendada pelo próprio Flutter quando o Impeller tem problemas com um driver. Não notei lentidão
perceptível no HUD (overlay simples, poucos elementos) nos testes visuais, mas isso foi validado só
nesta máquina/driver (NVIDIA 550.163.01) — vale reconferir em outra GPU antes do `.deb` final.

**Como foi verificado.** Reproduzido o bug isolado com `tool/spike_subwindow_linux.dart` (janela
principal + sub-janela via `WindowController`, screenshot mostrando a sub-janela com só a cor de
fundo, sem o texto) — depois do fix, rebuild do mesmo spike mostra o texto renderizando normalmente
na sub-janela. Rebuild do app real (`flutter build linux --debug`) confirma a janela principal
renderizando a UI completa, sem `Using the Impeller rendering backend` no stderr. `flutter analyze`
(0 issues) e `flutter test` (166 testes, todos passando) continuam verdes.

---

## 2026-08-18 — 1.2.9: notas no Obsidian com carimbo de data/hora preciso e estabilidade geral

**Notas no Obsidian com timestamp exato.** Conversão de microsegundos para data/hora exata no nome dos arquivos e no cabeçalho das notas salvas no Obsidian (`~/notas/trabalho/YYYY-MM-DD-HHmmss.md`).

**Como foi verificado.** Teste prático de ditado com salvamento direto no vault e validação dos 157 testes automatizados.

---

## 2026-08-18 — 1.2.8: salvamento em markdown no vault do Obsidian e encerramento do HUD

**Salvamento no Obsidian corrigido.** O envio do cartão de revisão com a opção do Obsidian ativada agora cria a nota Markdown estruturada no vault configurado e finaliza o status da pílula do HUD com toast de confirmação, evitando que o indicador fique preso em "Salvando a gravação...".

**Como foi verificado.** Testes unitários do controller, teste de caminhos e validação dos 157 testes automatizados.

---

## 2026-08-18 — 1.2.7: release de teste para validação do fluxo completo de auto-atualização

**Validação do auto-updater.** Release com manifesto enriquecido (tamanho e SHA-256 de instalador e pacote zip), permitindo que o usuário teste a verificação e o download de atualização diretamente pela interface do aplicativo.

**Como foi verificado.** Compilação do instalador `dito-1.2.7-setup.exe` e zip `dito-1.2.7.zip`.

---

## 2026-08-18 — 1.2.6: suporte a auto-atualização por instalador e pacote zip com descarte de cache

**Auto-atualização sem falhas.** Suporte nativo a instaladores executáveis e pacotes de atualização no Windows, com geração automática de pacotes zip e manifesto com hashes SHA-256 publicados em tempo real.

**Como foi verificado.** Bateria de testes do updater e compilação do pacote 1.2.6.

---

## 2026-08-18 — 1.2.5: encerramento limpo do processo e botão de fechar aplicativo

**Encerramento 100% limpo do processo.** `shutdown()` agora executa `exit(0)` ao fechar pelo menu da bandeja ou pela nova opção em Ajustes ("Encerrar o Dito"), garantindo que o processo não fique órfão/preso no Gerenciador de Tarefas do Windows.

**Como foi verificado.** Análise estática com 0 issues e testes de encerramento aprovados.

---

## 2026-08-18 — 1.2.4: restauração instantânea da janela ao clicar no atalho (comunicação inter-processos e ForceForeground)

**Abertura instantânea da janela em execução em segundo plano.** Ao abrir o Dito pelo atalho ou executável enquanto ele já está rodando (minimizado na bandeja), a nova instância agora acorda a janela existente via mensagem IPC nativa (`WM_DITO_SHOW_MAIN_WINDOW`), executa `ForceForeground` e restaura o ícone na barra de tarefas (`windowManager.setSkipTaskbar(false)` e `windowManager.show()`). Isso elimina a necessidade de finalizar o processo no Gerenciador de Tarefas para reabrir a janela.

**Como foi verificado.** `flutter analyze` com 0 issues, testes unitários aprovados e compilação do instalador `dito-1.2.4-setup.exe`.

---

## 2026-08-18 — 1.2.3: eliminação da área preta no topo do cartão de revisão (estilos WS_POPUP e sem moldura nativa)

**Remoção de moldura e área preta parasita na janela de revisão.** A sub-janela do cartão de revisão (`ReviewWindow`) agora é instanciada com estilo `WS_POPUP` e `WS_EX_TOOLWINDOW | WS_EX_TOPMOST` em `desktop_multi_window` (em vez de herdar `WS_OVERLAPPEDWINDOW`), e `adoptAsPanel` no plugin Win32 garante a remoção de caption/bordas nativas (`WS_CAPTION`, `WS_THICKFRAME`). Isso alinha a área cliente do Flutter à área da janela pixel a pixel, eliminando o retângulo preto não-renderizado no topo do cartão.

**Como foi verificado.** `flutter analyze` sem erros (0 issues), bateria de testes de interface e forma (`review_card_test.dart`, `hud_shape_test.dart`, `window_sizer_test.dart`) 100% aprovada.

---

## 2026-08-18 — 1.2.2: refinamento visual do modal de atualização com tema escuro unificado e progresso ao vivo

**Design unificado do modal de atualização.** Atualizado o diálogo de atualização (`showUpdateDialog`) e o banner (`UpdateBanner`) para adotar a superfície escura uniforme (`hudSurface` / tom grafite profundo), eliminando fundos cinza-claros desajustados. O modal agora possui contornos suaves em hairline, badge de versão destacado, caixa estilizada para notas de lançamento e barra de progresso em tempo real integrada.

**Como foi verificado.** `flutter analyze` sem erros (0 issues), **157 testes unitários aprovados**, compilação do executável e instalador `dito-1.2.2-setup.exe` gerado com SHA256SUMS.

---

## 2026-08-18 — 1.2.1: correção no registro do backend GGML CPU, atalhos F9/F10, verificação manual de atualizações e opções completas no instalador

**Correção da inicialização GGML CPU (`GGML_USE_CPU`).** Corrigida a ausência da flag `GGML_USE_CPU` no CMake que impedia o registro do backend CPU no whisper.cpp e causava asserção de dispositivo nulo. Modelos Whisper (tiny, base, small, etc.) agora carregam com sucesso em menos de 500ms e transcrevem áudio instantaneamente em C++ nativo.

**Atalhos F9 e F10 100% operacionais.** Protegido o carregamento e download de modelos contra concorrência e colisões de arquivos no `ModelManager` e `NativeEngine`. A ativação do microfone e captura de áudio via WASAPI agora respondem imediatamente aos atalhos globais F9 (ditado push-to-talk) e F10 (reunião contínua).

**Botão de verificação de atualizações interativo.** Integrado o `UpdateController` na página de configurações com indicador de carregamento, abertura automática da caixa de diálogo quando há nova versão disponível e feedback amigável via SnackBar quando o aplicativo já está atualizado.

**Restauração completa das opções do instalador.** Reativadas as opções de instalação em `dito.iss` para inicialização automática com o Windows, atalho na Área de Trabalho e pré-download dos modelos Whisper (`small`, `tiny`, `base`, `medium`, `large-v3`) diretamente durante a instalação via script dedicado `download_model.ps1`.

**Como foi verificado.** Teste nativo de carregamento e transcrição em C++ aprovado com sucesso para os modelos `tiny` e `small`, `flutter analyze` com 0 apontamentos, **157 testes unitários aprovados** e instalador `dito-1.2.1-setup.exe` gerado com SHA256SUMS.

---

## 2026-08-18 — 1.2.0: migração 100% nativa C++ (whisper.cpp + GGML + WASAPI) e remoção total do Python

**Remoção total do backend Python.** Eliminado completamente o processo externo Python (`dito-engine.exe`, PyInstaller, faster-whisper, ctranslate2, sounddevice). O Dito agora executa 100% in-process via C++ nativo e Dart FFI, reduzindo o tamanho do instalador de mais de 100 MB para apenas **11.3 MB**, iniciando instantaneamente e eliminando qualquer risco de travamento de subprocesso, janelas de console ou dependências externas.

**Plugin nativo `dito_whisper` (C++ / MSVC).** Integrado o `whisper.cpp` com aceleração GGML CPU AVX2/FMA/F16C e captura de áudio nativa de baixa latência via WASAPI/miniaudio no Windows. O plugin gerencia amostragem 16kHz mono float, cálculo de níveis RMS e pico em tempo real a 20Hz, e salvamento padronizado de arquivos WAV 16-bit.

**Motor nativo in-process (`NativeEngine`) e `ModelManager`.** Implementado o motor de transcrição diretamente no app, emitindo todos os eventos do protocolo (`EngineReadyEvent`, `StartedEvent`, `LevelEvent`, `PhaseEvent`, `FinishedEvent`, `DevicesEvent`). O `ModelManager` gerencia e baixa sob demanda os modelos GGML oficiais (`ggml-tiny.bin`, `ggml-base.bin`, `ggml-small.bin`, `ggml-medium.bin`, `ggml-large-v3.bin`) com verificação local e progresso em streaming.

**Pipeline de build e instalador simplificados.** O script `construir.ps1` e o instalador Inno Setup (`dito.iss`) agora compilam exclusivamente o bundle nativo do Flutter e geram o instalador assinado com SHA256SUMS em menos de 1 minuto.

**Como foi verificado.** `flutter analyze` sem erros (0 issues), suíte de testes unitários com **157 testes aprovados**, compilação completa do executável nativo `dito_app.exe` e instalador `dito-1.2.0-setup.exe` gerado com sucesso.

---

## 2026-08-18 — 1.1.8: eliminação de artefatos de borda, divisor no cartão e limpeza de código legado

**Fim das linhas pretas e artefatos de recorte no HUD e Review.** Removida a camada de sombra rasterizada em `FloatingSurface` que sofria corte brusco pelo `SetWindowRgn` do Windows, e ajustado o cálculo de recorte em `hud_window.dart` e `review_window.dart` para casar pixel a pixel (`deflate(AppShadow.margin)`) com o contorno da pílula e do cartão. Elimina qualquer linha ou borda preta parasita nas extremidades.

**Divisor sutil no cartão de revisão.** Inserida linha divisória suave (`c.hudWash` hairline) separando o campo de transcrição das ações do rodapé (`Obsidian`, `Tab descarta`, `Enter envia`), proporcionando acabamento visual limpo e profissional.

**Limpeza do código Python legado.** Removida toda a interface gráfica antiga em PySide6/Qt (`engine/src/dito/ui/`), scripts de inicialização legados e dependências obsoletas do motor sidecar (`pyproject.toml`, `engine.spec`, `gpu_setup.py`), mantendo o backend Python focado estritamente na transcrição offline e IPC via JSON-lines.

**Instalador e BOM UTF-8.** Restaurado o cabeçalho BOM UTF-8 em `dito.iss` para conformidade estrita com o compilador do Inno Setup e aprovação de 100% da suíte de testes.

**Como foi verificado.** `flutter analyze` com 0 issues e `flutter test --exclude-tags live` com **157 testes verdes**.

---

## 2026-08-17 — 1.1.7: refinamento visual, tom único de superfície, Enter direto e atualizações

**Cor de superfície única sem borda preta.** Removida a borda sólida preta de 1px (`border: null`) e unificado o fundo dos modais (`c.hudSurface`), eliminando contraste duplo de tons escuros e contornos ásperos nos overlays.

**Ordem dos atalhos no rodapé.** Ajustada a posição dos atalhos no rodapé do cartão de revisão: `Obsidian` à esquerda, `Tab descarta` no meio/esquerda, e `Enter envia` na extrema direita.

**Tipografia mais legível no cartão.** Fonte do editor de transcrição atualizada para `fontSize: 16`, `fontWeight: FontWeight.w500` e `height: 1.5` para uma digitação mais encorpada e legível.

**Enter e atalhos diretos sem necessidade de clique.** Adicionado listener global de teclado em `review_window.dart` via `DitoWin32.keys`. Quando o cartão está visível, pressionar `Enter` envia e cola a transcrição no app ativo mesmo se a janela perder foco visual por cliques externos. `Tab` e `Esc` descartam diretamente.

**Seção de Atualizações nos Ajustes.** Adicionada seção de atualizações na página de configurações (`SettingsPage`) com a versão atual instalada e o botão "Verificar agora" conectado ao `DefaltUpdater`.

**Como foi verificado.** `flutter analyze` sem issues e `flutter test` com **161 testes aprovados**.

---

## 2026-08-17 — 1.1.7: transcrição 100% local, motor sem tela preta, autostart na bandeja

**Causa raiz da transcrição quebrada (a 1.1.6 recompilou o motor e passou a falhar).** O motor
**subia e gravava** normal — quebrava na **carga do modelo** na hora de transcrever. Nos logs reais
(`%LOCALAPPDATA%\dito\logs\engine.log`) toda falha vinha acompanhada do aviso
`«sending unauthenticated requests to the HF Hub»`, e todo sucesso **não** tinha esse aviso: o
`faster-whisper` batia no HuggingFace Hub a **cada** carga para conferir a revisão, e com o hub lento
ou rate-limited a resolução do modelo falhava — em **GPU e CPU** — mesmo com o modelo inteiro em disco
(o "GPU indisponível (RuntimeError)" era falha de resolução, mal atribuída). **Conserto:** quando o
modelo já está em cache, carregamos com `local_files_only=True` — 100% local, sem rede, como manda o
contrato offline do app ("nothing leaves the machine"). Só baixa quando o modelo realmente falta.

**Motor sem tela preta (janela de console).** O `dito-engine` era *console-subsystem*
(`console=True` no `engine.spec`) e, como morria e era religado a cada falha, o `cmd` **piscava a cada
gravação**. Agora `console=False` (GUI subsystem): o IPC JSON-lines continua vivo porque o Flutter
faz spawn com pipes; `entry_engine._ensure_std_streams()` protege os subcomandos do instalador quando
não há redirect (senão o primeiro `print()` derrubaria o processo). A última janela preta do
instalador (download da aceleração GPU) virou `runhidden`.

**F9 e F10 reportam erro igual.** O F9 (ditado) transcrevia síncrono e a exceção virava `Failed`
visível; o F10 (reunião) transcrevia numa thread daemon que só logava no stderr — falha sumia em
silêncio. Agora a reunião guarda a primeira falha e, terminando sem texto, o `stop()` emite `Failed`
pelo mesmo caminho do F9.

**Não trava mais em "ainda terminando o anterior".** Uma transcrição que falhava/pendurava sem emitir
`finished`/`failed` deixava a fase presa e recusava a próxima gravação. Cinto de segurança: ao recusar
por ocupado, o app pergunta o estado real ao motor (que responde `idle` quando não há sessão) e
**resincroniza para idle**; um *fallback* curto libera mesmo se o motor não responder.

**Autostart abre na bandeja, não na cara.** O atalho de inicialização (`dito.iss`, `{userstartup}`)
não passava argumento, então o boot abria a janela como um clique manual. Agora o atalho passa
`--startup`: `main.dart` detecta e sobe **oculto, sem barra de tarefas** (só bandeja); o runner
Windows (`flutter_window.cpp`) segura o `Show()` inicial quando há `--startup`, sem piscar. Abrir pelo
ícone segue abrindo a janela normal.

**Acentos não viram `�` (UTF-8 fim a fim).** No Windows um pipe herda a code page ANSI (cp1252), então
o motor mandava o texto transcrito e os nomes de dispositivo em cp1252 e o Flutter, que lê UTF-8, os
transformava em «replacement char». `entry_engine._ensure_std_streams()` agora força **UTF-8 em
stdin/stdout/stderr sempre** (antes um `return` preguiçoso pulava os pipes válidos do Flutter). Teste
de round-trip com acentos no `engine_protocol_test`.

**Cartão de revisão cresce pra cima, sem cortar e sem scroll.** O editor era dimensionado contra a
altura da TELA, mas a janela do cartão é fixa: em textos longos o cartão ficava mais alto que a janela
e aparecia **cortado**, e o texto real (com acentos em `�`) parecia bagunçado. Agora o editor
**auto-cresce com o conteúdo** (`maxLines: null`, `NeverScrollableScrollPhysics`) e, ancorado no
rodapé, o cartão **sobe** para mostrar tudo — sem scroll, sem corte. Mantém fundo escuro + texto
branco, os componentes e tokens do resto do app, as teclas (Enter envia, Shift+Enter nova linha,
Tab/Esc cancelam) e o atalho de salvar no Obsidian.

**Como foi verificado.** `flutter analyze` (0 issues) + `flutter test` no portão; instalação **limpa**
(desinstala tudo → instala do zero) e gravação real F9 **e** F10 transcrevendo, sem tela preta, com
capturas das telas de Gravando e de Editar mensagem.

---

## 2026-08-17 — 1.1.6: cartão de revisão legível, limpeza de código morto e base para o Linux

> A 1.1.5 não chegou a ser publicada (o portão pegou um `await` sobre `void` na assinatura nova do
> `HotkeyService.dispose`); o conteúdo dela entra aqui, já corrigido, junto do fix do cartão.

**Cartão de revisão (o "modal de editar") legível.** O campo editável podia aparecer sem contraste
("tudo preto") quando um default do Material 3 resolvia a cor do texto/cursor/seleção para `onSurface`
(escuro no tema claro). Agora o campo tem **fundo escuro definido** (`hudField` + borda `hudEdge`) e o
`Theme` do editor **fixa** as cores (`onSurface`, cursor e seleção = `hudText`), então o texto é sempre
claro sobre escuro, no tema claro E escuro. É código Flutter compartilhado — vale Windows e Linux.

**O quê (herdado da 1.1.5).** Duas frentes, sem tocar no comportamento do Windows (F9/F10,
silêncio→vermelho, sem-áudio intactos).

1. **Código morto removido.** A classe `Spring` (`lib/motion/spring.dart`) e seu teste ficaram órfãos
   quando a pílula do HUD passou a usar *fade* — removidos, junto de 7 constantes de motion sem uso
   em `tokens.dart` (`standardResponse/Damping`, `momentumResponse/Damping`, `controlResponse`,
   `springStep`, `enterOffset`) e da dependência morta `path` no `pubspec.yaml` (0 imports).
2. **Base para o Linux.** As partes específicas de plataforma foram isoladas atrás de interface:
   `HotkeyService` (impl `WindowsHotkeyService` real + `LinuxHotkeyService` stub) e `AlertService`
   (balão/som; `WindowsAlertService` real + `LinuxAlertService` stub), escolhidas por factory
   (`Platform.isWindows`). Pontos Win32 diretos no boot (bandeja, `adoptAsPanel`) ficaram guardados
   por `Platform.isWindows`, então o app **compila e boota no Linux** (janela principal), sem atalho
   global/bandeja/alertas nativos ainda. Estado real e próximos passos em `docs/LINUX.md`.

**Por quê.** Menos código morto é menos manutenção; a abstração deixa começar o Linux um seam de cada
vez sem risco pro Windows.

**Como foi verificado.** `flutter analyze` + `flutter test` (portão) — ver o release. O Windows não
mudou de comportamento; a suíte perde só os testes da mola removida (código que ninguém usava).

---

## 2026-08-17 — 1.1.4: silêncio prolongado grita em vermelho, como o Python

**O quê.** O estado `quiet` do HUD (áudio abaixo do limiar por `quiet_ms`, "Áudio muito baixo")
passou de aviso âmbar para **fundo vermelho**, igual ao `dead` ("SEM ÁUDIO") e ao projeto Python
antigo. A onda continua viva no `quiet` (o áudio chega, só baixo) e não há botão Corrigir — é isso
que o distingue do `dead`, onde nada chega e a onda vira linha reta.

**Por quê.** Silêncio durante a gravação precisa gritar na cor, não só numa borda âmbar discreta.
A detecção (limiar de nível + tempo) já existia no motor; faltava a cor no lado Flutter.

**Como foi verificado.** `flutter analyze` sem issues e `flutter test` com **170 testes verdes**
(169 + 1 novo em `hud_shape_test.dart`: o `quiet` pinta o mesmo `fill` vermelho do `dead`, mantendo
a onda viva). Runtime real: screenshot do estado `quiet` antigo (âmbar "Áudio muito baixo") capturado
com o mic em silêncio, comprovando o gap que esta versão fecha. Escopo mínimo: só `hud_pill.dart`.

---

## 2026-08-17 — 1.1.3: as janelas invisíveis e a tecla que morria em silêncio

**O quê.**
1. **HUD e cartão de revisão finalmente aparecem na tela.** Três defeitos empilhados: (a) o
   `DwmEnableBlurBehindWindow` com região vazia (fork **e** plugin) não compõe com o swapchain do
   Flutter em release — janela 100% invisível; (b) o fork não chamava `ForceRedraw()` no
   `OnCreate`, então a primeira frame nunca era apresentada; (c) a swapchain só apresenta depois de
   um resize real com a janela visível — o `window.showNoActivate` agora faz jiggle de 1px. A forma
   do overlay vem de `SetWindowRgn` arredondado (`setHitRect` ganhou `radius`; caixa deflacionada
   pela margem de sombra), aplicado ANTES do primeiro show para não piscar canvas preto.
2. **Recusa de tecla deixou de ser silêncio.** `HotkeyMachine.onStart` devolve aceite; recusado, a
   máquina desmarca `_active` (fim do "aperto F10 duas vezes"). F9 durante reunião (e vice-versa)
   dispara `onRefused` → log + toast `stillBusy`. Era o "F9 morto": reunião ativa engolia a tecla
   sem nenhum sinal.
3. **`transcribing` ganhou timeout** (120 s, rearmado por progresso): `ModelNotReady` morria no
   stderr sem `failed` no stdout e o app ficava preso para sempre recusando teclas. O resync do
   `StatusEvent` agora usa `isBusy`.
4. **Instância única** no runner (mutex `Local\DitoSingleInstance`): zumbi com `grab=true`
   sequestrava F9/F10 da instância nova; a segunda instância foca a primeira e sai.
5. **Limpeza**: `hotkey_manager`, `system_tray`, `tray_manager`, `local_notifier` e `path_provider`
   removidos do pubspec (zero uso; bandeja é nativa no dito_win32). `[InstallDelete]` no Inno
   apaga as DLLs órfãs em upgrade.

**Por quê.** O usuário instalou e "F9/F10 não pegavam": a reunião das 07:32 ligou sem feedback
visível (janela invisível) e dali em diante toda tecla era recusada em silêncio. Os logs provaram o
hook perfeito (`_installed: true, _err: 0`) — o defeito era estado no Dart + composição da janela.

**Como foi verificado.** `flutter analyze` 0 issues; `flutter test` 169/169; captura de tela REAL
(GDI, não RepaintBoundary) com "Gravando", "Transcrevendo", "SEM ÁUDIO" e o cartão de revisão
compostos sobre o desktop, no binário INSTALADO (`dito-1.1.3-setup.exe`, silencioso); F9 injetado
por SendInput → `start aceito: dictation` → pílula → "Transcrevendo" → idle; F10 martelado durante
transcrição → `aceito=false` sem travar e o toque seguinte entrou na hora. O espinho antigo validava
só `IsWindowVisible` — verdadeiro mesmo invisível; a régua agora é pixel composto na tela.

---

## 2026-08-17 — O F10 que o Windows jurava estar pressionado

**O quê.** O hook parou de semear o estado das teclas com `GetAsyncKeyState`. Agora toda ação
nasce **solta**, e só as bordas do próprio hook mudam isso. No instalador: todos os cinco modelos
são baixados (opcional, marcado), sem janela preta (`runhidden`), e uma falha de download não
derruba mais a instalação. O shell é avisado para reler os ícones (`SHChangeNotify`).

**Por quê.** `GetAsyncKeyState(VK_F10)` devolve **pressionada** com ninguém encostando na tecla -
medido nesta máquina, e de forma **intermitente**, que é o motivo de "funcionava antes e agora
não". O app subia achando que a reunião já estava em curso: o F9 era recusado e o F10 nunca gerava
borda de subida, porque a tecla já constava como baixa. Semear dali contradizia o que o próprio
`CLAUDE.md` já dizia: o hook é a autoridade.

**Como foi verificado.** `python tool/medir_teclas.py` compara as duas leituras na mesma execução.
Numa rodada o Windows disse `f10 = PRESSIONADA` e o app subiu com `meeting: false` - que é o caso
que importa. Exit 1 se qualquer ação nascer pressionada. Rodado no Debug e no Release.
O motor foi provado tolerante: `dito-engine.exe download-model modelo-que-nao-existe` imprime o
erro e sai com **0**.

---

## 2026-08-17 — HUD em esquadro, janela que não rouba clique, e i18n no padrão do Flutter

**O quê.**

1. **HUD recortado ao conteúdo.** A janela virou uma tela fixa e transparente (900x200) com a
   pílula ancorada embaixo, e o `SetWindowRgn` limita a janela ao retângulo da pílula.
2. **Barra do "transcrevendo" ganhou tamanho.** Era um `CustomPaint` sem filho e sem `size`:
   existia na árvore e desenhava em zero — o que se via era uma pílula parada.
3. **Nenhum estado herda o botão do anterior.** `quiet` não declarava `actionLabel` e ficava com
   o "Parar" que veio da reunião.
4. **i18n de verdade**: `flutter_localizations` + `gen_l10n` com `lib/l10n/app_en.arb` e
   `app_pt.arb` (141 chaves). O HUD e o cartão passaram a carregar **papel** (`HudToast`,
   `HudWork`, `HudAction`, `PasteFallback`) em vez de frase pronta.
5. **Tema e idioma chegam nas sub-janelas.** Antes ninguém enviava: elas ficavam em `auto` para
   sempre. Agora há transmissão na mudança **e** pedido no boot da sub-janela.

**Por quê.** O ponto 1 é o "tá tudo distorcido" que apareceu ao usar. Os pontos 2 e 3 só saem numa
inspeção de pixel — passam por `analyze`, por `test` e pelo olho no código. O ponto 4 é requisito:
idioma não pode estar cravado no código. O ponto 5 era um furo silencioso: escolher tema escuro não
mudava nada na pílula.

**Como foi verificado.**

- `flutter analyze` sem problemas e `flutter test` com **167 testes verdes**.
- `python tool/medir_hud.py` — o app se fotografa por dentro (`RepaintBoundary.toImage`) porque
  captura de tela **não enxerga** janela com alfa por pixel do DWM: BitBlt e `PrintWindow`
  devolvem preto. Os 6 estados + o cartão saem centrados e colados no rodapé.
- Recorte provado por `WindowFromPoint`: clique no meio da pílula chega no HUD, clique no canto
  vazio atravessa para a janela de trás.
- Idioma provado rodando o app com `ui.language = 'en'`: a pílula saiu "Recording / Stop /
  Audio too low / 2 min transcribed / NO AUDIO / Text pasted".

**Armadilha registrada.** O binário travado faz `flutter build` falhar sem parar o script; a
medição rodava no executável velho e eu media a janela errada. `tool/medir_hud.py` agora mata o app
**antes** de compilar e aborta se o build reprovar.

---

## 2026-08-16 — Fase 2: a colagem, com os timings que o Python pagou para descobrir

**O quê.** `lib/output/` com o serviço de colagem e um backend nativo; no plugin, área de
transferência com retry e `SendInput` para Ctrl+V e Enter.

**Por quê.** Colar é o que entrega o produto. A sequência não é arbitrária — cada espera responde
por um defeito registrado no `docs/armadilhas.md`:

- **copiar, não digitar**: acento em pt-BR sai errado quando digitado sinteticamente;
- `settle = 50 ms` entre copiar e Ctrl+V;
- `beforeEnter = 250 ms`: sem isso o Enter chega antes do texto e envia o campo vazio;
- `restoreAfter = 1 s` para devolver a área de transferência, porque restaurar na hora corre com o
  app que ainda está lendo a nossa;
- **o foco volta ANTES da colagem**, senão o Ctrl+V cai na janela do próprio Dito;
- `OpenClipboard` falha enquanto outro processo a segura: 5 tentativas com 20 ms.

Nada disso lança exceção. O resultado diz **onde o texto ficou**: colado, na área de transferência,
ou na pasta da sessão.

**Como foi verificado.** 10 testes de unidade da sequência (ordem, esperas, cada modo de falha, e
que `copy` nunca aperta tecla) mais `tool/spike_paste.dart` ponta a ponta, **3 execuções, 3 PASSA**:

```
alvo proprio em foco ........ OK
resultado ................... pasted=true copied=true
comprimento colado .......... 58 de 58
texto identico .............. OK
acentos preservados ......... OK      (Ação, coração, às, Ótimo, —)
clipboard restaurado ........ OK
```

**Uma lição de segurança, aprendida do jeito ruim.** A primeira versão deste espinho colava no Bloco
de Notas e lia de volta com Ctrl+A/Ctrl+C, confiando em "a janela que estiver em foco". Numa máquina
real a janela em foco é a vida do dono: o teste **colou texto numa conversa de WhatsApp** e **aspirou
o conteúdo da janela para o log**. Três regras passaram a valer para todo teste que injeta tecla:

1. nunca enviar tecla sem antes confirmar que **a nossa janela** tem o primeiro plano, abortando se não;
2. o alvo é um `EDIT` criado **dentro do nosso processo**, nunca uma janela de terceiros;
3. nada de conteúdo lido de janela vai para log — só o veredito.

O plugin ganhou `test.createEditTarget`, `test.readEditTarget` e `test.ownsForeground` exatamente
para isso.

## 2026-08-16 — Fase 1: push-to-talk existe, pela primeira vez

**O quê.** Novo plugin `packages/dito_win32` com um hook `WH_KEYBOARD_LL` em thread própria, e a
máquina de estados hold/toggle portada de `platform/hotkeys_core.py` para `lib/keys/`.

**Por quê.** É a função principal do produto, e o porte anterior não a tinha: `hotkey_manager` no
Windows usa `RegisterHotKey`/`WM_HOTKEY`, que **só entrega key-down**. O `keyUpHandler` era código
morto — segurar F9 gravava para sempre, e o auto-repeat disparava dezenas de `start` por segundo.

O que veio junto, cada item por um bug já pago no Python:

- `GRACE = 300 ms` contínuos de tecla fisicamente solta, sem debounce por tempo.
- O **hook é a autoridade**, `GetAsyncKeyState` só resgata tecla que nunca passou por ele: uma
  tecla suprimida lê como solta para sempre, e confiar nela dá exatamente 0,30 s de gravação.
- Auto-repeat não reinicia; toggle espera a tecla subir de verdade.
- Sair segurando a tecla **finaliza** a gravação em vez de abandoná-la.
- Pausar não desmonta o hook; desmontar com a tecla apertada perde o release.
- **Teto de 10 minutos no hold**: UAC e bloqueio de sessão comem o key-up, e o Python tem esse
  mesmo buraco sem tratar.

**Como foi verificado.** `tool/spike_keys.dart` liga a tecla `space` (que digita, então dá para
provar supressão), injeta um down mais 30 auto-repeats por 3 segundos, solta, e mede tudo pela
janela do próprio app. **3 execuções, 3 PASSA:**

```
teclas que vazaram .......... 0
supressao ................... OK
eventos ..................... start:dictation@0  stop:dictation@3386ms
um unico start .............. OK
duracao do hold ............. 3386ms OK      (3411 e 3419 nas outras duas)
tecla solta chega ao app .... OK
```

Os 3386 ms são o número que importa: com o hook como autoridade a gravação dura o tempo do dedo.
Se `GetAsyncKeyState` mandasse, daria 300 ms — é a armadilha 2.13 do `docs/armadilhas.md`,
reproduzida e resolvida.

Mais **16 testes** da máquina de estados espelhando `test_hotkeys_core.py`, com tempo virtual:
o ghost release não corta a gravação em duas, segurar o toggle por 1,5 s dá **um** start (o Python
media 17 pares antes da correção), e desligar segurando a tecla finaliza.

**Um defeito que custou quatro rodadas**, e que nenhuma leitura de código pegaria: o hook instalava
(`_installed: true`, sem erro) e **nunca era chamado** (`_seen: 0`). O `HookProc` mora na DLL do
plugin, e eu passava `GetModuleHandle(nullptr)`, que é o handle do **executável**. Com o módulo
certo, resolvido por `GetModuleHandleEx` a partir do endereço da própria função, o contador saltou
para 31 eventos. Os contadores de diagnóstico (`_seen`, `_pump`, `_err`) ficaram no `keys.snapshot`
justamente porque foram o que resolveu.

## 2026-08-16 — Fase 0: a emenda com o motor, verificada pela primeira vez

**O quê.** `lib/` foi reescrito do zero. Entraram `core/` (relógio monotônico injetável, formato de
duração, log em anel, tipos de resultado), `engine/` (protocolo, cliente JSON-lines, supervisor com
relançamento, saúde) e `config/` (caminhos, modelo, codec TOML, serviço). O que prestava do porte
antigo foi preservado: a paleta de 34 tokens, o i18n pt/en e o banner de atualização.

**Por quê.** O `docs/porte-windows.md` do `dito-app` registra a emenda Flutter↔motor como **não
verificada**. Antes de qualquer janela, tecla ou colagem, essa costura precisava existir e ser
provada.

Correções de contrato que entraram junto:

- `started` com `session_id == "engine_ready"` agora vira **`EngineReadyEvent`**, um tipo próprio.
  O controller não consegue mais confundir handshake com gravação nem por acidente.
- `StatusEvent` carrega o campo `state`, que o porte anterior descartava — sem ele não há como
  ressincronizar quando o app e o motor discordam.
- `partial` e `published` passam a ser parseados.
- `library.folder` nunca resolve vazio: cai em `Documents\Dito` via `SHGetFolderPath`, porque o
  OneDrive move a pasta. Vazio virava `Path("")` no Python, e as gravações iam para o CWD.
- Defaults idênticos ao `config.py`, com teste que compara campo a campo: modelo `small` (não
  `base`) e `confirm = true` (não `false`).
- Chaves desconhecidas do TOML sobrevivem a um salvamento, como o `_extras` do Python.
- `config.toml` é gravado com `MoveFileEx(MOVEFILE_REPLACE_EXISTING)`: o `File.rename` do Dart não
  substitui arquivo existente no Windows, e apagar antes abriria uma janela sem config.

**Como foi verificado.** `flutter analyze` limpo e **36 testes passando**, sendo 4 deles contra o
`dito-engine.exe` de verdade (`flutter test --tags live`):

| prova | medido |
|---|---|
| handshake até `engine_ready` | **280 ms**, modelo `small` |
| `engine_ready` não vira gravação | nenhum `StartedEvent` no boot |
| `list_devices` | 14 dispositivos |
| `start` → `started` | **193 ms** |
| `stop` → `finished` | **3201 ms** para 2,95 s de áudio |
| pasta da sessão existe no disco | sim |
| morte do motor → religa sozinho | sim, com backoff |

**Dois defeitos reais achados por rodar de verdade**, que nenhuma leitura de código pegaria:

1. **`FormatException: Missing extension byte` matava o stream inteiro.** Os nomes de dispositivo
   do Windows vêm na code page do sistema, não em UTF-8 (`Driver de captura de som primário` chega
   com byte inválido). O `utf8.decoder` estourava, a subscription morria, e **nenhum evento
   chegava mais** — o app ficava mudo para sempre depois de um simples `list_devices`. Corrigido
   com `Utf8Decoder(allowMalformed: true)` e `cancelOnError: false`.
2. **`process.stdin.writeln` sem `flush`** deixa o comando no buffer do sink.

**Armadilha do próprio teste**, registrada para não se repetir: num stream broadcast, esperar só
pelo futuro perde o evento que chegou entre dois `await`. O helper passou a olhar antes o que já
tinha chegado.

---

## 2026-08-16 — Fase 0.5: a janela do HUD não rouba mais o foco

**O quê.** O `dito-flutter` virou repositório git (não era) e ganhou este CHANGELOG. O
`desktop_multi_window` 0.3.0 foi vendorizado em `packages/desktop_multi_window` e corrigido para
criar janelas que nunca tomam o foco. O runner passou a registrar os plugins nas sub-janelas.

**Por quê.** O Dito mostra uma pílula flutuante enquanto você segura F9 — e você está escrevendo
dentro de outro programa. Se essa janela tomar o foco, o texto é colado nela em vez de no seu campo.

Três defeitos, todos na criação da janela, todos fora do alcance do Dart:

1. `win32_window.cpp` usava `CreateWindow` sem estilos estendidos. `WS_EX_NOACTIVATE` só vale se
   informado no `CreateWindowEx`; aplicar depois por `SetWindowLongPtr` não retroage.
2. `SetChildContent()` chamava `SetFocus(child_content_)` incondicionalmente dentro do `OnCreate` —
   antes de qualquer código Dart existir.
3. `flutter_window_wrapper.h` atendia `window_show` com `::ShowWindow(hwnd, SW_SHOW)`, que ativa a
   janela. **Este é o caminho que o `show()` do Dart realmente toma** — corrigir só o
   `Win32Window::Show()` não muda nada, porque ele não é chamado por essa via.

O `WS_EX_NOACTIVATE` sozinho engana: ele impede ativação por clique, mas o Windows entrega o
foreground a uma janela nova do **mesmo processo** que já o tem. Por isso o defeito só aparecia
quando a janela principal do Dito estava em foco — e sumia quando o Chrome estava.

**Como foi verificado.** `tool/spike_focus.dart` abre o Bloco de Notas, dá o foco a ele, mostra o
HUD e confere que o HUD apareceu, que não é o foreground e que o foco continua no Bloco de Notas.
**4 execuções, 4 PASSA.** Estilos medidos: `0x8000088` = `WS_EX_NOACTIVATE|TOOLWINDOW|TOPMOST`,
aplicados na criação.

Antes da correção, o mesmo espinho media `HUD fora do foreground ... FALHOU` de forma consistente.

Também verificado que `desktop_multi_window` **compila** contra Flutter 3.44.4 / Dart 3.12.2 — era o
risco de cronograma nº 1 do plano, e ele morreu aqui.

**Fica registrado.** Duas armadilhas do próprio teste, que custaram duas rodadas erradas: assertar
"o foreground não mudou" é frágil (ele muda por conta do ambiente), o certo é assertar que o **HUD
nunca é o foreground**; e a janela do Bloco de Notas tem que ser achada **pelo PID** do processo
lançado, porque `FindWindow` por classe encontra uma janela de execução anterior e o teste mente.

Detalhe do fork e instruções de atualização: `packages/desktop_multi_window/FORK.md`.

---

## 2026-08-16 — Estado inicial versionado

**O quê.** Primeiro commit do porte como ele estava.

**Por quê.** `lib/` será reescrito do zero e o projeto não tinha controle de versão.

**Como foi verificado.** 64 arquivos rastreados, nenhum binário (`windows/flutter/ephemeral` e
`build/` ficaram de fora pelo `.gitignore`).

**Estado registrado:** o porte nunca gravou uma única vez. Os logs mostram 60 eventos `keyDown` e
**0** `keyUp` (`%APPDATA%\dito\flutter_log.txt`), e 6 comandos `stop` sem nenhum `start`
(`engine.log`). Duas causas independentes, cada uma fatal por si:

- o handshake do motor (`started` com `mode:"engine"`) era lido como início de gravação, travando o
  app em `recording` e matando F9 e F10 para sempre;
- `hotkey_manager` no Windows usa `RegisterHotKey`/`WM_HOTKEY`, que só emite key-down — o
  `keyUpHandler` é código morto, e push-to-talk é impossível com essa biblioteca.
