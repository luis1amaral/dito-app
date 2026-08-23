# plano.md — o que falta

Escrito para ser executado **do zero, sem nada da conversa anterior**. Quem abrir isto consegue
terminar.

Projeto: `C:\Users\Luis\Desktop\Projetos\dito\dito-desktop`

---

## Antes de qualquer coisa

```bash
npm install
npm run addon      # precisa de MSVC + Windows SDK; faz build limpo sempre
npm run verify     # 12 camadas; exit 0 PASSA, 1 FALHA, 2 INCOMPLETO
```

**Regra que não se pula:** nada é dado por pronto sem `verify` em verde. INCOMPLETO nunca é verde.
Ao criar portão novo, prove-o **nos dois sentidos**: recoloque o defeito e exija que ele reprove.

Regras de escrita do projeto estão em `CLAUDE.md` (código e comentário em inglês, comentário de no
máximo 1 linha, texto de tela em pt-BR/en via `src/shared/i18n.ts`).

---

## 1. Publicar a 2.0.1 no Windows

O estado atual já compila, sobe e passa nos portões. Falta:

```bash
npm run pack                                   # gera dist/dito-2.0.1-setup.exe
pwsh -File quality/smoke.ps1 -Exe "$env:LOCALAPPDATA\Programs\Dito\Dito.exe"   # depois de instalar
```

Depois, no repositório `luis1amaral/dito-app`:

1. **Substituir o conteúdo do repositório** por este projeto (decisão do dono: um commit só, sem
   nada do app Flutter antigo). O histórico do Git preserva o que era; o que precisava sobreviver
   já foi copiado para `docs/heranca/` e `native/reference/`.
2. `gh release create v2.0.1` com `dist/dito-2.0.1-setup.exe`.
3. Conferir que a **2.0.0 continua como rascunho** — ela está quebrada e não pode voltar a ser
   `Latest`.

---

## 2. Portões que ainda faltam

| Portão | O que provar | Onde |
|---|---|---|
| `review` | o cartão abre **com o texto**, `Enter` cola no alvo, `Tab` não cola nada | novo em `quality/` |
| `chunker` | 20 s de áudio viram ≥2 janelas, o corte cai em silêncio, a emenda não duplica | novo, unitário sobre `src/main/audio-chunker.ts` |
| `i18n` | toda chave existe em `pt` e `en`, e nenhum texto fixo sobrou no HTML | novo; o `Record<MessageKey, string>` já garante metade em tempo de compilação |
| ditado longo | 3 minutos falando sem estourar memória (é a issue #7925 do Orca) | manual, com o app aberto |

O `quality/verify.ps1` já tem a lista de camadas; basta acrescentar as novas linhas seguindo o
padrão dos outros arquivos.

---

## 3. Linux — o trabalho de verdade

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

## 4. Pendências do Windows

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
