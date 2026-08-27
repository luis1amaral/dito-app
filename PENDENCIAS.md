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

**Dívida aberta do porte, medida em 2026-08-25:** o portão `regras do projeto`
(`npx tsx quality/code-quality.ts`) está **vermelho com 5 itens**, todos herdados do porte X11 —
comentário de mais de uma linha em `src/main/paths.ts:6`, `paths.ts:13`, `native/src/input_x11.h:27`
e `native/src/key_hook_x11.h:28`, e `native/src/input_x11.cc` com 287 linhas para um teto de 260.
Enquanto isso não zerar, o `npm run verify` do Linux nunca fecha verde e o portão perde o valor de
sinal.

Pendências antigas que continuam: janela transparente no X11 depende de compositor
ativo, senão a pílula vem com fundo preto. **APT parado na 1.6.8** (subir `.deb` no GitHub não atualiza
Linux nenhum — o updater lê `apt.defaltm.com`; pendência de infraestrutura, não de código).

## 2. Windows — aberto

| # | Pendência | Por quê importa |
|---|---|---|
| W2 | **Ditado longo com voz de verdade ainda não gravado.** A 2.0.11 mediu 200 s de captura contínua na pílula real, mas com o microfone falso do Chromium: prova que o áudio não é mais cortado, **não** prova a transcrição de 3 min de fala humana | É o caminho que derruba o app se estiver errado, e a parte do motor continua sem execução longa |
| W3 | **Modelos que não são transducer sem portão automático.** O Whisper foi provado à mão na 2.0.5 (carrega em 608 ms e transcreve); `nemo-ctc`, `senseVoice` e `paraformer` continuam sem nenhuma execução | O portão `engine.mjs` monta o transducer na mão em vez de chamar o `build()` real, então não cobriria a regressão que a 2.0.5 corrigiu |
| W3b | **Whisper Tiny transcreve português como inglês.** `"Testando, testando"` saiu `"test and to test and to test"`; o campo `language` do sherpa nunca é preenchido a partir do `lang` da configuração | Oferecer um modelo que devolve lixo é pior que não oferecer |
| W4 | **Modelo streaming nunca rodou.** Nomes da API conferidos contra o pacote, mas nenhum foi baixado | Nome certo não é execução certa |
| W5 | **Sem a voz do dono nas fixtures.** Falta número por extenso e termo em inglês | Critério A5/A6 da paridade |
| W6 | **Iniciar com o Windows** não implementado (Linux feito na 2.0.12 via `loginItemSettings`) | O 1.7 tinha; o atalho com `--startup` existe, falta a entrada de inicialização no Windows |
| W7 | **Sem assinatura de código** — o SmartScreen avisa | Atrito para quem não é o dono |
| W8 | **Instalador cai na mesma pasta da 1.7.x** (`%LOCALAPPDATA%\Programs\Dito`) | Quem atualizar sem desinstalar fica com duas árvores misturadas |
| W9 | **Histórico antigo não migra** (`historico.jsonl` → `history.jsonl`) | Quem tinha histórico vê lista vazia |
| W10 | **A correção do microfone da 2.0.11 ainda não tem build no Windows.** O código é comum às duas plataformas e já está no repositório; falta rodar `npm run pack` e `npm run verify` numa máquina Windows | Até isso acontecer, no Windows a pílula continua ficando vermelha em toda pausa de 2 s e o ditado continua parando de gravar aos 3 min sem avisar. Detalhe do que mudou e por quê: `CHANGELOG.md` da 2.0.11 e `docs/decisoes.md` |
| W11 | **`npm run verify` inteiro nunca rodou na 2.0.11.** No Linux o `verify.ps1` não roda (sem `pwsh`); as camadas `nativo`, `tecla`, `segurar`, `fumaça`, `colagem` e `mutação` ficaram sem execução | São exatamente as camadas que cobrem hook de tecla e colagem — o caminho que a mudança da pílula não toca, mas que ninguém confirmou depois dela |

## 3. Provado nesta versão (não reabrir por engano)

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
