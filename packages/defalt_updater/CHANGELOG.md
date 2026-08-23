# CHANGELOG — defalt_updater

## 1.0.0 — 16/08/2026

Primeira versão. Pacote Dart/Flutter que extrai o auto-update **que já rodava em produção
no `slime-animes`** para os três apps que não passam por loja no Windows.

### O quê

- `DefaltUpdater` — I/O puro, sem estado e **sem tela**: `check()`, `download()`,
  `downloaded()`, `apply()`, `cleanup()`, `compareVersions()`.
- `UpdaterConfig` — tudo que muda de um app para outro: `appId`, `manifestUrl`,
  `downloadUrl`, `displayName`, `aptPackage`, timeouts.
- `UpdateDelivery` — a plataforma declara **como** ela atualiza (`inAppDownload` no Windows,
  `browserHandoff` no Android, `packageManager` no Linux/APT, `none` no resto), em vez de a
  UI ficar perguntando `Platform.isX`.
- `UpdaterConfig.platforms` — **onde este app se atualiza sozinho**, e o padrão **não inclui
  Android**. App que publica na Play Store não pode se auto-instalar (a loja atualiza, e um
  APK lateral colide com o que ela instalou); só quem está fora da loja declara `'android'`.
  Esquecer o campo **desliga** o Android — falha fechado, não aberto.
- `UpdateController` — `ChangeNotifier` opcional com throttle de 6h, "pular versão", modo
  `notify`/`auto`/`off`, progresso e estágio. Serve `provider` e `riverpod` sem adaptador.
- **Verificação de integridade de verdade**: `sha256` quando o manifesto traz um, tamanho
  exato quando não traz, e `UpdateInfo.integrity` dizendo qual dos dois valeu. O hash é
  conferido em streaming (um APK de ~100 MB não cabe confortavelmente na memória do
  celular). O download escreve num `.part` e só é renomeado depois de conferir.

### Por quê

O mesmo auto-update estava escrito uma vez só (no `slime-animes`) e faltava nos outros dois
apps, que também são distribuídos fora de loja no Windows. Copiar os quatro arquivos para
cada app criaria três cópias de uma lógica cheia de armadilhas de plataforma — e as
armadilhas já custaram bug (ver `doc/PLATAFORMAS.md`: o `powershell` sem console que morria
na hora, o `.deb` que o `dpkg` passaria a mentir sobre, o aviso de "fonte desconhecida" do
Android). Um pacote, um lugar para corrigir.

O comportamento do `slime-animes` foi **preservado**, não redesenhado — inclusive o Android,
que é o único dos três fora da Play Store e o único que se atualiza sozinho no celular.

Além do que já existia, o pacote acrescentou a conferência por `sha256` (antes só havia
tamanho, que pega truncamento mas não pega troca de conteúdo).

### Como foi verificado

`flutter analyze` → `No issues found!` (exit 0)
`flutter test` → **33 testes, All tests passed!** (exit 0)

O que os testes provam de verdade, não por mock:

- **O ciclo inteiro, encaixado** (`test/full_cycle_test.dart`): um app na **1.12.0** pergunta
  a um `HttpServer` de verdade, descobre a **1.13.0**, baixa o zip por streaming, confere o
  `sha256` e roda **o updater real**, que troca os arquivos da instalação e relança. No fim, a
  instalação **é** a 1.13.0: o arquivo existente virou `1.13.0`, o arquivo novo apareceu, o
  arquivo do usuário sobreviveu e quem reabriu foi a versão nova. É o único teste que responde
  "sim" à pergunta *o update funciona de ponta a ponta?*.
- **Ciclo completo contra um `HttpServer` local** (`test/download_integrity_test.dart`):
  versão antiga (1.12.0) consulta o manifesto, encontra a 1.13.0, baixa 64 KB por streaming
  e confere o `sha256`. Também prova as recusas: conteúdo trocado **com o tamanho certo** é
  barrado pelo hash, download truncado é barrado pelo tamanho, e nos dois casos nada sobra
  no disco. Cancelar no meio não deixa arquivo "pronto" nem vira erro de rede. Versão igual
  ou mais nova que a publicada nunca vira downgrade. Servidor fora do ar devolve `null`, não
  exceção.
- **Troca de instalação no Windows, de verdade** (`test/windows_apply_test.dart`): monta uma
  instalação "velha", empacota uma "nova" com `Compress-Archive`, sobe um processo cobaia no
  lugar do app e roda **o mesmo `.ps1` que o app dispara**. Assere que o arquivo existente
  foi sobrescrito, que o arquivo novo apareceu, que um arquivo do usuário **sobreviveu**
  (robocopy sem `/MIR`), que o zip foi limpo e que quem foi relançado é a versão **nova**.
- Parser do `Packages` do APT (CRLF, prefixo que não pode casar, pacote ausente) e o
  comparador semver (`1.11` > `1.9`, `+build` ignorado, lixo não vira update falso).

### O que NÃO foi verificado rodando

- **Android**: o handoff para o navegador (`url_launcher`) e a instalação pelo instalador do
  sistema exigem aparelho. O código é o mesmo que já roda em produção no `slime-animes`, mas
  neste ciclo ele não foi exercitado num aparelho.
- **Linux/APT**: `pkexec` + o helper do polkit exigem a máquina Linux com o pacote instalado
  pelo repositório. Só o parser do `Packages` foi testado.
- O caminho de **elevação (UAC)** do Windows, usado quando o app está em pasta protegida.
