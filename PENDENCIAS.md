# Pendências

Sem enfeite: o que ficou faltando depois da 1.7.4, e por quê importa.

## Linux: publicar no APT

Subir o `.deb` numa release do GitHub **não atualiza Linux nenhum**. O updater do Linux lê
`https://apt.defaltm.com/dists/stable/main/binary-amd64/Packages`
(`packages/defalt_updater/lib/src/linux_apt.dart`), e **nada neste repositório publica lá** —
confirmado por grep em `.github/` e `packaging/` (zero ocorrências de `apt.defaltm`,
`apt-ftparchive`, `reprepro` ou `dists/stable`). Conferido ao vivo agora: o repositório APT está
parado na **1.6.8**. Esse passo é manual, feito na máquina Linux, e a release não está terminada
sem ele. Ver `docs/RELEASE.md`.

## Linux: as correções da 1.7.4 ainda não foram exercitadas em Linux

O conserto de coordenadas do recorte (armadilha 4.14) foi feito no plugin Windows
(`packages/dito_win32/windows/dito_win32_plugin.cpp`). O lado GTK
(`packages/dito_win32/linux/dito_win32_plugin.cc`, `gtk_widget_shape_combine_region`) não foi
tocado e precisa ser conferido numa máquina Linux X11 — ele pode ter o mesmo problema de origem
cliente-vs-janela, ou pode não ter, mas ninguém mediu. Idem o comportamento de abrir só na bandeja
(armadilha 4.15 e o `--startup` nos atalhos): isso hoje só está garantido no instalador Windows
(`packaging/windows/dito.iss`); o empacotamento Linux não foi revisado com o mesmo critério.

## Linux: `windowManager.hide()` viola a armadilha 4.3

`lib/ui/window_orchestrator.dart` chama `windowManager.hide()` nas linhas **47, 90 e 124**, sem
nenhum desvio por plataforma. No Windows isso é correto. No **X11 é a armadilha 4.3**, paga em
2026-08-21: desmapear a janela faz o `FlView` perder o contexto GL e **não voltar** — o HUD some
para sempre até reabrir o app. A regra que o projeto aprendeu é: esconder é recortar para uma
região **vazia**, nunca desmapear.

Isso já foi feito no Windows (`window.setHitRect` com retângulo vazio agora aplica
`CreateRectRgn(0,0,0,0)` em vez de remover a região). Falta o equivalente no caminho Linux, e falta
o `hide()` deixar de ser chamado lá.

## Linux: dois métodos nativos novos só existem no Windows

`window.clearHitRect` e `window.forceRepaint` foram criados hoje em
`packages/dito_win32/windows/dito_win32_plugin.cpp` e **não têm par** em
`packages/dito_win32/linux/dito_win32_plugin.cc` (grep: zero ocorrências). No Linux as chamadas
levantam `MissingPluginException` — engolida pelo `try/catch` do `WindowOrchestrator`, então não
quebra, mas o comportamento simplesmente não acontece:

- `clearHitRect` é quem devolve a janela à forma retangular ao abrir o painel de Configurações. Sem
  ele, o painel pode herdar o recorte da pílula.
- `forceRepaint` é o *jiggle* que evita a faixa preta quando a janela é dimensionada escondida.

No GTK o equivalente de limpar o recorte é `gtk_widget_shape_combine_region(widget, NULL)`; o
`forceRepaint` provavelmente é desnecessário fora do swapchain do Windows, mas isso **precisa ser
medido numa máquina X11**, não presumido.

## `stt.device` é botão morto

O campo existe na config (`lib/config/config_model.dart`), aparece nos Ajustes
(`lib/ui/main/settings_page.dart`) e trafega no protocolo do motor
(`devicePref` em `lib/engine/native_engine.dart:174`) — mas **não decide nada**: dentro de
`_handleStart`, `devicePref` é recebido e nunca lido de novo; `_ensureModelLoaded` chama
`worker.loadModel(path, useGpu: true, ...)` com `useGpu: true` fixo, e quem escolhe CPU ou GPU de
fato é o whisper.cpp por baixo. Ou o campo vira decisão de verdade (passar `devicePref` adiante e
honrar `cpu`), ou sai da config e da tela de Ajustes.

## CUDA no Windows

`packages/dito_whisper/windows/CMakeLists.txt` não tem nenhuma referência a CUDA — hoje o Windows
compila e roda **só em CPU**. `docs/WINDOWS.md` já documenta o pré-requisito opcional (CUDA Toolkit
12.x) e a armadilha das arquiteturas reais (`CUDA_ARCHITECTURES="61;75;86;89"`, nunca só `-virtual`),
mas o CMake do Windows ainda não usa nada disso. Se outro agente estiver portando isso agora, esta
pendência sai quando o build Windows ganhar a opção de GPU; se não, falta ligar o `GGML_CUDA` no
CMake do Windows do mesmo jeito que já existe em `packages/dito_whisper/src/ggml/src/ggml-cuda/`.
