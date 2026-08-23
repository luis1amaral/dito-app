# CHANGELOG — Dito

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
- `npm run verify` roda 12 camadas de portão, cada uma provada também no sentido contrário.
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
