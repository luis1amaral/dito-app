# Paridade — o que precisa funcionar, e quem prova

Este arquivo existe para que **"não quebrei nada" seja uma lista conferível**, e não uma sensação.

A régua vem de um episódio concreto: a 1.7.0 saiu com o analisador limpo, 220 testes e 16 goldens
verdes — e **morria antes da primeira linha de log**. Portanto: nenhuma linha aqui é dada por pronta
sem que o binário tenha subido, e **nenhum portão entra sem ter sido visto reprovando**.

Cada linha veio de um teste que existia na versão 1.x em Flutter ou de um defeito que já aconteceu
de verdade — os dois estão no histórico do Git.

**Estados:** `OK` provado · `PENDENTE` sem portão ainda · `BLOQUEADO` depende de máquina/porte.
Onde a coluna "Quem prova" cita um arquivo de `quality/`, ele roda em `npm run verify`.

---

## Contrato e regras do projeto

| # | Comportamento | Quem prova | Estado |
|---|---|---|---|
| N1 | O contrato compila (config, IPC, modelos) | `npx tsc --noEmit` | **OK** |
| N2 | Sem comentário de mais de 1 linha, arquivo acima de 260 linhas, canal órfão | `quality/code-quality.ts` | **OK** |
| N3 | Texto aparece durante a fala | `quality/chunker.ts` (corte em janelas) | **OK** |
| N4 | Aviso de microfone sem som só quando o sinal é nulo | `quality/mic-signal.ts` | **OK** |
| N5 | Modelo é baixado em máquina limpa, com retomada e sha256 | `quality/models.mts` | **OK** |
| N6 | Toda chave usada nas telas tem texto em pt-BR e en | `quality/shared.ts` | **OK** |
| N7 | As telas compilam | `electron-vite build`, camada `bundle` | **OK** |

## A. Motor — transcrição

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| A1 | Transcreve pt-BR com o texto certo | teste da 1.x | `quality/engine.mjs` (WER ≤ 10%) | **OK** |
| A2 | Entrega pontuação e maiúscula | risco levantado no porte | `engine.mjs`, `requirePunctuation` | **OK** |
| A3 | Aceita 48 kHz do microfone e reamostra | novo (`getUserMedia` dá 48 k) | fixture `fala-48k.wav` | **OK** |
| A4 | Falta de arquivo do modelo falha alto | teste da 1.x | mutação `modelo-ausente` | **OK** |
| A5 | Números por extenso | critério do portão 1 | fixture a gravar | PENDENTE |
| A6 | Termos em inglês no meio do português | critério do portão 1 | fixture a gravar | PENDENTE |
| A7 | Ditado longo **não estoura 2 GiB** | comentário do Orca (#7925) | `audio-chunker.ts`: janela de 8 s cortada no silêncio | **OK** (falta o teste de 3 min, W2) |
| A8 | Modelo carrega **uma vez** e fica quente | medido: 10,5 s de carga | fumaça mede 2º ditado | PENDENTE |
| A9 | Baixa o modelo na 1ª execução, com sha256 | teste da 1.x | `quality/models.mts`: catálogo inteiro, sha256 por arquivo, cópia local se já existir | **OK** |
| A10 | Silêncio não vira texto alucinado | testes da 1.x | medido: 3 s de silêncio → texto vazio, sem `[Música]` | **OK** |
| A11 | Alarme de silêncio com histerese | teste da 1.x | `quality/mic-signal.ts`: mudo é acusado, pausa não | **OK** |

## B. Tecla — a global (padrão F10)

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| B1 | A tecla funciona **fora** do app, em qualquer janela | teste da 1.x | `quality/native.mjs` (Windows e Linux) + ciclo real no log | **OK** |
| B2 | A tecla continua funcionando depois da 1ª vez | armadilha real da 1.x | `hold.mjs`: 5 ciclos seguidos | **OK** |
| B3 | Tecla não fica "presa" | armadilha real da 1.x | `hold.mjs`: teto de duração encerra sozinho | **OK** |
| B4 | Modo alternar (padrão) e modo segurar | decisão do dono | `hotkey.mjs` (alternar) e `hold.mjs` (segurar) | **OK** |
| B5 | Hook em **thread própria com message pump** | armadilha `LowLevelHooksTimeout` | `native.mjs` exige `pumps > 0` e `installed` | **OK** |

## C. Colagem — o que dá valor ao Dito

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| C1 | Cola em janela Chromium (WhatsApp, navegador) | teste da 1.x | `paste-targets.mjs` | **OK** |
| C2 | Cola em **`cmd.exe` cru** (modo cru) | armadilha medida | `quality/paste-wiring.mjs` + `raw-target.mjs` | **OK** |
| C3 | Acento pt-BR não corrompe | sonda já mede | `paste-wiring.mjs` compara byte a byte | **OK** |
| C4 | A colagem espera o foco trocar antes de digitar | achado hoje: ia para a janela errada | `input.cc` + `paste-targets.mjs` | **OK** |
| C5 | Alvo capturado na **descida** da tecla | teste da 1.x | `addon.cc`: `RememberTarget()` no `edge.down` | **OK** |
| C6 | Multilinha não vira N execuções no CLI | sonda já mede | mesma sonda | reusável |

## D. Janela — pílula, ajustes

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| D1 | App **sobe** e registra `boot completo` | 1.7.0 (`0xC0000005`) | `quality/smoke.ps1`, prova amarrada ao PID | **OK** |
| D2 | Sem faixa preta: < 3% de preto puro | armadilha 4.13 | `smoke.ps1` no quadro do `capturePage` — medido 0% | **OK** |
| D3 | Pílula visível por cima de um `cmd.exe` | memória do alfa/DWM | `PrintWindow` externo | PENDENTE |
| D4 | Clique-através na pílula | teste da 1.x | roteiro manual + sonda | PENDENTE |
| D5 | Esconder = recortar vazio, **nunca** desmapear | armadilha 4.3 | teste da política de overlay | PENDENTE |
| D6 | Recorte usa coordenada de janela, não de cliente | armadilha 4.14 | roteiro manual | PENDENTE |
| D7 | Janela não pisca ao esconder | armadilha real | captura de 3 quadros seguidos | PENDENTE |
| D10 | **Sem erro de JS no renderer** | achado hoje: tela desenha e a parte viva morre | `smoke.ps1` reprova em `[console] Uncaught` | **OK** |
| D8 | Abre **sempre** só na bandeja (decisão do dono) | armadilha 4.15 | `smoke.ps1` reprova se abrir janela | **OK** |
| D9 | Ícone volta se o Explorer reiniciar | `TaskbarCreated` | roteiro: matar/subir Explorer | PENDENTE |

## E. Estado e fluxo

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| E1 | Máquina de estado do ditado | testes da 1.x | teste unitário | PENDENTE |
| E2 | Fase travada é detectada e sai sozinha | teste da 1.x | teste unitário | PENDENTE |
| E3 | Cancelar o ditado solta o microfone e para de enviar áudio | defeito real da 2.0.15 | `quality/audio-leak.mjs`, 4 cenários de corrida | **OK** |
| E4 | Emenda de trechos com o separador certo | defeito real da 2.0.9 | `quality/shared.ts` | **OK** |
| E5 | Histórico lê e escreve | teste da 1.x | teste unitário | PENDENTE |

## F. Config, dados e idioma

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| F1 | Config lê/grava sem perder campo | teste da 1.x | `quality/shared.ts`: `migrate` preserva e completa | **OK** |
| F2 | Config antiga migra sem quebrar | teste da 1.x | `quality/shared.ts`: campos e valores em pt-BR migram | **OK** |
| F3 | Textos em pt-BR e en | teste da 1.x | `quality/shared.ts`: chave de tela sem texto reprova | **OK** |
| F4 | Tokens visuais (cor, raio, espaço) | teste da 1.x | teste + golden | PENDENTE |
| F5 | Ícone/fonte sem glifo faltando | teste da 1.x | teste unitário | PENDENTE |
| F6 | Duração formatada | teste da 1.x | teste unitário | PENDENTE |

## G. Empacotamento

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| G1 | O **instalador** instala e o app instalado sobe | `fumaca_instalador.ps1` | `smoke.ps1 -Exe <instalado>` rodou e passou | **OK** |
| G2 | Auto-update encontra e aplica a versão nova | 1.7.0 despublicada | `quality/update-feed.mts` por plataforma + clique de ponta a ponta na 2.0.3 | **OK** |
| G3 | Não empacota se qualquer portão reprovar | `construir.ps1` | `verificar.ps1` no build | PENDENTE |

## H. Linux — feito na 2.0.10, provado desde então

| # | Comportamento | Quem prova | Estado |
|---|---|---|---|
| H1 | Atalho global sob X11, sem root | `quality/native.mjs` com o addon `dito_linux.node` | **OK** |
| H2 | Colagem e digitação com acento em janela real | `quality/paste-linux.js` (Electron + `xed`) | **OK** |
| H3 | Pacote `.deb` instala e atualiza pelo `apt` | repositório assinado em `apt.defaltm.com` | **OK** |
| H4 | Feed de atualização do Linux serve o `.deb` anunciado | `quality/update-feed.mts` | **OK** |
| H5 | A tecla abre **e fecha** o ditado, sem sobrar captura | `quality/hotkey-linux.mjs` no binário empacotado | **OK** |
| H7 | App sobe, pílula aparece, sem erro de JS | equivalente ao `smoke.ps1` ainda não existe aqui | PENDENTE |
| H6 | Pílula transparente sem compositor | depende do ambiente gráfico | BLOQUEADO |

---

## Como se usa

```bash
npm run verify              # roda tudo, imprime a tabela, devolve o exit code
npm run verify -- --rapido  # pula a camada de mutação, que é a mais demorada
npm run engine              # só o motor
npm run mutation            # prova que os portões reprovam
```

**Regra de entrada:** uma linha só sai de `PENDENTE` quando (1) a checagem existe, (2) ela passou e
(3) ela foi **vista reprovando** com o defeito recolocado. Sem os três, continua PENDENTE.
