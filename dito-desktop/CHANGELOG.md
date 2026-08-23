# CHANGELOG — dito-desktop

## 2.0.0 — 2026-08-23

Reescrita do Dito: sai Flutter + Whisper/CUDA, entra Electron + Parakeet/ONNX. O produto é o mesmo
e mais simples: **aperta F9, fala, o texto é digitado onde o cursor estava.** Só transcrição.

### Por quê

O Dito compilava **141 kernels CUDA** por horas para gerar um download extra de 290 MB — e mesmo
assim não cobria RTX 50xx. O Parakeet TDT 0.6B v3 int8 em ONNX é binário pronto, **zero
compilação**, e em CPU roda mais rápido do que o Whisper rodava em GPU. Numa única sessão anterior
apareceram seis defeitos em produção, quatro deles do malabarismo de uma janela só trocando de papel
— coisa que existe porque o Flutter lida mal com várias janelas.

### O que foi feito

**Motor** — `sherpa-onnx-node` 1.13.6 (Apache-2.0) com Parakeet TDT v3 int8 (CC-BY-4.0, NVIDIA),
numa `worker_thread` para não travar o processo principal. Decodifica em janelas de 20 s.

**Modelos** — catálogo completo do Orca, **10 modelos locais** (os 2 de nuvem ficaram de fora: o
Dito é 100% local). Cada um com revisão fixada no Hugging Face, tamanho e **sha256 por arquivo**.
O padrão vem sozinho na primeira execução; os outros só se o usuário quiser. **Não é possível apagar
o último modelo instalado** — para apagar um, é preciso ter outro.

**Atalho e colagem** — addon N-API em `native/`, portado de `packages/dito_win32/windows`:
`key_hook.cpp` e `key_table.cpp` foram **inteiros**, sem uma linha alterada; a colagem virou
`input.cc`. `WH_KEYBOARD_LL` em thread própria com message pump próprio, e `SendInput` UNICODE.

**Interface** — janela de desktop com barra lateral (Início, Atalho, Áudio, Modelos, Histórico) e
pílula de estado com forma de onda. Ícones de bandeja com estado reusados do Dito antigo.

**Abre sempre na bandeja.** Nunca abre janela sozinho: só no clique da bandeja ou ao rodar de novo.

### Como foi verificado

`npm run verify` — **exit 0**, cinco camadas:

```
PASSA      motor (regressao por fixture)     WER 0,0% em 16 kHz e 48 kHz
PASSA      mutacao (portao reprova?)         3 defeitos plantados, 3 pegos
PASSA      nativo (hook instala?)            installed=true, pumps>0, erro Win32 0
PASSA      fumaca (o app sobe?)              bandeja sem janela · 0% preto · sem erro de JS
PASSA      colagem (cmd.exe cru)             texto e acento intactos em modo cru
```

Medidas: modelo carrega em ~7–13 s (uma vez, fica quente); transcrição a **5–8× tempo real** em CPU;
instalador de 109 MB.

### Armadilhas novas, pagas nesta sessão

| Sintoma | Causa provada | Regra |
|---|---|---|
| Portão de fumaça verde com a janela vazia | `PrintWindow(PW_RENDERFULLCONTENT)` **não captura** superfície composta na GPU do Chromium | Medir a tela do Electron só por `capturePage()` |
| `capturePage()` nunca resolvia, alternando passa/falha | Chromium **estrangula o desenho** de janela coberta e a captura fica pendurada | `show()` + `focus()` e `backgroundThrottling: false` antes de capturar |
| Portão dizia que bootou antes da hora | Detecção por **contagem de linhas** casava com `boot completo` de rodada anterior | Amarrar a prova ao **PID** do processo que o portão subiu |
| Erro de JS passava batido | Contagem de pixel não muda: a tela desenha e a parte viva morre | Portão reprova em `[console] Uncaught` no log |
| Cola não achava o `cmd.exe` | Este Windows usa **Windows Terminal** como host padrão: não existe `ConsoleWindowClass` | Subir o alvo cru pela receita da `sonda_colagem.ps1` |
| `dito_win32.node` sumia do build | `LNK1103` de objeto velho | Build limpo depois de renomear fonte |

Também descoberto lendo o Orca: **decodificar um ditado inteiro numa chamada só faz o tensor crescer
com a duração até estourar ≥2 GiB e derrubar o app** (issue #7925 deles).

### Licenças

`stablyai/orca` é **público e MIT** (`gh repo view`), então o que veio de lá é cópia legítima com o
aviso preservado — bem diferente do tema do Alethe, que é **AGPL** e contaminaria o Dito. Vieram do
Orca: o resample, o catálogo de modelos, o formato do gerenciador de download e a configuração dos
recognizers por tipo. O Dito segue livre para ser MIT.

### O que **não** está pronto

Está tudo em `PENDENCIAS.md`, com destaque para: Linux inteiro (o addon nativo não atravessa),
auto-update nunca exercitado, ditado de 3 minutos nunca gravado, e 9 dos 10 modelos nunca rodados.
