# CHANGELOG — Dito

## Não publicado

### Por dentro

- **`npm run release` publica nos dois sistemas.** O script só conhecia o instalador do Windows e
  recusava rodar em qualquer outro lugar; agora escolhe os arquivos pela plataforma
  (`.exe` + `.blockmap` + `latest.yml` no Windows, `.deb` + `latest-linux.yml` no Linux) e aplica a
  mesma exigência de manifesto: a versão do arquivo de canal tem de bater com a do `package.json` e
  apontar para o instalador desta versão.

---

## 2.0.16 — 2026-08-27 · trava de sessão de áudio e correção de vazamento em idle

### Correções Críticas

- **Eliminação de vazamento de áudio em background:** Corrigida uma condição de corrida no ciclo de vida de captura (`pill.ts` e `dictation.ts`) onde chamadas rápidas ou interrupções antes do término do `getUserMedia` assíncrono deixavam a stream de áudio do sistema/microfone gravando em segundo plano.
- **Identificador de sessão (`activeRecordId`):** A pílula agora rastreia o ID da sessão ativa e aborta instantaneamente qualquer captura cujas promises resolvam após o ditado ter sido cancelado ou finalizado.
- **Travas rígidas de fase no processo principal:** As funções `feedAudio`, `onSegment` e `onText` em `dictation.ts` agora rejeitam estritamente qualquer áudio ou texto que chegue fora da fase correspondente (`recording` / `transcribing`), impedindo digitação involuntária de sons de fundo (músicas do YouTube, chamadas, etc.) quando o app está inativo.

---

## 2.0.15 — 2026-08-27 · captura de som do computador (loopback de áudio)

### Novidades e Recursos

- **Captura de som do computador (loopback de sistema):** O Dito agora capta diretamente o áudio emitido pelo computador (mensagens de voz no WhatsApp Web, vídeos do YouTube, reuniões e qualquer aplicativo), mesmo com fones de ouvido conectados. O áudio do sistema é somado em tempo real com a voz do microfone no Web Audio API (descartando streams de vídeo para zero impacto de GPU/processamento).
- **Controle nos Ajustes:** Nova opção "Capturar som do computador" na aba Áudio das Configurações para ligar/desligar a qualquer momento.

---

## 2.0.14 — 2026-08-26 · correção do "Apertar Enter depois de colar"

### Correções

- **Disparo real da tecla Enter (pressEnter):** A opção "Apertar Enter depois de colar" agora dispara a tecla virtual `VK_RETURN` via `SendKeyStroke` no Win32 (e `sendEnter` / `XK_Return` no Linux) em vez de enviar o caractere `\r` como glifo Unicode (`KEYEVENTF_UNICODE`). Isso permite que terminais (Windows Terminal, conhost), IDEs (Antigravity IDE, VS Code), navegadores e CLIs reconheçam o Enter como submissão de comando.
- **Temporização segura pós-colagem:** Adicionado intervalo de segurança (50 ms) para garantir que a aplicação em primeiro plano processe a colagem da área de transferência antes de receber o Enter, evitando perda de caracteres ou execuções prematuras.
- **Qualidade de código:** Dívidas técnicas de formatação e limites de linhas de arquivo zeradas no portão de qualidade (`npm run quality`).

---

## 2.0.13 — 2026-08-26 · suporte a idioma no Whisper e migração de histórico

### Novidades e Correções

- **Suporte a idioma no Whisper (W3b):** O Whisper agora recebe explicitamente o idioma ativo (ex.: `pt`), evitando alucinações e transcrições em inglês para falas em português.
- **Migração do histórico legado (W9):** O histórico do Dito 1.x (`historico.jsonl`) agora é migrado automaticamente para `history.jsonl` na inicialização, preservando todos os ditados anteriores.
- **Build oficial Windows:** Empacotamento para Windows com todas as melhorias recentes (autostart, correções de áudio/microfone e compatibilidade).

---

## 2.0.12 — 2026-08-26 · abrir junto com o sistema no Linux

### 1. Opção "Abrir junto com o sistema" (Autostart)

O Dito agora tem a opção de iniciar automaticamente com a sessão no Linux, minimizado na bandeja.

- **Interface:** Adicionado toggle "Abrir junto com o sistema" na aba Atalho das configurações.
- **Implementação:** Usa a API nativa `app.setLoginItemSettings()` / `app.getLoginItemSettings()` do Electron, integrando com o padrão XDG autostart (`~/.config/autostart`).
- **Persistência:** O estado reflete a configuração real do sistema operacional e persiste entre reinícios.

### 2. Correção de dois cliques para parar o áudio no modo alternar (X11)

- **Causa:** No loop de eventos do addon nativo X11 (`native/src/key_hook_x11.cpp`), a checagem periódica `XQueryKeymap` sobrescrevia `binding.last_down = physical`. Quando o usuário apertava a tecla para parar, o polling físico marcava o estado como `down=true` antes do `XNextEvent` retirar o evento `KeyPress` da fila. O `XNextEvent` então comparava `last_down == down` e descartava o evento como repetição falsa de auto-repeat.
- **Correção:** O estado de borda (`last_down`) agora é mantido exclusivamente pela fila de eventos reais (`KeyPress` e `KeyRelease`), eliminando o descarte indevido do comando de parada no modo alternar.

---

## 2.0.11 — 2026-08-25 · o microfone parou de "desligar sozinho"

Dois defeitos diferentes davam a mesma sensação: o ditado morria no meio sem avisar. Nenhum dos
dois era do microfone — os dois eram do app mentindo sobre o que estava fazendo.

### 1. "Sem som" disparava em toda pausa de 2 segundos

A pílula ficava **inteira vermelha** ("Sem som — nada está chegando do microfone") sempre que o RMS
passava 2 s abaixo de `0.006`. Quem via aquilo desligava o ditado achando que o microfone tinha
caído — mas o áudio continuava chegando e a transcrição saía inteira. O aviso mentia.

**Medido nesta máquina antes de mexer**, 93 blocos de 4096 quadros a 48 kHz em cada caso:

| microfone | blocos nulos | RMS máximo |
|---|---|---|
| funcionando, sala em silêncio | **0 de 93** | 5,8e-3 |
| mudo | **93 de 93** | 0 |

Os dois casos ficam **inteiros** abaixo de `0.006`: o limiar não separava mic quebrado de pessoa
calada. No `app.log` real ele disparou em **56 dos 159 ditados** (35%), quase sempre aos 3,3 s
(apertou a tecla e pensou antes de falar) ou nos últimos segundos (parou de falar e foi apertar a
tecla). Num único ditado de 317 s disparou 34 vezes.

**Agora** o aviso só aparece quando o sinal chega **digitalmente nulo** por 2 s — que é o que
"nada está chegando" quer dizer. Pausa deixou de ser falha, e o aviso passou a valer também no meio
do ditado (mute no botão do headset), coisa que o limiar não conseguia fazer sem gritar sem parar.
A regra virou `src/shared/mic-signal.ts`, fora do renderer, para poder ter portão.

### 2. O ditado parava de gravar aos 3 minutos e continuava escrito "Ouvindo"

O renderer tinha um teto de 180 s que **parava de enfileirar áudio e não avisava ninguém**: a
pílula seguia dizendo "Ouvindo", a onda seguia se mexendo, e nada mais era transcrito. É o defeito
que atinge exatamente o modo *alternar*, que a documentação vende como "reunião sem limite de
tempo". O log tem um ditado de 317 s que caiu nisso.

O comentário justificava o teto como proteção contra buffer sem limite — **não procedia**:
`flushPending` despacha a cada segundo e o `AudioChunker` nunca guarda mais que uma janela de 8 s.
Não havia buffer crescendo.

**Agora** não há teto no renderer. O teto que existe é honesto e mora no processo principal:
`MAX_TAKE_MS` (1 h, `DITO_MAX_TAKE_MS` para portão) **encerra o ditado de verdade** — transcreve,
entrega o texto e registra no log. Ele existe porque o modo *alternar* não tem key-up para
terminar, e uma tecla esquecida gravaria para sempre.

### Como foi verificado

- **Portão novo `quality/mic-signal.ts`**, na camada `sinal` do `npm run verify`. Prova que 5 min de
  sala silenciosa e um ditado com 80 s de pausa **não** acusam nada, que microfone mudo é acusado em
  3,3 s, que mute no meio do ditado é pego, e que o aviso some quando o som volta. Tem contraprova
  embutida: roda a regra antiga contra a mesma fixture e exige que ela dispare.
- **Provado nos dois sentidos** (`CLAUDE.md`): com o limiar antigo de volta no lugar de "sinal
  nulo", o portão reprova com exit 1; com a correção, exit 0.
- **Ditado longo medido no app real**, pílula compilada carregada num Electron com microfone falso
  do Chromium: 200 s de gravação entregaram **198,1 s de áudio**, sem corte aos 180 s. Com o teto
  antigo recolocado, a mesma medição trava (registro abaixo, na contraprova).
- `npx tsc --noEmit` e `npx oxlint`: exit 0. `quality/chunker.ts`: PASSA.

### O que este release **não** provou

`npm run verify` inteiro exige `pwsh`, que não existe nesta máquina Linux — as camadas `nativo`,
`tecla`, `segurar`, `fumaça`, `colagem` e `mutação` **não rodaram**. O portão `regras do projeto`
roda e está **vermelho com 5 itens herdados do porte X11** (comentários de mais de uma linha em
`paths.ts`, `input_x11.h` e `key_hook_x11.h`; `input_x11.cc` com 287 linhas para um teto de 260) —
nenhum deles tocado aqui. Está registrado em `PENDENCIAS.md`.


## 2.0.10 — 2026-08-24 · agora também no Linux

### Novidades

- **Port para Linux (X11), empacotado como `.deb`.** Mesma versão do Windows, mesmo comportamento:
  segurar ou alternar a tecla, gravar, transcrever offline e o texto cair onde o cursor está. O
  `.deb` é instalado com `apt` e puxa as dependências sozinho.

### Como o Linux resolve o que o Windows resolvia de outro jeito

Não foi tradução linha a linha do Win32 — cada peça usa o que o X11 tem de melhor:

- **Tecla global com supressão** — `XGrabKey` na janela raiz, registrada em todas as combinações de
  Caps/Num/Scroll Lock. Entrega press e release e a tecla não vaza para o app de baixo, sem precisar
  de root nem do grupo `input` (era o que o `WH_KEYBOARD_LL` com `suppress` fazia).
- **`XkbSetDetectableAutoRepeat`** — sem isso o X11 forja um release antes de cada repetição e o
  modo *segurar* nunca segura. Além disso o addon só emite uma borda quando o estado **muda**: a
  repetição automática chegava a desligar a gravação sozinha no modo *alternar*.
- **Estado físico da tecla** — `XQueryKeymap` a cada 100 ms, no lugar da leitura de estado do
  Windows. É a rede de segurança para um key-up perdido, e é o árbitro que ressincroniza a borda.
- **Janela alvo** — `_NET_ACTIVE_WINDOW`, `WM_CLASS` e `_NET_WM_NAME` no lugar de
  `GetForegroundWindow`/`GetClassNameW`.
- **Roubo de foco: não existe.** O Windows precisa de `SetForegroundWindow` + `AttachThreadInput`
  porque o sistema não entrega o primeiro plano a quem não o tem. No X11 isso não é problema, e a
  pill já é `focusable: false` — então esse bloco inteiro simplesmente não foi portado. Se o foco
  mudou durante o ditado, a colagem é **recusada** em vez de forçada, e o texto vai para a área de
  transferência.
- **Terminal cola com Ctrl+Shift+V** — é a mesma armadilha do `conhost` no Windows, com outra cara.
  `xterm`, `urxvt` e `rxvt`, que não têm esse atalho, recebem o texto **digitado** tecla a tecla.
- **Acento pt-BR** — `KEYEVENTF_UNICODE` não existe aqui. O addon remapeia temporariamente um
  keycode livre para o keysym de cada caractere e restaura o mapa no fim (é o que o `xdotool` faz).
- **Área de transferência** — fica com o Electron, que já é dono da seleção X11. O addon só
  sintetiza o atalho. Menos C++, menos chance de erro.

### Onde os arquivos ficam no Linux

Modelos e histórico em `~/.local/share/dito`, configuração em `~/.config/dito`, log em
`~/.local/state/dito` — XDG, como manda o sistema. Deixar 3 GB de modelo dentro de `~/.config`
seria errado. No Windows nada mudou.

### Correção no pacote antes de publicar

- **`libatspi2.0-0t64` faltava no `depends`.** O `deb.depends` do electron-builder **substitui** o
  default inteiro, e a lista montada à mão deixou essa de fora — mas o binário do Electron linka
  contra `libatspi.so.0`. Numa máquina onde a lib não estivesse presente, o `apt install` passaria e
  o app não abriria. Derivado agora do próprio binário com `ldd` + `dpkg -S`, não de uma lista
  copiada.

### Como foi verificado

- `npx node-gyp build` gera `dito_linux.node` — exit 0.
- Gate do hook (`xdotool key F10` passa pelo XTest e é capturado pelo grab): `installed: true`,
  bordas down/up corretas, `seen` e `pumps` subindo — exit 0.
- Gate de colagem sob Electron real (`quality/paste-linux.js`): abre o `xed`, lembra o alvo
  (`Xed`, `kind: gui`, é o ativo), cola `"teste com acentuação, ção e ênfase"` pela área de
  transferência e digita `" | digitado: ação"` por XTest; salva e o arquivo em disco contém os dois
  exatos — exit 0.

### Correções

- **O último trecho ainda saía colado no anterior** — `"tá ficando.Tá show"` em vez de
  `"tá ficando. Tá show"`. A 2.0.9 corrigiu a emenda dos trechos do meio e deixou passar a do fim,
  que é justamente a que todo ditado tem.

## 2.0.9 — 2026-08-24

### Correções

- **O texto chegava duas vezes.** O que já tinha sido digitado enquanto você falava era digitado de
  novo, inteiro, quando o ditado terminava. Agora o fim do ditado manda **só o que faltou**.
- **Os trechos saíam colados** na emenda — `"quando eu.Tô falando"` em vez de `"quando eu. Tô
  falando"`. O espaço que separa um trecho do outro estava sendo descartado.

O ditado inteiro continua indo para o `Ctrl+V`, sempre: se a colagem der errado em qualquer ponto,
está tudo lá para colar à mão.

## 2.0.8 — 2026-08-24

Nenhuma mudança de comportamento em relação à 2.0.6. Publicada, como a 2.0.7, só para exercitar o
botão de atualizar.

## 2.0.7 — 2026-08-24

Nenhuma mudança de comportamento em relação à 2.0.6. Publicada para exercitar o fluxo novo de
atualização — baixar em segundo plano, mostrar o progresso, e o app fechar e reabrir sozinho.

## 2.0.6 — 2026-08-24

### Mudou

- **Atualizar virou um clique, e o app volta sozinho.** Antes ele instalava escondido quando você
  fechava o Dito — e não reabria: da sua cadeira, o app simplesmente sumia. Agora a versão nova baixa
  em segundo plano, a tela mostra **quanto já baixou**, e o botão vira **"Reiniciar e atualizar"**.
  Ao clicar, o Dito fecha, instala e **abre de novo sozinho**.
- **Fechar o Dito não mexe mais na instalação.** Sair é só sair.

Mesmo comportamento do Slime Animes, de onde a regra veio: *só encerra depois que o atualizador
provar que subiu — fechar sozinho e não atualizar nada é o pior resultado possível.*

## 2.0.5 — 2026-08-24

### Correções

- **Trocar o modo não fazia nada até reiniciar o app.** A escolha era gravada, mas a tecla continuava
  com o modo que valia quando o app subiu — daí a sensação de que o "alternar" voltava sozinho para
  "segurar". A tecla passou a consultar o modo a cada toque.
- **Trocar para um modelo que não é do tipo Parakeet derrubava o motor.** Escolher o Whisper deixava
  o app sem transcrever nada até voltar ao modelo anterior. O caminho de cada família de modelo já
  existia, mas o app procurava um arquivo que só o Parakeet tem antes de chegar nele.

### Mudou

- **O modo virou um botão**, em vez de uma lista para abrir: são dois estados, então um clique
  alterna entre "alternar" e "segurar".

## 2.0.4 — 2026-08-23

Nenhuma mudança de comportamento em relação à 2.0.3. Publicada para exercitar a atualização pelo
botão **Procurar atualização** com uma versão nova de verdade do outro lado.

## 2.0.3 — 2026-08-23

### Correções

- **A tela de Atualizações não achava versão nenhuma** e mostrava um bloco de erro HTTP cru no lugar
  da situação. O app procurava a versão direto no GitHub, mas o repositório é privado: sem
  credencial o GitHub responde 404 e ainda sugere que o token está errado — quando não existia token
  algum. Agora a busca passa pelo servidor do Dito, que guarda a credencial; o app continua sem
  segredo nenhum dentro dele.
- **As versões eram publicadas sem o arquivo que descreve a atualização.** Mesmo com o acesso
  resolvido, o app pararia no passo seguinte. Publicar agora recusa sair sem esse arquivo.
- **O erro na tela virou frase de gente.** "não consegui falar com o servidor de atualização" em vez
  do despejo do protocolo. O detalhe técnico continua inteiro no log.

### Por dentro

- Camada nova no `npm run verify`: **feed** — confere que o app aponta para o servidor certo, que ele
  responde com a versão e que o instalador anunciado é alcançável.
- O instalador **não passa mais pelo servidor**: ele devolve um endereço temporário e os 109 MB vêm
  direto do CDN do GitHub.

### Atenção ao instalar

Quem estiver na **2.0.1 ou 2.0.2 precisa instalar a 2.0.3 à mão** — o endereço de atualização fica
gravado dentro do pacote, e essas duas nasceram apontando para o lugar errado. Da 2.0.3 em diante a
atualização é sozinha.

## 2.0.2 — 2026-08-23

### Novidades

- **O texto sai enquanto você fala, sem cartão no meio do caminho.** O cartão de revisão foi
  removido: cada trecho de 8 segundos é digitado direto no alvo assim que fica pronto, e só
  digita se aquela janela ainda estiver em primeiro plano — trocar de janela no meio da fala
  não faz o texto cair no lugar errado.
- **O texto sempre vai também para a área de transferência** — mesmo quando é digitado no
  destino, um `Ctrl+V` recupera. Assim, nenhum ditado se perde quando a janela ativa não aceita
  o texto e a colagem falha em silêncio.
- **Texto ao vivo na pílula ficou branco**, mais legível que o cinza apagado de antes.
- **A pílula fica por cima mesmo depois** de um Meet ou overlay de jogo assumir o modo
  "sempre no topo" — ela volta a se reafirmar acima de quem chegou depois.

### Correções

- **Os dados do app podiam ir parar numa pasta relativa** em vez de `%APPDATA%\dito`, levando junto
  o log e os modelos. Acontecia quando a variável de ambiente que aponta a pasta existia vazia.

### Conhecido

O modo **segurar** tem um portão de teste intermitente sob repetição muito rápida. O modo padrão é
o alternar, que está provado. Detalhes e evidência em `plano.md`.

## 2.0.1 — 2026-08-23

### Novidades

- **O texto aparece enquanto você fala.** O áudio é cortado em janelas de 8 segundos, sempre no
  ponto mais silencioso para não partir palavra, e cada janela transcrita aparece na pílula.
- **Cartão de revisão.** Quando não há campo onde colar, o texto abre num cartão em vez de se
  perder: `Enter` envia, `Shift+Enter` quebra linha, `Tab` descarta. Dá para deixá-lo sempre
  ligado ou sempre desligado nos Ajustes.
- **Aviso de microfone mudo.** Se nada chega da entrada por 2 segundos, a pílula fica vermelha na
  hora, em vez de você descobrir no fim.
- **Devolve a área de transferência** depois de colar, e opcionalmente aperta `Enter` no fim — útil
  para ditar um comando no terminal.
- **Atualização automática** ligada, com verificação manual nos Ajustes.
- **Interface em português e inglês**, seguindo o idioma do sistema.

### Correções

- **A tecla não fazia nada na 2.0.0.** O addon nativo e o processo principal usavam nomes
  diferentes para a mesma ação. Agora o nome tem um dono só e o empacotamento recompila o addon
  sempre.
- **O modo segurar podia ficar gravando para sempre** se o sistema engolisse o soltar da tecla.
  Passou a existir um teto de duração e a checagem do estado físico.
- **A tecla ficava sem resposta por 1,6 s** depois de um ditado vazio.
- **O texto podia cair na janela errada:** a troca de foco no Windows é assíncrona e a digitação
  começava antes de ela terminar. Agora a colagem espera o foco chegar e desiste se ele não chegar.
- **O cartão de revisão abria vazio** quando a janela ainda não tinha carregado.

### Por dentro

- O projeto é **TypeScript**. O contrato de configuração, de IPC e de modelos vive em `src/shared/`,
  então uma opção de tela que o código não aceita deixa de compilar.
- O processo principal virou 15 módulos de um assunto cada; a partida tem 46 linhas.
- As telas rodam com `contextIsolation`, sem acesso a Node.
- `npm run verify` roda 13 camadas de portão, cada uma provada também no sentido contrário.
- **Obsidian foi removido**: o Dito é só transcrição.

### Não incluído

Linux. O addon de atalho global e colagem é Win32; sem o equivalente em X11 o app abriria mas não
ouviria a tecla nem colaria em lugar nenhum. O que falta está em `PENDENCIAS.md`.

---

## 2.0.0 — 2026-08-23 (despublicada)

Primeira versão em Electron, trocando Whisper com CUDA por **Parakeet TDT 0.6B v3 em ONNX**: sem
compilar kernel, rodando na CPU mais rápido do que a versão anterior rodava na GPU, com pontuação e
maiúsculas vindas do modelo.

Saiu com o defeito da tecla descrito acima e virou rascunho no mesmo dia.

---

## 1.x — Flutter

O histórico da versão em Flutter está no histórico do Git. O que aprendemos nela e continua valendo
foi preservado em `docs/heranca/`.
