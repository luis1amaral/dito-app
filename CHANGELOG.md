# CHANGELOG — Dito

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
