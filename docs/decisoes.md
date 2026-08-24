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
