# Paridade — o que o Electron tem de fazer igual, e quem prova

Este arquivo existe para que **"não quebrei nada" seja uma lista conferível**, e não uma sensação.

A régua é a `plano/REGRAS.md`: a 1.7.0 saiu com `analyze` limpo, 220 testes e 16 goldens verdes — e
**morria antes da primeira linha de log**. Portanto: nenhuma linha aqui é dada por pronta sem que o
binário tenha subido, e **nenhum portão entra sem ter sido visto reprovando**.

Cada linha veio de um teste que existe hoje no Flutter (`dito-app/test/`) ou de um defeito que já
aconteceu de verdade (`plano/referencia/armadilhas.md`).

**Estados:** `OK` provado · `PENDENTE` sem código ainda · `BLOQUEADO` depende de máquina/porte.

---

## Novas linhas desta versão

| # | Comportamento | Quem prova | Estado |
|---|---|---|---|
| N1 | O contrato compila (config, IPC, modelos) | `npx tsc --noEmit` | **OK** |
| N2 | Sem comentário de mais de 1 linha, arquivo > 260 linhas, canal órfão | `quality/code-quality.ts` | **OK** |
| N3 | Texto aparece durante a fala | `audio-chunker.ts` (falta portão) | PENDENTE |
| N4 | Aviso de microfone sem som | `pill.ts`, 2 s de silêncio | PENDENTE |
| N5 | Modelo é baixado em máquina limpa, com retomada | `quality/models.ts` | **OK** |
| N6 | Idiomas pt-BR e en sem texto fixo | `shared/i18n.ts` | em andamento |

## A. Motor — transcrição

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| A1 | Transcreve pt-BR com o texto certo | `native_transcription_test` | `qualidade/motor.mjs` (WER ≤ 10%) | **OK** |
| A2 | Entrega pontuação e maiúscula | novo (era risco do plano) | `motor.mjs` `exigePontuacao` | **OK** |
| A3 | Aceita 48 kHz do microfone e reamostra | novo (`getUserMedia` dá 48 k) | fixture `fala-48k.wav` | **OK** |
| A4 | Falta de arquivo do modelo falha alto | `model_manager_test` | mutação `modelo-ausente` | **OK** |
| A5 | Números por extenso | critério do portão 1 | fixture a gravar | PENDENTE |
| A6 | Termos em inglês no meio do português | critério do portão 1 | fixture a gravar | PENDENTE |
| A7 | Ditado longo **não estoura 2 GiB** | comentário do Orca (#7925) | `audio-chunker.ts`: janela de 8 s cortada no silêncio | **OK** (falta o teste de 3 min, W2) |
| A8 | Modelo carrega **uma vez** e fica quente | medido: 10,5 s de carga | fumaça mede 2º ditado | PENDENTE |
| A9 | Baixa o modelo na 1ª execução, com sha256 | `model_manager_test` | `models.js`: catálogo do Orca inteiro, sha256 por arquivo, cópia local se já existir | **OK** |
| A10 | Silêncio não vira texto alucinado | `sound_tags_test`, `gain_test` | medido: 3 s de silêncio → texto vazio, sem `[Música]` | **OK** |
| A11 | Alarme de silêncio com histerese | `silence_alarm_test` | porte do `silence_alarm` | PENDENTE |

## B. Tecla — F9

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| B1 | F9 funciona **fora** do app, em qualquer janela | `hotkey_machine_test` | `quality/native.mjs` + ciclo real de ditado no log | **OK** |
| B2 | A tecla continua funcionando depois da 1ª vez | `hotkey_repeat_test` (armadilha real) | `hold.mjs`: 5 ciclos seguidos | **OK** |
| B3 | Tecla não fica "presa" | `hotkey_stuck_test` | `hold.mjs`: teto de duração encerra sozinho | **OK** |
| B4 | Modo alternar (padrão) e modo segurar | decisão do dono | `hotkey.mjs` (alternar) e `hold.mjs` (segurar) | **OK** |
| B5 | Hook em **thread própria com message pump** | armadilha `LowLevelHooksTimeout` | `native.mjs` exige `pumps > 0` e `installed` | **OK** |

## C. Colagem — o que dá valor ao Dito

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| C1 | Cola em janela Chromium (WhatsApp, navegador) | `paste_sequence_test` | `paste-targets.mjs` | **OK** |
| C2 | Cola em **`cmd.exe` cru** (modo cru) | armadilha medida | `quality/paste-wiring.mjs` + `raw-target.mjs` | **OK** |
| C3 | Acento pt-BR não corrompe | sonda já mede | `paste-wiring.mjs` compara byte a byte | **OK** |
| C4 | A colagem espera o foco trocar antes de digitar | achado hoje: ia para a janela errada | `input.cc` + `paste-targets.mjs` | **OK** |
| C5 | Alvo capturado na **descida** da tecla | `focus_target_test` | `addon.cc`: `RememberTarget()` no `edge.down` | **OK** |
| C6 | Multilinha não vira N execuções no CLI | sonda já mede | mesma sonda | reusável |

## D. Janela — pílula, ajustes

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| D1 | App **sobe** e registra `boot completo` | 1.7.0 (`0xC0000005`) | `quality/smoke.ps1`, prova amarrada ao PID | **OK** |
| D2 | Sem faixa preta: < 3% de preto puro | armadilha 4.13 | `smoke.ps1` no quadro do `capturePage` — medido 0% | **OK** |
| D3 | Pílula visível por cima de um `cmd.exe` | memória do alfa/DWM | `PrintWindow` externo | PENDENTE |
| D4 | Clique-através na pílula | `hud_visibility_test` | roteiro manual + sonda | PENDENTE |
| D5 | Esconder = recortar vazio, **nunca** desmapear | armadilha 4.3 | teste da política de overlay | PENDENTE |
| D6 | Recorte usa coordenada de janela, não de cliente | armadilha 4.14 | `hud_shape_test` portado | PENDENTE |
| D7 | Janela não pisca ao esconder | armadilha real | captura de 3 quadros seguidos | PENDENTE |
| D10 | **Sem erro de JS no renderer** | achado hoje: tela desenha e a parte viva morre | `smoke.ps1` reprova em `[console] Uncaught` | **OK** |
| D8 | Abre **sempre** só na bandeja (decisão do dono) | armadilha 4.15 | `smoke.ps1` reprova se abrir janela | **OK** |
| D9 | Ícone volta se o Explorer reiniciar | `TaskbarCreated` | roteiro: matar/subir Explorer | PENDENTE |

## E. Estado e fluxo

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| E1 | Máquina de estado do ditado | `controller_test`, `hud_state_test` | teste unitário | PENDENTE |
| E2 | Fase travada é detectada e sai sozinha | `stuck_phase_test` | teste unitário | PENDENTE |
| E5 | Histórico lê e escreve | `library_reader_test` | teste unitário | PENDENTE |

## F. Config, dados e idioma

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| F1 | Config lê/grava sem perder campo | `config_codec_test` | teste unitário | PENDENTE |
| F2 | Config antiga migra sem quebrar | `config_migration_test` | teste com config da 1.7.x | PENDENTE |
| F3 | Textos em pt-BR e en | `l10n_test` | teste unitário | PENDENTE |
| F4 | Tokens visuais (cor, raio, espaço) | `ui_tokens_test` | teste + golden | PENDENTE |
| F5 | Ícone/fonte sem glifo faltando | `glyph_guard_test` | teste unitário | PENDENTE |
| F6 | Duração formatada | `duration_format_test` | teste unitário | PENDENTE |

## G. Empacotamento

| # | Comportamento | Vem de | Quem prova | Estado |
|---|---|---|---|---|
| G1 | O **instalador** instala e o app instalado sobe | `fumaca_instalador.ps1` | `smoke.ps1 -Exe <instalado>` rodou e passou | **OK** |
| G2 | Auto-update encontra e aplica a versão nova | 1.7.0 despublicada | `electron-updater` em canal de teste | PENDENTE |
| G3 | Não empacota se qualquer portão reprovar | `construir.ps1` | `verificar.ps1` no build | PENDENTE |

## H. Linux — anotado, não feito

Fica registrado em `PENDENCIAS.md` e é executado **na máquina Linux** (decisão do dono):
`XGrabKey` exclusivo por processo · `hide()` viola a armadilha 4.3 · `clearHitRect`/`forceRepaint`
sem par no GTK · publicação no APT parada na 1.6.8.

---

## Como se usa

```
pwsh -File qualidade/verificar.ps1          # roda tudo, imprime a tabela, devolve exit code
node qualidade/motor.mjs                    # só o motor (rápido)
node qualidade/mutacao.mjs                  # prova que os portões reprovam
```

**Regra de entrada:** uma linha só sai de `PENDENTE` quando (1) a checagem existe, (2) ela passou e
(3) ela foi **vista reprovando** com o defeito recolocado. Sem os três, continua PENDENTE.
