# Armadilhas — o que já custou caro neste projeto

Cada item aqui é um defeito **que aconteceu de verdade**, com o sintoma que o dono viu, a causa
provada e a regra que impede a reincidência. Herdeiro direto do `docs/armadilhas.md` do Dito em
Python: aquele arquivo existia, o port não o trouxe, e metade dos defeitos de 2026-08-21 foi
reaprender o que ele já sabia.

Regra de uso: **antes de mexer em áudio, teclas globais ou janelas no Linux, leia a seção
correspondente.** Ao pagar uma armadilha nova, acrescente-a aqui no mesmo formato.

---

## 1. Áudio

### 1.1 Nunca fazer trabalho pesado dentro do callback de áudio
**Sintoma:** áudio gravado com picos isolados e o resto zerado; `pipewire-pulse: [com.defalt.dito_app]
overrun recover ... skip:4082` no journal; Whisper transcrevendo vazio.
**Causa:** o callback do driver escrevia o WAV em disco, dava `flush()` uma vez por segundo, convertia
float→int16, crescia um `std::vector` sem `reserve()` e ainda segurava o mesmo mutex do medidor de
nível de 20 Hz. No backend PulseAudio, `pa_stream_drop()` — o "já consumi" que o servidor espera — só
é chamado **depois** que o callback retorna (`miniaudio.h:31757-31771`); callback preso = servidor sem
ack = buffer cheio = amostras descartadas.
**Por que o Windows não sofria:** no WASAPI o miniaudio eleva a thread a "Pro Audio" via MMCSS
(`miniaudio.h:24546`); no caminho PulseAudio não há elevação nenhuma (`miniaudio.h:43909-43912`).
**Regra:** o callback **só copia para um ring pré-alocado e mede nível em atômicos**. Disco,
conversão e crescimento de buffer vivem na thread consumidora. O Dito em Python já dizia, em
`src/dito/audio/capture.py:58`: *"Realtime thread: slow work here drops blocks."*

### 1.2 Definir o tamanho do período explicitamente
**Sintoma:** mais sensível a qualquer atraso; overrun com o sistema sob carga.
**Causa:** `ma_device_config_init` deixa `periodSizeInMilliseconds = 0`, e o default do miniaudio é
`low_latency` = 10 ms × 3 períodos (`miniaudio.h:12217-12222`). O Python fixava **50 ms**
(`BLOCKSIZE = 800`) por decisão consciente, comentada no código.
**Regra:** sempre setar `periodSizeInMilliseconds = 50`, `periods = 4` e
`performanceProfile = ma_performance_profile_conservative`. Latência não é requisito aqui; não perder
amostra é.

### 1.3 Nunca abrir o dispositivo ALSA cru
**Sintoma (herdado do Python, seções 1.7 e 1.12 do arquivo antigo):** gravação que sai em ruído de
fundo, porque o "default" do ALSA é o card 0 — a entrada analógica da placa-mãe, sem nada plugado.
Nesta máquina os `hw:` locais **rejeitam 16 kHz** (`PaErrorCode -9997`).
**Regra:** `ma_context_init` pede **PulseAudio/JACK explicitamente**; ALSA só como último recurso e
**sempre com aviso no log**. Quem sabe qual é o microfone do dono é o servidor de som.

### 1.4 Registrar o dispositivo e a taxa realmente abertos
**Sintoma:** "o mic parou de captar" sem nenhuma forma de saber se o app abriu o headset, a placa-mãe
ou um monitor de saída.
**Regra:** toda captura loga `backend`, nome do device, taxa pedida × taxa real, formato e período.
Sem isso, um episódio de áudio ruim vira palavra contra palavra — foi o que fez o defeito durar um
dia inteiro.

### 1.5 Uma fonte `.monitor` grava a saída, não a voz
**Sintoma:** gravação em silêncio ou com o áudio do YouTube em vez da fala.
**Regra:** ao listar/escolher dispositivos, tratar `.monitor` como caso especial e nunca deixá-lo
virar padrão silenciosamente.

### 1.6 Alarme de silêncio precisa de histerese e de aquecimento por TEMPO
**Sintoma:** triângulo vermelho piscando (`dead`→`quiet`→`dead`, 5 trocas em menos de 1 s) e alarme
disparando com o dono já falando.
**Causa:** o estado trocava a cada tick de 50 ms conforme o RMS cruzava `deadRms`, sem banda de
histerese; e o aquecimento era medido em **amostras** (800), então um bloco maior do driver liberava o
gate no primeiro instante, com o sinal ainda subindo.
**Regra:** trocar de estado só depois de N ticks consecutivos concordando, e medir aquecimento em
tempo real (1,2 s), nunca em contagem de amostras.

---

## 2. Teclas globais (Linux/X11)

### 2.1 Um hook por PROCESSO, nunca por janela
**Sintoma:** F9/F10 funcionavam uma vez e depois ficavam mudos; só voltavam fechando e abrindo o app;
o snapshot dizia `grab: true` enquanto o contador de eventos ficava congelado.
**Causa:** o plugin é registrado **uma vez por janela** (principal + HUD + revisão) e cada registro
abria seu próprio `XOpenDisplay` — conexões distintas são **clientes X distintos**, e `XGrabKey` é
exclusivo. As três janelas do mesmo Dito brigavam pela tecla; quando o vencedor era o HUD ou a
revisão, o evento ia para um engine que ninguém escutava.
**Regra:** estado do teclado e thread X11 são **singletons do processo**; os eventos são transmitidos
a todas as janelas registradas. Nunca criar um `PluginState` por registrar.

### 2.2 `XGrabKey` falha em silêncio
**Sintoma:** app surdo achando que tinha a tecla.
**Causa:** `BadAccess` chega pelo handler de erro do X, e o handler descartava tudo; `keys.bind`
respondia `TRUE` fixo.
**Regra:** contar erros do X em volta do grab (`XSync` + contador), devolver o resultado real ao Dart,
**avisar o dono na tela** e re-tentar periodicamente — a tecla pode ser liberada por quem a tomou.

### 2.3 Instância única não é detalhe de conforto
**Sintoma:** vários Ditos abertos, e a tecla indo para o processo errado.
**Causa:** `G_APPLICATION_NON_UNIQUE` no runner GTK, enquanto o Windows sempre teve mutex +
`FindWindow`.
**Regra:** o segundo lançamento **foca a janela existente e sai**. Com `XGrabKey` exclusivo, duas
instâncias significam uma surda.

---

## 3. Máquina de estado da gravação

### 3.1 Desistir do start sem avisar o motor cria gravação fantasma
**Sintoma:** a fase travava em `recording`/`meeting` e toda tecla seguinte era recusada, para sempre.
**Causa:** o timeout de 5 s devolvia a fase para `idle` **sem mandar `StopCommand`**; a tecla era
solta sem parar nada; o `StartedEvent` atrasado chegava e cravava a fase de volta, sem ninguém para
encerrá-la.
**Regra:** todo caminho de desistência manda `StopCommand`, e uma sessão que chega depois de
abandonada é **encerrada, não adotada**.

### 3.2 Evento de sessão antiga não pode mexer na sessão do ar
**Sintoma:** o cartão de revisão com o texto da sessão errada; a pílula da gravação nova sumindo.
**Regra:** comparar `sessionId` antes de tocar em fase, watchdog, HUD ou revisão. Proteger a sessão
nova tanto **gravando** quanto **transcrevendo** — proteger só o primeiro caso foi o furo do 1.4.5.

### 3.3 `Isolate.spawn` sem `onExit`/`onError` trava para sempre
**Sintoma:** transcrição que nunca termina e app preso.
**Regra:** todo isolate declara `onExit` e `onError`, e a morte falha as chamadas em voo em vez de
deixá-las penduradas.

---

## 4. Janelas e HUD

### 4.1 Timer de saída precisa ser cancelado por qualquer estado visível
**Sintoma:** a pílula "gravando" aparecia e sumia sozinha; ficava invisível pelo resto da sessão.
**Causa:** `dismiss()` armava um timer de 180 ms que forçava `hidden` incondicionalmente, e nenhum
outro estado o cancelava.
**Regra:** todo estado visível cancela a saída pendente; e o nível de áudio (que só existe com o
motor capturando) religa a pílula se ela estiver escondida.

### 4.3 Nunca desmapear a sub-janela para escondê-la (Linux/X11)
**Sintoma:** o HUD "gravando" **nunca** aparecia no Linux. A janela existia, o Dart dentro dela
rodava e calculava o estado certo, mas o X reportava `IsUnMapped` — e nem `xdotool windowmap`
conseguia mapeá-la. No boot saía `Failed to setup compositor shaders, unable to make OpenGL context
current`, duas vezes (uma por sub-janela).
**Causa:** esconder chamava `hide` de verdade (desmapeava). Nesta pilha (NVIDIA/GLX + visual RGBA), a
sub-janela desmapeada perde o contexto GL do `FlView` e **não volta**: todo `show` seguinte retorna
sucesso sem mapear nada, e a flag `_visible` do Dart passa a mentir para sempre.
**Regra:** a sub-janela sobe uma vez e **fica**. Esconder é recortar a forma para uma região vazia
(`gtk_widget_shape_combine_region` com `cairo_region_create()`); mostrar é recortar de volta para a
forma da pílula. Além disso, o `show` é **idempotente** — chamar sempre que o estado pedir, sem
confiar em flag. Com isso o visual RGBA (transparência) volta a funcionar.
**Não adianta:** recortar a `GdkWindow` filha do Flutter (apaga o conteúdo inteiro), nem realizar a
janela antes da view, nem trocar o backend GL — testados, nenhum resolve.

### 4.4 Sub-janela precisa nascer MAPEADA, e quanto menos sub-janelas, melhor
**Sintoma:** o cartão de revisão (e às vezes o HUD) nascia morto: a janela existia com o tamanho de
fábrica (560x180), o Dart dentro dela nunca rodava, e o que ficava na tela era um quadro congelado
que não respondia a clique nenhum. Intermitente entre boots. No log, sempre:
`Failed to setup compositor shaders, unable to make OpenGL context current` — **uma vez por
sub-janela**.
**Causa:** o `FlView` da sub-janela só consegue contexto GL sobre uma janela **realmente mapeada**.
Criar a view com a janela apenas realizada (`gtk_widget_realize`) não basta.
**Regra:** a sub-janela é mostrada (`gtk_widget_show_all`) **antes** de a view ser criada, já com
recorte vazio para nascer invisível, e o loop de eventos é drenado antes de seguir. E: **uma
sub-janela só** — a pílula e os cartões vivem na mesma, porque cada sub-janela extra é mais uma
chance de nascer morta.
**Não adianta:** atrasar a criação (piora), esperar `endOfFrame` (piora), `LIBGL_ALWAYS_SOFTWARE`,
`GDK_GL=gles`, `glx-legacy`, criar sem foco, nem inverter a ordem — todos testados em 2026-08-21/22.

### 4.6 `accept_focus=FALSE` no X11 é definitivo, ao contrário do Windows
**Sintoma:** o cartão de revisão aparecia, o cursor piscava no campo de texto, mas **o Enter ia para
a janela de trás** (o terminal). Clicar no cartão também não adiantava. O dono descreveu como "é como
se nunca tivesse selecionado a janela".
**Causa:** `adoptAsHud()` (chamado incondicionalmente em `hud_window.dart` quando a sobreposição
sobe) executa `gtk_window_set_accept_focus(FALSE)`, que grava `WM_HINTS.input = False`. Para o
Mutter/Muffin isso não é preferência: é **incapacidade estrutural**. O WM passa a recusar foco a essa
janela para sempre — nem `_NET_ACTIVE_WINDOW` nem `XSetInputFocus` contornam, porque o WM devolve o
foco na interação seguinte. E não existia nenhuma chamada que voltasse o hint para `TRUE`.
**Por que o Windows não sofre:** lá o equivalente é `WS_EX_NOACTIVATE`, que é **fraco** — só suprime
ativação automática; um `SetForegroundWindow` explícito ainda funciona. A tradução 1:1 do port
mudou a semântica sem que ninguém percebesse.
**Regra:** o hint acompanha o estado — `setFocusable(true)` **antes** de pedir foco para o cartão, e
`setFocusable(false)` quando resta só a pílula. E o `FlView` da sub-janela precisa de
`gtk_widget_grab_focus` na criação (o runner principal faz; o fork não fazia), senão o teclado não
chega ao motor mesmo com a janela focada.

### 4.7 Nunca sintetizar tecla com subprocesso síncrono
**Sintoma:** a interface congelava a cada Ctrl+V e a cada Enter enviados pelo app.
**Causa:** `RunXdotoolKey` usava `g_spawn_sync` — fork + exec + espera do `xdotool` **na thread do
GTK**, 20–150 ms por tecla, com a interface inteira parada no meio.
**Regra:** XTEST direto (`XTestFakeKeyEvent` via `libXtst`), que é uma chamada de biblioteca e não
um processo. O `xdotool` fica só como último recurso, com aviso no log.

### 4.8 Recorte de forma VAZIO não faz o compositor repintar a área liberada
**Sintoma:** depois de descartar (Tab) ou enviar (Enter), a pílula ficava desenhada na tela e não
saía. Parecia interface travada, e um F9 novo "destravava" — porque redesenhava naquela área.
**Causa:** o app estava certo (o log registra o descarte e a região de clique zera no tempo). O que
sobrava eram pixels que o Muffin nunca repintava. Medido: com a região de clique vazia há 2,5 s,
**100% dos pixels da pílula continuavam idênticos**, e um `xrefresh` os limpava.
`gtk_widget_shape_combine_region` com região **vazia** não gera a repintura da área liberada.
**Regra:** havendo compositor (`gdk_screen_is_composited`), esconder é **`_NET_WM_WINDOW_OPACITY = 0`**
e recorte de *input* vazio (para o clique passar) — a forma **nunca** fica vazia. Sem compositor,
forma vazia continua valendo. Medição A/B: 20/20 com fantasma antes, 0/20 depois.
**Não adianta:** `gtk_widget_set_opacity` (no GTK3 não grava a propriedade que o WM lê — usar
`XChangeProperty`); e, num fantasma **já assentado**, nem opacidade, nem mover, nem redimensionar
limpam — o remédio só funciona aplicado **junto** com a mudança de forma.

### 4.9 A sobreposição nasce `NORMAL` se ninguém disser o contrário
**Sintoma:** nenhum visível de imediato — é custo estrutural. `xprop` mostrava
`_NET_WM_WINDOW_TYPE_NORMAL` numa janela 900×900 sempre-no-topo.
**Causa:** `gtk_window_new(GTK_WINDOW_TOPLEVEL)` sem `gtk_window_set_type_hint`. `NORMAL` é a
categoria EWMH com o tratamento de foco e empilhamento mais pesado — o oposto do indicado.
**Regra:** `GDK_WINDOW_TYPE_HINT_UTILITY`, **nunca** `NOTIFICATION` nem `DOCK` (a sobreposição
precisa de foco quando há cartão — ver 4.6), e **antes** do `show_all`, porque hint aplicado depois
não retroage. Não usar `transient_for` junto.
**Cuidado ao aplicar:** o bloco `if (!focusable)` do fork **não roda** para esta janela — ela é
criada com `focusable: true` (`boot.dart`). Colocar o hint lá dentro é um conserto que nunca executa.

### 4.10 Corrigir o caminho de ESCONDER não corrige o de NASCER
**Sintoma:** abrir o Dito e a janela ficar em "Iniciando…" até um F9; **a imagem do monitor inteiro
congelar**; arrastar uma janela e o rastro dela ficar parado. Sempre no monitor onde o Dito abre.
**Causa:** a 4.8 foi corrigida só no `hudShape` (esconder). A **criação** da sobreposição
(`desktop_multi_window_plugin.cc`) continuava fazendo `gtk_widget_shape_combine_region(win, vazio)`
logo depois do `show_all` — uma janela 900×900 `ABOVE`, **mapeada**, com forma **vazia**, parada
sobre o monitor primário desde o boot até o primeiro F9. O Muffin para de repintar aquela área, e o
que congela não é o app: é o compositor. Um app não consegue congelar o rastro de *outras* janelas.
**Regra:** o estado "escondido" tem **um** lugar de verdade e vale desde o nascimento — forma
**nunca vazia** (1 px basta), recorte de clique vazio e `_NET_WM_WINDOW_OPACITY = 0`. Ao pagar uma
armadilha num caminho, procure o **outro caminho que produz o mesmo estado**.
**Medição A/B:** com `DITO_HUD_HOLD=1` (a sobreposição desenha no boot) o defeito sumia — 6/20
aberturas congeladas sem, 0/20 com. Foi isso que apontou a sobreposição. Depois do conserto,
**0/25** sem HUD nenhum.
**Falso alarme registrado:** o `input shape` da ociosa aparece como 900×900 cheio numa consulta X,
o que sugere roubo de clique. **Não rouba** — 0/20 amostras no centro dela. A consulta cai no frame
do WM, não na janela que recebe evento.

### 4.2 Canal entre janelas é fire-and-forget: não confie só na transição
**Sintoma:** sub-janela dessincronizada quando uma mensagem se perde.
**Regra:** além de empurrar transições, a sub-janela **pergunta o estado atual** ao dono no boot
(mesmo padrão já usado para tema e idioma), e chamadas nativas de mostrar/esconder são serializadas,
com a flag de visibilidade seguindo o resultado real.

---

## 5. Método

### 5.1 Sem log, não há causa raiz — há opinião
O alarme de "sem áudio" não era registrado em lugar nenhum; o nível medido tampouco; o backend de
áudio idem. Um defeito de um dia inteiro se resolveu quando os números passaram a existir.
**Regra:** todo caminho de falha registra o número que o sustenta.

### 5.2 Hipótese boa não é causa provada
A suspensão do microfone pelo WirePlumber explicava tudo — e os dados do dono a derrubaram
(gravações após 25 s, 43 s e 290 s parado saíram ótimas). O mesmo com "áudio esburacado por
descarte": a análise forense mostrou buracos aperiódicos presentes também nas gravações boas.
**Regra:** antes de corrigir, **reproduzir e medir**. Comparar o app com uma gravação externa
simultânea (`pw-record`) é o teste que separa "o app perde áudio" de "o sistema entrega ruim".

### 5.3 Instrumento sem controle mente com cara de dado
Em 2026-08-22, três medições minhas deram resposta errada e quase mandaram uma correção para o lugar
errado: (a) "encolher o canvas de 900×900 resolve a lentidão" — era artefato, a pílula saía para fora
da janela encolhida e não havia frame nenhum; (b) "o toast some certo" — media 0,8 s depois de
esconder, momento errado; com a régua certa a base era 20/20 determinística; (c) "a janela principal
nasce morta em 3/3" — a sonda era redimensionar e olhar pixel, e o **`xed`, que está vivo, deu o
mesmo resultado**.
**Regra:** toda sonda nova passa por um **controle conhecido** antes de valer como prova, e toda
conclusão de uma única medição é repetida antes de virar correção.

### 5.4 Critério vermelho não prova culpa da mudança: alterne os binários
Em 2026-08-22, na 1.6.4, o portão acusou `abre com conteudo: 5/5 congeladas` logo na primeira rodada
depois de uma mudança que **só mexe em áudio**. A leitura óbvia — "quebrei" — estava errada. O que
resolveu foi guardar os **dois bundles** e alternar sem reconstruir: com a mudança deu 2 falhas em 4;
**sem** a mudança deu 1 falha em 3. Duas rodadas com o **mesmo binário** deram 0/5 e 5/5.
**Regra:** antes de atribuir uma falha do portão à sua mudança, rode o portão inteiro no binário
**anterior**, na mesma sequência. `cp -r build/linux/x64/release/bundle` guarda um bundle inteiro e
o `BIN` do `regressao.py` aceita ser trocado por fora — não precisa reconstruir para comparar.
Vale para os **três** critérios que hoje oscilam: `abre com conteudo`, `sem pixel fantasma` e
`cartao aparece` — este último deu 1/6 e, na rodada seguinte **com o binário idêntico**, 0/6.

### 5.5 A fala de teste do portão mora no repo, não na biblioteca
`tool/regressao.py` e `tool/repro_ditado.py` injetam `tool/fixtures/fala.wav` no microfone virtual.
Ela ficava dentro de `~/Documentos/Dito`, e desde a 1.6.4 **o app não gera mais WAV** — apagar aquele
arquivo era perder a entrada do portão sem como refazê-la. Se ela sumir, a única forma de gerar outra
é rodar o app com `DITO_SALVAR_WAV=1` e ditar.

---

## 6. Port Windows → Linux

### 6.2 Inverter um padrão de linha de comando exige mexer nos DOIS lados
**Sintoma:** a janela principal aparecia no boot e fechava sozinha um instante depois.
**Causa:** o runner nativo (`linux/runner/my_application.cc`) e o Dart (`lib/main.dart`) leem **o
mesmo vetor** de argumentos — `dart_entrypoint_arguments = argv + 1` — mas cada um tinha a sua
regra. A 1.6.3 inverteu o padrão do Linux ("sem argumento sobe escondido") só no Dart; o runner
continuou com a lista do Windows (`--startup`, `--minimized`, `--tray`, `listen`, `--hidden`). Sem
argumento, o runner concluía "mostrar" e o Dart, "esconder": um mostrava, o outro escondia.
**Regra:** padrão de inicialização é **uma** decisão. Ao mudá-la, procure todo lugar que lê `argv` —
no mínimo o runner de cada plataforma e o `main()` do Dart — e mude juntos. Sintoma clássico dessa
divergência: algo que **aparece e desaparece sozinho**, em vez de simplesmente não aparecer.

### 6.1 Separador de caminho cravado fora de ramo de plataforma
**Sintoma:** a biblioteca nunca achava o áudio das gravações (`hasAudio` sempre falso, duração pelo
tamanho do arquivo nunca calculada) e "salvar no Obsidian" não gravava nada.
**Causa:** `'$dir\\$nome'` cravado em `library_reader.dart` e em `_saveToVault`, **fora** de qualquer
`if (Platform.isWindows)`. No Linux a barra invertida é caractere de NOME, não separador: o caminho
procurado vira `.../07-42-13\07-42-13.wav`, que nunca existe. Falha 100% silenciosa — nenhum erro,
só um `existsSync()` falso para sempre.
**Regra:** construir caminho com `Platform.pathSeparator` (ou dentro de ramo de plataforma explícito,
como `lib/config/paths.dart` faz corretamente). **Interpretar** caminho é outra coisa: `RegExp(r'[\\/]')`
aceitando os dois separadores está certo e não deve ser mexido.
**Como caçar:** `grep -rn '\\\\' lib/` e conferir, um a um, se está dentro de ramo Windows ou dentro
de uma regex de parsing.

### 6.3 `Ctrl+V` em terminal Linux não é colar — é caractere de controle (`0x16` / `lnext`)
**Sintoma:** ao ditar no terminal (ex.: CLI do Antigravity `agy`, `bash`, `zsh`), o texto **não era colado**,
um `Enter` vazio era enviado em seguida e 1 segundo depois o texto sumia do clipboard.
**Causa:** no Windows, o subsistema de console e o Windows Terminal aceitam `Ctrl+V` para colar. No Linux,
emuladores de terminal (`gnome-terminal`, `xterm`, `alacritty`, `kitty`, `konsole`, etc.) interpretam
`Ctrl+V` como o caractere `0x16` (SYN / *literal-next* do termios). O atalho universal de colar no
terminal Linux é **`Ctrl+Shift+V`**.
**Regra:** no Linux (`dito_win32_plugin.cc`), inspecionar a propriedade `WM_CLASS` da janela ativa no X11
via `XGetClassHint`. Se pertencer a uma classe de terminal, sintetizar **`Ctrl+Shift+V`**; para todas as
demais janelas normais (WhatsApp, Discord, navegadores, editores GUI), sintetizar **`Ctrl+V`**.

### 6.4 Traduzir a intenção semântica, nunca a chamada de API literal
**Sintoma:** dias inteiros gastos tentando fazer o porte funcionar no Linux enquanto no Windows funcionava.
**Causa:** tradução 1:1 de APIs do Windows para Linux sem considerar a semântica de baixo nível dos sistemas:
| Conceito | No Windows | No Linux (erro 1:1) | Consequência | Correção correta |
|---|---|---|---|---|
| **"Não roubar foco"** | `WS_EX_NOACTIVATE` *(fraco)* | `gtk_window_set_accept_focus(FALSE)` *(permanente no X11)* | O Window Manager recusava foco para sempre; o Enter ia para a janela de trás | `window.setFocusable(bool)` dinâmico |
| **Hook de teclado** | `WH_KEYBOARD_LL` *(global)* | `XGrabKey` *(exclusivo por conexão X)* | 3 janelas do Dito brigando pelo F9; a janela sem listener vencia e o app ficava mudo | Singleton: 1 thread X11 no processo |
| **Injetar tecla** | `SendInput` *(sistema)* | `g_spawn_sync("xdotool ...")` *(subprocesso)* | Fork+exec síncrono na thread do GTK congelando a UI por 100 ms a cada tecla | `XTestFakeKeyEvent` direto via `libXtst` |
| **Colagem** | `Ctrl+V` *(universal)* | `Ctrl+V` *(GUI only no Linux)* | Terminal ignorava e descartava a colagem | Inspecionar `WM_CLASS` e enviar `Ctrl+Shift+V` em terminais |
**Regra:** ao portar ou tocar em código de plataforma, entenda a garantia que o SO exige em vez de buscar a função com nome parecido.

### 6.5 Sub-janela do Flutter precisa de contexto GL e janela mapeada no boot
**Sintoma:** sub-janela (cartão/HUD) nascia como um retângulo cinza congelado que não respondia a cliques.
**Causa:** no Linux/NVIDIA, o `FlView` do Flutter só obtém contexto OpenGL válido se a janela X11 estiver
realmente mapeada (`gtk_widget_show_all`). Sem contexto GL, o Flutter nunca gera o primeiro frame e o
`initState` do Dart nunca executa.
**Regra:** criar uma única sub-janela (HUD + cartão juntos), mapeá-la no nascimento com recorte de forma vazio
(ou opacidade 0) para nascer invisível sem perder o contexto gráfico.

### 6.6 Decisão de Produto: Ditador ágil vs "Gravador de reuniões"
**Decisão do dono (2026-08-22):** O conceito de "gravação de reuniões" foi **completamente abandonado**.
O Dito existe com um único propósito essencial: ser a camada de entrada por voz mais rápida, leve e
confiável para comandos, prompts de IA e textos do usuário.
* **`F9`:** Modo *Push-to-Talk* (segurar para falar e colar diretamente ao soltar).
* **`F10`:** Modo *Toggle* (dar um toque para iniciar e outro para parar), feito exclusivamente para ditar
  sem precisar segurar tecla (por exemplo, ao ditar andando, em pé ou afastado do teclado). O fluxo encerra
  no cartão de revisão com colagem via Enter.
**Regra:** não adicione recursos de diários longos, divisão de oradores ou fluxos pesados de conferência.
O Dito é um digitador/ditador por voz focado em produtividade.


