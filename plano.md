# plano.md — o que falta

Escrito para ser executado **do zero, sem nada da conversa anterior**. Quem abrir isto consegue
terminar.

Projeto: `C:\Users\Luis\Desktop\Projetos\dito\dito-desktop`

---

## Antes de qualquer coisa

```bash
npm install
npm run addon      # precisa de MSVC + Windows SDK; faz build limpo sempre
npm run verify     # 13 camadas; exit 0 PASSA, 1 FALHA, 2 INCOMPLETO
```

**Regra que não se pula:** nada é dado por pronto sem `verify` em verde. INCOMPLETO nunca é verde.
Ao criar portão novo, prove-o **nos dois sentidos**: recoloque o defeito e exija que ele reprove.

Regras de escrita do projeto estão em `CLAUDE.md` (código e comentário em inglês, comentário de no
máximo 1 linha, texto de tela em pt-BR/en via `src/shared/i18n.ts`).

---

## 1. O portão `segurar` é intermitente (o mais urgente)

**Resolvido no caminho, e era defeito de PRODUTO:** o app gravava os dados em caminho **relativo**
dentro do projeto em vez de `%APPDATA%\dito`. Causa: `process.env['DITO_APPDATA'] ?? app.getPath(...)`
— o `??` só cai para o outro lado com `null`, então uma variável vazia vencia e `join('', 'dito')`
virava caminho relativo. Trocado por `||`. Isso derrubava `tecla`, `segurar` e `fumaca` juntos;
as duas primeiras voltaram a passar.

**O que sobrou:** `node quality/hold.mjs` passa e falha de forma **intermitente**, com mensagem
diferente a cada corrida (`up nao parou o ditado`, `a transcricao nao terminou`, `down nao iniciou`).

**O que o log do app mostra durante a falha:**

```
dictation: started    23:33:55.759
dictation: stopped    23:33:55.884   <- 125 ms depois, nao 1500
transcribed: 0 ms ""
dictation: started    23:33:57.448
...
CRASH Utility: crashed (exit -1)
```

**Leitura honesta:** o portão segura a tecla por 600 ms e repete cinco vezes em dez segundos — um
ritmo que nenhuma pessoa produz. Parte da falha é o produto recusando começar enquanto a
transcrição anterior roda, que é a regra correta ("um ouvindo por vez"), e o teste culpa a tecla
por isso. Já pus uma espera pelo `transcribed:` entre ciclos e ainda assim oscila.

**Próximo passo sugerido:** medir se o `CRASH Utility` acontece só sob esse ritmo ou também em uso
normal. Se for só sob metralhadora, o portão precisa de ritmo realista (segurar 2 s, esperar o
ciclo fechar). Se acontecer em uso normal, é defeito de produto e vira prioridade.

Enquanto isso: **modo segurar não é o padrão** (o padrão é alternar, que tem portão verde), e as
outras 12 camadas passam.

## 2. Publicar

A **2.0.1 já foi publicada**: https://github.com/luis1amaral/dito-app/releases/tag/v2.0.1
O repositório já foi substituído por este projeto num commit só.

Falta apenas, quando o corredor estiver verde: instalar o `.exe` e rodar
`pwsh -File quality/smoke.ps1 -Exe "$env:LOCALAPPDATA\Programs\Dito\Dito.exe"`.

## 3. Portões que ainda faltam

Os 13 que existem estão em `quality/verify.ps1`. **O cortador de áudio já tem portão** (`chunker.ts`,
provado nos dois sentidos) — não refaça.

| Portão | O que provar | Situação |
|---|---|---|
| `i18n` | nenhum texto fixo sobrou nos `.ts` das telas | parcial: `code-quality.ts` já conta o HTML (dá 0), e `Record<MessageKey, string>` já barra chave faltando em tempo de compilação; falta cobrir os `.ts` |
| ditado longo | 3 minutos falando sem estourar memória (issue #7925 do Orca) | manual, com o app aberto |

## 4. Linux — o trabalho de verdade

**Nada disso pode ser feito no Windows.** Precisa de uma máquina Linux com X11.

O que já está pronto:
- `native/binding.gyp` tem o bloco `OS=='linux'` apontando para `src/input_x11.cc` e
  `src/key_hook_x11.cpp` — **os dois arquivos que faltam escrever**.
- `npm run pack:linux` gera o `.deb` numa linha, assim que o addon existir.
- `native/reference/dito_win32_plugin.cc` é o plugin X11 do Dito 1.x, **que funcionava**: `XGrabKey`
  com thread própria, `XTest` para digitar, EWMH para achar e ativar a janela. É trocar a casca
  (method channel → N-API), não reescrever a lógica.

Armadilhas por peça estão em `PENDENCIAS.md` §1. As três que mais custam:

1. `XGrabKey` é **exclusivo por processo** e falha **em silêncio** com `BadAccess`.
2. Não existe equivalente de `KEYEVENTF_UNICODE`: é preciso remapear um keysym livre por caractere.
3. Janela transparente no X11 depende de **compositor ativo**; sem ele a pílula vem com fundo preto.
   Detectar com `XGetSelectionOwner` de `_NET_WM_CM_S0` e cair para janela opaca.

Depois do `.deb`: **subir no APT** (`apt.defaltm.com`). Publicar no GitHub não atualiza Linux
nenhum — o updater lê o `Packages` do repositório APT, que está parado na 1.6.8. Passo manual.

---

## 5. Pendências do Windows

Lista completa em `PENDENCIAS.md` §2. Por ordem de risco:

| # | O quê | Por quê |
|---|---|---|
| W1 | Auto-update **nunca exercitado** | a 1.7.0 foi despublicada por update ruim; testar 2.0.1 → 2.0.2 |
| W8 | Instalador cai na **mesma pasta da 1.7.x** | quem atualizar sem desinstalar mistura duas árvores |
| W3 | **9 dos 10 modelos nunca rodaram** | `resolveFile` pode não achar arquivo de outro tipo |
| W6 | **Iniciar com o Windows** não existe | o atalho `--startup` já existe, falta a entrada |
| W7 | Sem assinatura de código | SmartScreen avisa na instalação |
| W9 | Histórico antigo não migra | `historico.jsonl` → `history.jsonl` |

---

## Onde olhar quando algo quebrar

- `docs/decisoes.md` — os porquês que não cabem num comentário de uma linha.
- `docs/heranca/armadilhas.md` — defeitos reais do Dito 1.x, com sintoma e causa provada. Muitos
  continuam valendo porque são do Windows, não do Flutter.
- `quality/PARIDADE.md` — comportamento por comportamento: o que já está provado e o que não.
- `native/README.md` — por que aquele C++ é congelado e o que quebra se você mexer.
