# Decisões e por quês

Este arquivo existe porque **comentário no código tem no máximo uma linha**. Quando o porquê não
cabe numa linha, ele vem para cá e o código guarda um ponteiro.

---

## Corte do áudio em blocos — `src/main/audio-chunker.ts`

Portado de `stablyai/orca` (MIT), `src/main/speech/stt-offline-audio-chunker.ts`.

**Por que existe:** decodificar um ditado inteiro numa chamada só faz o tensor do ONNX crescer com a
duração até uma alocação ≥ 2 GiB derrubar o processo — é a issue #7925 deles.

**Por que 8 s e não 30 s:** o Orca usa janela de 30 s porque é o teto seguro para reunião. 30 s é
**limite, não alvo**: num ditado de 10 s você não veria texto nenhum antes de terminar. Com 8 s o
texto aparece enquanto a pessoa ainda fala. O preço é mais chamadas de decodificação e pontuação um
pouco pior na emenda entre blocos.

**Por que cortar no ponto mais silencioso, medindo janelas de 100 ms:** 100 ms é o tamanho de uma
pausa entre palavras. Janela menor confunde o fechamento de uma plosiva (o silêncio curto dentro de
um "p", "t", "k") com pausa de verdade, e o corte cai no meio da palavra.

**Por que `Math.max(1, ...)` no ponto de corte:** um corte de zero amostra não consome o buffer e o
laço nunca termina.

## Sinal do microfone — `src/shared/mic-signal.ts`

**Por que o limiar de volume foi embora.** Até a 2.0.10 a pílula gritava "Sem som" quando o RMS
ficava abaixo de `0.006` por 2 s. Medido nesta máquina em 2026-08-25, 93 blocos de 4096 quadros a
48 kHz em cada caso:

| microfone | blocos nulos | RMS máximo |
|---|---|---|
| funcionando, sala em silêncio | 0 de 93 | 5,8e-3 |
| mudo | 93 de 93 | 0 |

Os dois casos ficam **inteiros** abaixo de `0.006` — o limiar não separava nada. No log real ele
disparou em **56 dos 159 ditados**, quase sempre aos 3,3 s (a pessoa apertou a tecla e pensou antes
de falar) ou nos últimos segundos (parou de falar e foi apertar a tecla). O áudio continuava
chegando e a transcrição saía inteira: o aviso mentia, e quem via a pílula vermelha desligava o
ditado achando que o microfone tinha caído.

**O critério que sobrou:** um microfone que funciona nunca entrega bloco **digitalmente nulo** —
nem numa sala em silêncio, nem com supressão de ruído ligada. Nulo é o que "nada está chegando"
quer dizer, então é o que a regra mede. Pausa deixou de ser falha, e o aviso passou a valer também
no meio do ditado (mute no botão do headset), coisa que o limiar não fazia sem gritar sem parar.

**Por que o aquecimento de 1200 ms continua:** o dispositivo pode entregar blocos nulos enquanto
acorda de `suspend-on-idle`, e isso não é falha.

## Anti-repique da tecla — `src/main/dictation.ts`

O modo alternar ignorava qualquer toque que chegasse **menos de 250 ms** depois do anterior. O filtro
nasceu contra a repetição automática do teclado, quando o addon ainda emitia borda repetida.

Isso deixou de ser verdade: desde a 2.0.12 a borda só é emitida quando o estado **muda**
(`if (binding.last_down == down) continue`, no hook dos dois sistemas), e no X11 a repetição é
detectável (`XkbSetDetectableAutoRepeat`). O filtro de 250 ms virou redundante — e nocivo: um toque
duplo rápido para **parar** caía dentro da janela e era descartado em silêncio. A pílula sumia, o
usuário achava que tinha parado, e o app seguia gravando o som do ambiente e do computador até o
teto do ditado — e no fim digitava aquilo na janela que estivesse em foco. Medido em 2026-08-28:
com 150 ms entre os dois toques, sobravam **2 streams de captura vivos** no PipeWire e o ditado
correu por 29 s.

A janela caiu para **40 ms**, que cobre o repique físico da chave (poucos milissegundos) e não
alcança toque humano nenhum. Quem prova é `quality/hotkey-linux.mjs`, que aperta a tecla duas vezes
com 150 ms e exige o `stopped` no log e zero captura sobrando.

## Duração de um ditado — `src/renderer/src/pill.ts` e `src/main/dictation.ts`

**Por que o teto de 180 s do renderer foi removido.** Ele parava de enfileirar áudio aos 3 minutos
e **não avisava ninguém**: a pílula continuava escrita "Ouvindo" e a onda continuava se mexendo,
enquanto nada mais era transcrito. O log tem um ditado de 317 s que caiu exatamente nisso. O
comentário dizia proteger contra um buffer sem limite, mas `flushPending` despacha a cada segundo e
o `AudioChunker` nunca guarda mais que uma janela de 8 s — não havia buffer crescendo para proteger.

**O teto que ficou é honesto.** `MAX_TAKE_MS` (1 h, `DITO_MAX_TAKE_MS` para os portões) vive no
processo principal e **encerra o ditado de verdade**: transcreve, entrega o texto e registra no log.
Existe porque o modo *alternar* não tem key-up para terminar — uma tecla esquecida gravaria para
sempre. O teto de `MAX_HOLD_MS` é outro assunto: aquele é a rede do key-up engolido no modo
*segurar*.

## Download de modelo — `src/main/models.ts`

Formato adaptado de `stablyai/orca` (MIT), `src/main/speech/model-manager.ts`. Cada peça está lá por
um motivo que eles pagaram:

| Peça | Por quê |
|---|---|
| Retomada por `Range` | rede instável e proxy matam transferência longa perto do fim |
| Reiniciar da URL canônica | redirecionamento assinado de CDN expira; retentar no link velho falha |
| Progresso pelo tamanho em disco | é o real; o que o socket disse pode não ter chegado ao arquivo |
| Contador de travamento | só desiste quando os bytes param de chegar, não no primeiro erro |

**Por que "instalado" confere arquivo por arquivo com o tamanho exato:** cada modelo nomeia os
arquivos de um jeito (`encoder.int8.onnx`, `tiny-encoder.onnx`, `encoder-epoch-99-avg-1.onnx`), então
a lista do catálogo é a única verdade — não dá para procurar um nome fixo.

**Por que o sha256:** download truncado passa pela checagem de tamanho e quebra o motor depois, longe
da causa.

## Auto-update — `src/main/updater.ts`

Formato do `stablyai/orca` (MIT). A lição que carregamos é a issue #7576 deles: um feed que falha
sempre **não pode** rearmar a checagem numa cadência fixa para sempre. O intervalo dobra a cada
falha até um teto, e qualquer checagem completa zera o contador.

## Feed de atualização — por que passa por um Worker

`dito-app` é um repositório **privado**. O `electron-updater` busca o feed sem credencial nenhuma —
o app instalado na máquina do usuário não tem token —, e o GitHub responde **404** (não 403) para
recurso privado sem auth, por política de não revelar que o repositório existe. A mensagem que ele
imprime, *"double check that your authentication token is correct"*, engana: não há token errado,
não há token. Foi assim que a 2.0.2 mostrou um dump de HTTP na tela de Atualizações.

Embutir um PAT no `.exe` seria o mesmo que publicá-lo: `strings` num binário devolve qualquer
segredo. Então o token mora no Worker `dito-api` (`dito-api.defaltm.com`), que autentica no GitHub e
serve o feed no formato do provider `generic`:

- `GET /update/win/latest.yml` — o manifesto, repassado **como asset da release**. Ele carrega o
  `sha512` em base64 que só o `electron-builder` sabe calcular, e a API do GitHub só expõe `sha256`:
  sintetizar esse arquivo no Worker seria inventar um hash. Por isso `npm run release` recusa
  publicar sem ele.
- `GET /update/win/<arquivo>` — **302** para a URL assinada do CDN do GitHub. Os 109 MB nunca
  atravessam o Worker, e o header `Range` chega intacto ao CDN, que é do que o download diferencial
  depende. Medido: `Range: bytes=0-1023` seguindo o redirect devolve `206` com 1024 bytes.

O `.blockmap` da versão **substituída** vive numa release antiga, então o Worker procura o arquivo
na última release e, não achando, varre as 20 mais recentes.

**Consequência que não dá para desfazer:** o `resources/app-update.yml` fica congelado dentro de cada
pacote. As builds 2.0.1 e 2.0.2 apontam para o GitHub público e **nunca** vão se atualizar sozinhas —
a 2.0.3 é a primeira que fala com o Worker, e precisa ser instalada à mão uma vez. Custou zero porque
`downloadCount` das duas era 0.

## Instalar a atualização — por que NÃO no fechamento

A 2.0.5 usava `autoInstallOnAppQuit`. O efeito medido: o usuário fechava o Dito, o instalador rodava
em silêncio, trocava a versão — e **não relançava o app**. Da cadeira dele o Dito simplesmente
sumiu, e ele concluiu que "apagou e não instalou nada", quando na verdade a 2.0.5 estava instalada.

A regra vem do `defalt_updater`, o pacote que o Slime Animes usa, escrita lá em
`lib/src/windows_installer.dart:38`:

> *só encerra o app depois que o updater PROVAR que subiu … fechar sozinho e não atualizar nada é o
> pior resultado possível.*

Então o Dito passou ao mesmo desenho:

- `autoDownload = true` — baixa em segundo plano, sem perguntar. Ninguém é interrompido no meio de
  um ditado.
- `autoInstallOnAppQuit = false` — **sair é só sair**. Fechar o app nunca mexe na instalação.
- `installNow()` chama `quitAndInstall(true, true)`. O segundo `true` é `isForceRunAfter`: é ele que
  faz o app **voltar sozinho**. Sem ele, o comportamento é o da 2.0.5.
- `checkNow()` devolve cedo quando o estado é `ready`: uma verificação nova não pode descartar um
  download que já terminou e está a um clique de instalar.
- O estado carrega `percent`, porque uma frase congelada durante 109 MB é lida como travamento.

A chamada de `quitAndInstall` é adiada em 400 ms de propósito: ela mata o processo, e sem o atraso a
resposta do IPC morreria antes de chegar na tela.

## Entrega do texto — por que a área de transferência espera

A 2.0.8 digitava o trecho ao vivo **e**, no fim do ditado, a mensagem inteira de novo. Duas causas
independentes, as duas achadas na mensagem duplicada que o próprio usuário ditou.

**1. A corrida com a área de transferência.** `native/src/input.cc:138` põe o texto na área de
transferência e dispara `Ctrl+V` com `SendInput` — que é **assíncrono**: a função volta assim que o
evento é postado, sem esperar o app de destino ler. Na linha seguinte o `dictation.ts` fazia
`clipboard.writeText(spoken)`, trocando o conteúdo pela mensagem inteira **antes** do destino ler.
O `Ctrl+V` chegava depois e colava tudo.

A escrita do texto completo passou a ser adiada em `CLIPBOARD_HANDOVER_MS = 1500`. O número não é
chute: `quality/paste-targets.mjs:91` prova que uma colagem chega dentro de 1400 ms, então o repasse
tem que ficar acima dessa janela. A garantia para o usuário continua a mesma — o ditado inteiro
sempre acaba no `Ctrl+V` —, só que 1,5 s depois, o que ninguém percebe.

**2. O separador aparado.** `onSegment` calculava `delta` (que já vem com o próprio espaço, por
exemplo `" Tô falando"`) e passava por `joinSegment(unsent, delta)`. Com `unsent` vazio — o caso
normal, porque ele é limpo a cada segmento digitado — essa função cai em `if (!soFar) return piece`,
e `piece` é `next.trim()`. O espaço morria ali, e os trechos saíam colados: `"quando eu.Tô falando"`.

Agora o delta é concatenado cru, e o cálculo virou `segmentDelta()` em `src/shared/join-segments.ts`
para poder ser exercitado. A invariante está no portão `chunker`:

> a soma de tudo que foi digitado tem que dar exatamente o que vai para a área de transferência.

Provada nos dois sentidos: repondo o `joinSegment('', delta)` da 2.0.8, o portão reprova com
`"correcao.Eu nao pensei"` — o mesmo defeito, reproduzido.

## Contrato compartilhado — `src/shared/config.ts` e `src/shared/ipc.ts`

**Por que existe:** a 2.0.0 saiu com um `<select>` de modo cujos valores (`alternar`/`segurar`) não
batiam com o que o código comparava (`toggle`/`hold`). O campo vinha em branco e o modo segurar
nunca funcionaria. Com o tipo declarado num lugar só, o compilador para o build.

Mesmo raciocínio no IPC: canal com nome errado ou payload de formato diferente deixa de compilar dos
**dois** lados, em vez de virar mensagem perdida em tempo de execução.

## Emenda dos blocos — `src/shared/join-segments.ts`

Regras portadas de `dictation-final-segments.ts` do Orca. As janelas nunca se sobrepõem, então não há
o que deduplicar: a única decisão é o espaço entre um bloco e o próximo — sem espaço antes de
vírgula, ponto e fecha-parêntese; sem espaço depois de abre-parêntese.

## Código nativo — `native/src/`

`key_hook.cpp` e `key_table.cpp` vieram inteiros de `packages/dito_win32/windows` e são **congelados**.
As duas armadilhas que eles carregam:

1. `WH_KEYBOARD_LL` precisa de **thread própria com message pump próprio**. Na thread principal o
   Windows desinstala o hook em silêncio por `LowLevelHooksTimeout`.
2. **Tecla suprimida some do `GetAsyncKeyState`.** Por isso existe o timer que confere o estado
   físico: sem ele, um key-up engolido deixa a tecla presa no modo segurar.

`ACTION` é exportado pelo addon porque a string existia em dois lugares e dessincronizou — foi esse
o defeito que quebrou a 2.0.0.
