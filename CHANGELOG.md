# CHANGELOG — Dito

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
