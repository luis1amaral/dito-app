# CHANGELOG — dito-flutter

Mais recente no topo. Cada entrada diz **o quê**, **por quê** e **como foi verificado**.

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
