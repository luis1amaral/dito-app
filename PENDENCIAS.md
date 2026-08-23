# Pendências

Escrito em 2026-08-23, na 2.0.1. O que **não** foi feito e por que importa.

---

## 1. Linux — medido, não presumido

O que atravessa de graça, porque é Chromium ou Node:

| Peça | Situação |
|---|---|
| Interface (pílula, ajustes, cartão) | funciona: o Chromium vai embutido |
| Captura de áudio | funciona: `getUserMedia` é igual nos dois |
| Motor Parakeet/ONNX | funciona: `sherpa-onnx-linux-x64` existe no mesmo pacote |
| Download, sha256, histórico, config | funciona: Node puro |

**O que NÃO atravessa — e é o produto inteiro:**

`native/src/input.cc` usa API do Win32 em **8 pontos** e `key_hook.cpp` é Win32. Sem o irmão X11,
o app no Linux **não tem atalho global e não cola em lugar nenhum**. Ele abriria, mostraria a tela e
transcreveria só dentro de si mesmo.

**Por isso o `.deb` não foi publicado.** Publicar seria entregar um app que não faz o que promete.

**O que já está pronto para quando for feito no Linux:**
- `native/binding.gyp` tem o bloco `OS=='linux'` apontando para `src/input_x11.cc` e
  `src/key_hook_x11.cpp` — os dois arquivos que faltam escrever.
- `npm run pack:linux` gera o `.deb` numa linha, assim que o addon existir.
- A referência de porte é `dito-app/packages/dito_win32/linux/dito_win32_plugin.cc` (1.687 linhas,
  já funciona): é **trocar a casca** (method channel → N-API), não reescrever a lógica.

| Peça | Windows (feito) | Linux (a fazer) | Armadilha |
|---|---|---|---|
| Atalho global | `WH_KEYBOARD_LL` em thread própria | `XGrabKey` | exclusivo por processo; falha **em silêncio** com `BadAccess` |
| Digitar | `SendInput` UNICODE | `XTestFakeKeyEvent` | precisa remapear keysym por caractere |
| Alvo da colagem | foreground na descida da tecla | `_NET_ACTIVE_WINDOW` | capturar na descida, nunca depois |
| Trazer para frente | `SetForegroundWindow` + **esperar a troca** | `_NET_ACTIVE_WINDOW` com timestamp | sem timestamp o WM ignora calado |
| Bandeja | `Shell_NotifyIcon` | `StatusNotifierItem` | GNOME puro não tem bandeja sem extensão |

Pendências antigas que continuam: **APT parado na 1.6.8** (subir `.deb` no GitHub não atualiza
Linux nenhum — o updater lê `apt.defaltm.com`), e janela transparente no X11 depende de compositor
ativo, senão a pílula vem com fundo preto.

## 2. Windows — aberto

| # | Pendência | Por quê importa |
|---|---|---|
| W1 | **Auto-update nunca exercitado.** `electron-updater` está ligado e aponta para `luis1amaral/dito-app`, mas nunca houve duas versões para comparar | A 1.7.0 foi despublicada por update ruim |
| W2 | **Ditado de 3 minutos nunca gravado.** O corte em janelas de 8 s existe e é testado por unidade, mas ninguém falou 3 minutos seguidos | É o caminho que derruba o app se estiver errado |
| W3 | **9 dos 10 modelos nunca rodaram.** URL, tamanho e sha256 conferidos; o motor tem o ramo de cada tipo; falta baixar e transcrever | `resolveFile` pode não achar o arquivo de um tipo diferente |
| W4 | **Modelo streaming nunca rodou.** Nomes da API conferidos contra o pacote, mas nenhum foi baixado | Nome certo não é execução certa |
| W5 | **Sem a voz do dono nas fixtures.** Falta número por extenso e termo em inglês | Critério A5/A6 da paridade |
| W6 | **Iniciar com o Windows** não implementado | O 1.7 tinha; o atalho com `--startup` existe, falta a entrada de inicialização |
| W7 | **Sem assinatura de código** — o SmartScreen avisa | Atrito para quem não é o dono |
| W8 | **Instalador cai na mesma pasta da 1.7.x** (`%LOCALAPPDATA%\Programs\Dito`) | Quem atualizar sem desinstalar fica com duas árvores misturadas |
| W9 | **Histórico antigo não migra** (`historico.jsonl` → `history.jsonl`) | Quem tinha histórico vê lista vazia |

## 3. Provado nesta versão (não reabrir por engano)

- Addon carrega no Electron 43 / Node 24; `ACTION` vem do addon, não é literal repetido.
- A tecla **começa e termina** um ditado de verdade; modo segurar provado em 5 ciclos seguidos.
- Modo segurar tem teto de duração: key-up perdido não deixa mais o ditado preso para sempre.
- Colagem chega inteira, com acento, **nas duas vias**: console cru e janela Chromium.
- A colagem **espera o foco trocar** antes de digitar — sem isso o texto ia para a janela errada.
- App sobe nos dois modos, não abre janela na bandeja, 0% de preto puro, sem erro de JS.
- Download em máquina limpa funciona: 640 MB em 39 s, sha256 conferido, com retomada.
