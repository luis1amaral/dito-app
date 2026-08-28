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
| **Sistemas** | Windows 10/11 e Linux com X11 |
| **Privacidade** | 100% local: o áudio nunca sai da máquina |

O modelo padrão (640 MB) é baixado na primeira execução, com sha256 conferido por arquivo e
retomada se a rede cair. Dá para baixar outros, escolher qual usar e apagar — menos o último, para
você nunca ficar sem transcrição.

## Instalar

**Windows** — baixe o `dito-*-setup.exe` da
[última release](https://github.com/luis1amaral/dito-app/releases) e execute.

> Se você tem a 1.7.x instalada, **desinstale antes** — o instalador usa a mesma pasta.

**Linux (Debian/Ubuntu/Mint)** — pelo repositório, que também traz as atualizações seguintes:

```bash
curl -fsSL https://apt.defaltm.com/defaltm-archive-keyring.gpg \
  | sudo tee /usr/share/keyrings/defaltm-archive-keyring.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/defaltm-archive-keyring.gpg] https://apt.defaltm.com stable main" \
  | sudo tee /etc/apt/sources.list.d/defaltm.list
sudo apt update && sudo apt install dito
```

Ou baixe o `dito-*-amd64.deb` da release e instale com `sudo apt install ./dito-*-amd64.deb`.

Nos dois sistemas o app vive na **bandeja**; a janela abre no clique do ícone. No Linux a pílula
transparente depende de um compositor ativo — sem ele, ela aparece com fundo opaco.

## Desenvolver

```bash
npm install
npm run addon        # compila o addon nativo
npm run dev          # sobe com recarga
npm run pack         # instalador do Windows
npm run pack:linux   # pacote .deb
npm run verify       # o portão de qualidade inteiro
```

O addon precisa de compilador C++: **MSVC + Windows SDK** no Windows, e no Linux
`build-essential` mais `libx11-dev`, `libxtst-dev` e `libxi-dev`.

### Estrutura

```
src/shared/     o contrato: config, IPC e modelos, num lugar só
src/main/       15 módulos de um assunto cada; index.ts só dá a partida
src/preload/    a única ponte para as telas, com contextIsolation
src/renderer/   pílula e ajustes, em TypeScript
native/         addon N-API: atalho global, colagem e digitação (Win32 e X11)
quality/        os portões; entrada única em verify.mjs
_docs/          os porquês que não cabem num comentário de uma linha
```

## O portão de qualidade

Nada é dado por pronto sem o binário ter subido — a 1.7.0 saiu com 220 testes verdes e morria antes
da primeira linha de log. `npm run verify` roda em **Windows e Linux** e devolve
**exit 0 PASSA, 1 FALHA, 2 INCOMPLETO**; INCOMPLETO nunca é verde.

| Camada | Prova | Onde roda |
|---|---|---|
| `typecheck` · `lint` · `regras do projeto` | o contrato compila e as regras do projeto valem | ambos |
| `bundle` | as telas compilam | ambos |
| `compartilhado` | emenda de segmentos, migração de configuração e i18n das telas | ambos |
| `motor` | transcreve as fixtures dentro do teto de WER, com pontuação e velocidade | ambos |
| `mutacao` | recoloca cada defeito conhecido e **exige** que o portão reprove | ambos |
| `modelos` | baixa, confere sha256 e recusa arquivo adulterado | ambos |
| `cortador` · `sinal` | corte no silêncio; pausa não vira "sem som" | ambos |
| `captura` | cancelar um ditado solta o microfone e para de enviar áudio | ambos |
| `nativo` | o addon carrega e o atalho global instala de verdade | ambos |
| `tecla` · `segurar` · `fumaca` · `colagem` | a tecla dita, o app sobe, o texto chega no alvo | Windows |
| `colagem (x11)` | colagem e digitação com acento numa janela X11 real | Linux |
| `feed` | o app acha a versão nova no feed da **sua** plataforma | ambos |

Uma camada que não existe no sistema onde você roda entra como **PENDENTE**, nunca como passe.
Todo portão é provado **nos dois sentidos**: recoloca-se o defeito e exige-se que ele reprove.
`_docs/PARIDADE.md` lista comportamento por comportamento o que já está provado e o que não.

## Créditos e licença

- Modelo **Parakeet TDT** da NVIDIA — CC-BY-4.0
- Motor **sherpa-onnx** — Apache-2.0
- Resample, catálogo de modelos, formato do gerenciador de download, corte de áudio em janelas e
  configuração dos recognizers adaptados de [stablyai/orca](https://github.com/stablyai/orca) — MIT

O Dito é MIT.
