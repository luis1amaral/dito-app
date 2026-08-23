# Dito

**Aperte a tecla, fale, e o texto é digitado onde o cursor estiver.** Em qualquer janela — terminal,
navegador, WhatsApp, campo de busca. Nada sai do seu computador.

Só transcrição. Sem agente, sem chat, sem nuvem.

---

## Como funciona

| | |
|---|---|
| **Motor** | NVIDIA Parakeet TDT 0.6B v3 int8, em ONNX, rodando na **CPU** a 5–8× tempo real |
| **Pontuação** | vem do modelo, com maiúsculas |
| **Idiomas** | 25, inclusive português; mais 9 modelos opcionais no catálogo |
| **Atalho** | uma tecla (padrão **F10**), no modo alternar ou segurar |
| **Privacidade** | 100% local: o áudio nunca sai da máquina |

O modelo padrão (640 MB) é baixado na primeira execução, com sha256 conferido por arquivo e
retomada se a rede cair. Dá para baixar outros, escolher qual usar e apagar — menos o último, para
você nunca ficar sem transcrição.

## Instalar

Baixe o `dito-*-setup.exe` da [última release](https://github.com/luis1amaral/dito-app/releases) e
execute. O app vive na **bandeja**; a janela abre no clique do ícone.

> Se você tem a 1.7.x instalada, **desinstale antes** — o instalador usa a mesma pasta.

Linux ainda não: o addon nativo é Win32. Ver `PENDENCIAS.md`.

## Desenvolver

```bash
npm install
npm run addon      # compila o addon nativo (precisa de MSVC + Windows SDK)
npm run dev        # sobe com recarga
npm run pack       # gera o instalador
npm run verify     # o portão de qualidade inteiro
```

### Estrutura

```
src/shared/     o contrato: config, IPC e modelos, num lugar só
src/main/       15 módulos de um assunto cada; index.ts só dá a partida
src/preload/    a única ponte para as telas, com contextIsolation
src/renderer/   pílula, ajustes e cartão de revisão, em TypeScript
native/         addon N-API: atalho global e colagem (importado e congelado)
quality/        os portões; entrada única em verify.ps1
docs/           os porquês que não cabem num comentário de uma linha
```

## O portão de qualidade

Nada é dado por pronto sem o binário ter subido — a 1.7.0 saiu com 220 testes verdes e morria antes
da primeira linha de log. `npm run verify` roda 13 camadas e devolve **exit 0 PASSA, 1 FALHA,
2 INCOMPLETO**; INCOMPLETO nunca é verde.

```
typecheck · lint · regras do projeto · motor · mutação · modelos · cortador ·
nativo · tecla · segurar · fumaça · colagem console · colagem gui
```

Todo portão é provado **nos dois sentidos**: recoloca-se o defeito e exige-se que ele reprove.
`quality/PARIDADE.md` lista comportamento por comportamento o que já está provado e o que não.

## Créditos e licença

- Modelo **Parakeet TDT** da NVIDIA — CC-BY-4.0
- Motor **sherpa-onnx** — Apache-2.0
- Resample, catálogo de modelos, formato do gerenciador de download, corte de áudio em janelas e
  configuração dos recognizers adaptados de [stablyai/orca](https://github.com/stablyai/orca) — MIT

O Dito é MIT.
