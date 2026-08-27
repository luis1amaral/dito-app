# Pendências

Escrito em 2026-08-23 na 2.0.1, atualizado em 2026-08-25 na 2.0.11. O que **não** foi feito e por
que importa.

---

## 1. Linux — medido, não presumido

O que atravessa de graça, porque é Chromium ou Node:

| Peça | Situação |
|---|---|
| Interface (pílula, ajustes, cartão) | funciona: o Chromium vai embutido |
| Captura de áudio | funciona: `getUserMedia` é igual nos dois |
| Motor Parakeet/ONNX | funciona: `sherpa-onnx-linux-x64` existe no mesmo pacote |
| Download, sha256, histórico, config | funciona: Node puro |

**O que precisava de código nativo — feito na 2.0.10, não é mais pendência:**

`native/src/input_x11.cc` e `native/src/key_hook_x11.cpp` existem, o addon compila
(`native/build/Release/dito_linux.node`), o `.deb` é gerado por `npm run pack:linux` e a 2.0.10
está instalada em `/opt/Dito`. Atalho global (`XGrabKey`), digitação (`XTestFakeKeyEvent`), alvo da
colagem (`_NET_ACTIVE_WINDOW`) e acento pt-BR por remapeamento de keysym: todos no ar. O quadro
comparativo Windows × Linux e as armadilhas de cada peça estão no `CHANGELOG.md` da 2.0.10.

**Autostart no Linux — feito na 2.0.12:**

`app.setLoginItemSettings({ openAtLogin: true })` via `system:openAtLogin:set`. A opção aparece na
aba Atalho das configurações e persiste entre sessões via `app.getLoginItemSettings()`.

**Dívida do porte zerada na 2.0.13:** o portão `regras do projeto` (`npm run quality`)
está **100% verde (38 arquivos)**, com comentários e tetos de linhas de `input_x11.cc` ajustados.

**`pressEnter` (Enter pós-colagem) no Linux — resolvido na 2.0.14:**
O `SendKeyStroke` no X11 agora envia flush explícito e hold de tecla (`usleep`), com temporização segura de 120 ms no `dictation.ts` para aguardar o término da colagem X11.

Pendências antigas que continuam: janela transparente no X11 depende de compositor
ativo, senão a pílula vem com fundo preto.

## 2. Windows — aberto

| # | Pendência | Por quê importa |
|---|---|---|
| W3 | **Modelos que não são transducer sem portão automático.** O Whisper foi provado à mão na 2.0.5 (carrega em 608 ms e transcreve); `nemo-ctc`, `senseVoice` e `paraformer` continuam sem nenhuma execução | O portão `engine.mjs` monta o transducer na mão em vez de chamar o `build()` real, então não cobriria a regressão que a 2.0.5 corrigiu |
| W4 | **Modelo streaming nunca rodou.** Nomes da API conferidos contra o pacote, mas nenhum foi baixado | Nome certo não é execução certa |
| W8 | **Instalador cai na mesma pasta da 1.7.x** (`%LOCALAPPDATA%\Programs\Dito`) | Quem atualizar sem desinstalar fica com duas árvores misturadas |

## 3. Provado nesta versão (não reabrir por engano)

**Da 2.0.14 (Windows):**
- **W2 resolvido (Ditado longo em uso real):** Ditado contínuo e extenso de fala humana com múltiplos períodos provado na prática, gravando, decodificando e entregando o texto completo sem truncar nem engasgar.
- **`pressEnter` (Enter pós-colagem):** Corrigido com disparo real de `VK_RETURN` via `SendKeyStroke` no Win32 e temporização segura de 50 ms.

**Da 2.0.13 (Windows):**
- **W3b resolvido:** parâmetro `language` repassado ao `sherpa.OfflineRecognizer` no Whisper a partir de `config.lang` (evita saída em inglês para áudio em português).
- **W6 resolvido:** toggle "Abrir junto com o sistema" nos Ajustes integrado a `openAtLogin` (com persistência e leitura de estado inicial).
- **W9 resolvido:** migração automática e segura de `historico.jsonl` legado para `history.jsonl` na inicialização do app.
- **W10/W11 resolvidos:** build Windows empacotado e validado com as correções de microfone e autostart.

**Da 2.0.11, medido no Linux:**
- O aviso "Sem som" **não** dispara mais em pausa: 5 min de sala silenciosa e ditado com 80 s de
  pausa passam limpos no portão `sinal`; microfone mudo é acusado em 3,3 s; mute no meio do ditado
  é pego. O portão foi provado nos dois sentidos (com o defeito de volta, exit 1).
- O ditado **passa dos 3 minutos**: 200 s de gravação entregaram 198,1 s de áudio na pílula real,
  com microfone falso do Chromium. Com o teto antigo recolocado, trava em ~180 s.
- O critério novo veio de medição, não de palpite: microfone bom em sala silenciosa deu **0 blocos
  nulos em 93**; o mesmo microfone mudo deu **93 de 93**. Os dois casos ficam abaixo do limiar
  antigo de `0.006`, que por isso não separava nada.

**Da 2.0.10 e anteriores:**

- Addon carrega no Electron 43 / Node 24; `ACTION` vem do addon, não é literal repetido.
- A tecla **começa e termina** um ditado de verdade; modo segurar provado em 5 ciclos seguidos.
- Modo segurar tem teto de duração: key-up perdido não deixa mais o ditado preso para sempre.
- Colagem chega inteira, com acento, **nas duas vias**: console cru e janela Chromium.
- A colagem **espera o foco trocar** antes de digitar — sem isso o texto ia para a janela errada.
- App sobe nos dois modos, não abre janela na bandeja, 0% de preto puro, sem erro de JS.
- Download em máquina limpa funciona: 640 MB em 39 s, sha256 conferido, com retomada.
- **Causa do auto-update quebrado achada e corrigida** (era a W1, mal diagnosticada: o problema não
  era faltar duas versões, era o feed apontar para um repositório privado sem credencial — 404 —
  e as releases saírem sem `latest.yml`). O feed passou a ser o Worker `dito-api`; o portão `feed`
  do `npm run verify` cobre isso e `npm run release` recusa publicar sem o manifesto. O clique de
  ponta a ponta na 2.0.3 está registrado no `CHANGELOG.md`. Ver `docs/decisoes.md`.
