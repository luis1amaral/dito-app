# Pendências — o que falta, e o que muda no port para Linux

Escrito em 2026-08-23, com a 2.0.0 do Windows pronta e provada. Sem enfeite: o que **não** foi feito
e por quê importa.

---

## 1. Linux — o port inteiro

Decisão do dono: **Windows primeiro, Linux se faz no Linux.** Nada aqui foi executado numa máquina
Linux, então nada aqui é "provavelmente funciona" — é trabalho aberto.

### 1.1 O que já é portátil de graça

Não precisa de trabalho nenhum, porque é Chromium ou Node:

| Peça | Por que atravessa |
|---|---|
| Interface (pílula, ajustes) | Chromium vai embutido; o CSS é o mesmo |
| Captura de áudio | `getUserMedia` + `ScriptProcessor`, igual nos dois sistemas |
| Motor Parakeet/ONNX | `sherpa-onnx-linux-x64` existe no mesmo pacote npm |
| Download e sha256 dos modelos | Node puro |
| Histórico, config, log | Node puro |

### 1.2 O que **não** atravessa — é o addon nativo inteiro

`native/src/` é Win32 puro. No Linux precisa de um irmão em X11, e **cada item abaixo já mordeu
este projeto uma vez** (`plano/referencia/armadilhas.md`):

| O quê | Windows (feito) | Linux (a fazer) | Armadilha paga |
|---|---|---|---|
| Atalho global | `WH_KEYBOARD_LL` em thread própria com message pump | `XGrabKey` | `XGrabKey` é **exclusivo e por processo**: um hook por processo, nunca por janela. E falha **em silêncio** com `BadAccess` |
| Digitar texto | `SendInput` UNICODE | `XTest` (`XTestFakeKeyEvent`) | Precisa remapear um keysym livre por caractere: não existe equivalente direto de `KEYEVENTF_UNICODE` |
| Alvo da colagem | `GetForegroundWindow` na descida da tecla | EWMH `_NET_ACTIVE_WINDOW` | Capturar na **descida**, nunca depois: aí o Dito já é o foco |
| Classificar o alvo | classe da janela (`ConsoleWindowClass`) | `WM_CLASS` | O critério de "é terminal" é outro; **medir**, não presumir |
| Trazer para frente | `AttachThreadInput` + `SetForegroundWindow` | `_NET_ACTIVE_WINDOW` com timestamp | Sem timestamp válido o WM ignora e não avisa |
| Bandeja | `Shell_NotifyIcon` + `TaskbarCreated` | `libappindicator` / `StatusNotifierItem` | Em GNOME puro **não existe bandeja** sem extensão |

**Referência de porte:** `dito-app/packages/dito_win32/linux/dito_win32_plugin.cc` (1.687 linhas) já
tem `XGrabKey`, o thread X11 e o EWMH funcionando. Assim como no Windows, é **trocar a casca**
(method channel → N-API), não reescrever a lógica.

### 1.3 Janela transparente no Linux é o risco de verdade

A pílula usa `transparent: true` + `setIgnoreMouseEvents(true)`. No X11 isso depende de **compositor
ativo** — sem compositor a janela vem com fundo preto, e é exatamente o defeito que este projeto já
pagou no Flutter. Duas coisas obrigatórias:

1. Detectar compositor (`XGetSelectionOwner` de `_NET_WM_CM_S0`) e, sem ele, cair para janela opaca.
2. Rodar o portão 2.5 (`quality/smoke.ps1`, equivalente em shell) numa máquina X11 **antes** de dizer
   que funciona.

### 1.4 Pendências antigas do Linux que continuam de pé

Herdadas do Dito em Flutter e **ainda não resolvidas**:

- **APT parado na 1.6.8.** Subir `.deb` numa release do GitHub não atualiza Linux nenhum: o updater
  lê `https://apt.defaltm.com/dists/stable/main/binary-amd64/Packages`, e **nada no repositório
  publica lá**. Passo manual, na máquina Linux.
- **`hide()` viola a armadilha 4.3.** Desmapear a janela faz o contexto GL sumir e não voltar.
  Esconder é **recortar para região vazia**. No Electron isso vira `hide()` do Chromium, que é
  outro caminho — **medir no X11**, não presumir que herdou o problema.
- **`clearHitRect` / `forceRepaint` sem par no GTK.** No Electron não existem: o recorte é CSS. Fica
  como verificação, não como porte.

### 1.5 Empacotamento

`electron-builder` gera `.deb` e `.AppImage` com uma linha de config, mas:
- o addon nativo tem de compilar no Linux (`binding.gyp` precisa do bloco `conditions` para X11);
- `sherpa-onnx-linux-x64` traz `.so` que precisam entrar em `asarUnpack`, como as `.dll` hoje;
- auto-update no Linux só funciona por AppImage ou por APT — ver 1.4.

---

## 2. Windows — o que ficou aberto

| # | Pendência | Por quê importa |
|---|---|---|
| W1 | **Auto-update não foi exercitado.** `electron-updater` está configurado apontando para `luis1amaral/dito-app`, mas nunca houve duas versões para ele comparar | A 1.7.0 foi despublicada justamente por causa de update ruim. Testar com 2.0.0 → 2.0.1 antes de confiar |
| W2 | **Não há teste de ditado longo.** O worker corta em janelas de 20 s por causa do estouro de 2 GiB (issue #7925 do Orca), mas ninguém gravou 3 minutos para provar | É o caminho que derruba o app se estiver errado |
| W3 | **Só o Parakeet v3 foi transcrito de verdade.** Os outros 9 modelos do catálogo têm URL, tamanho e sha256 conferidos, e o motor tem o ramo de cada tipo — mas nenhum foi baixado e rodado | Tipo `senseVoice`/`whisper`/`nemo-ctc` pode ter nome de arquivo fora do padrão que o `resolveFile` não acha |
| W4 | **Modelo streaming nunca foi rodado.** Os nomes da API foram conferidos contra `node_modules/sherpa-onnx-node/streaming-asr.js` e batem (`createStream`, `acceptWaveform`, `isReady`, `decode`, `inputFinished`, `getResult`), mas nenhum modelo streaming foi baixado e transcrito | Nome certo não é execução certa: falta rodar um deles uma vez |
| W5 | **Não há teste da voz do dono.** As fixtures do portão de motor são uma frase de teste, não a fala real, e falta o critério de números por extenso e termos em inglês | É o critério A5/A6 da paridade, ainda `PENDENTE` |
| W6 | **Iniciar com o Windows** não está implementado | O Dito antigo tinha; o atalho com `--startup` existe, falta a entrada de inicialização |
| W7 | **Sem assinatura de código.** O instalador não é assinado, então o SmartScreen avisa | Atrito na instalação de quem não é o dono |
| W8 | **O instalador cai na mesma pasta da versão 1.7.x.** Medido: NSIS instala em `%LOCALAPPDATA%\Programs\Dito`, exatamente onde o Inno Setup da 1.7.3 já estava — `Dito.exe` do Electron conviveu com `dito_app.exe` e `flutter_windows.dll` na mesma pasta | Quem atualizar do 1.7.x sem desinstalar antes fica com duas árvores misturadas, e o desinstalador de uma apaga a outra. O instalador precisa detectar e remover a instalação antiga (Inno, `unins000.exe`) antes de copiar |
| W9 | **Histórico antigo não migra.** O arquivo mudou de `historico.jsonl` para `history.jsonl` na renomeação para inglês | Quem tinha histórico vê a lista vazia; migrar ou renomear na primeira execução |

---

## 3. O que foi provado (para não reabrir por engano)

- Addon nativo carrega no Electron 43 / Node 24 (N-API é estável entre os dois).
- Parakeet v3 int8 entrega **pontuação e maiúscula** em português — não é preciso passo de pontuação.
- Colagem em `cmd.exe` cru (`PROCESSED_INPUT` desligado) chega inteira, com acento pt-BR exato.
- O app sobe nos dois modos, não abre janela na bandeja e desenha a tela (0% de preto puro).
- `PrintWindow(PW_RENDERFULLCONTENT)` **não** captura o Chromium: devolve janela vazia.
- `capturePage()` **trava** se a janela não estiver sendo pintada — mostrar e focar antes.
