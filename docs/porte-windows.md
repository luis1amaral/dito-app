# Porte para Windows — briefing

Este arquivo é o **regente** do porte: a missão, a ordem, e como provar. O detalhe técnico não
mora aqui, para não envelhecer em dois lugares:

| onde | o quê |
|---|---|
| `src/dito/platform/windows/README.md` | módulo a módulo, e as armadilhas do adaptador (cuBLAS, foco, versão do Python) |
| `packaging/windows/README.md` | estado conferido, PyInstaller e Inno Setup |
| `docs/armadilhas.md` | tudo que já custou depuração, com números |
| `CLAUDE.md` | as regras do projeto |

Leia os quatro antes de escrever uma linha.

---

## Como usar

Abra o Claude Code dentro do repositório, na máquina Windows, e diga:

> Vamos portar o Dito para Windows. Leia `docs/porte-windows.md` e siga.

## A missão

Uma pessoa em Windows instala, abre, segura F9, fala, solta — e o texto aparece onde o cursor
está. F10 faz o mesmo sem precisar segurar. Nada aparece no login além do ícone da bandeja.

## Não confie neste documento sem verificar

Ele foi escrito em 16/08/2026, na versão 0.3.0, com 265 testes verdes. Rode isto primeiro e
trabalhe a partir do que a máquina responder:

```
git log --oneline -5
ruff check . ; python -m pytest -q
```

Divergiu do que está escrito? **O repositório manda.**

## As quatro garantias que nenhuma mudança pode enfraquecer

1. **Áudio nunca se perde.** Vai para o disco desde o primeiro bloco; o WAV é válido a qualquer
   instante, inclusive depois de o processo ser morto.
2. **Quando não está captando, ele grita** — em ~1 s, por forma, cor e som. Falha silenciosa é o
   defeito que originou o projeto: 99 s de fala perdidos.
3. **A gravação não tem limite de tempo.**
4. **Nada aparece no login** além do ícone da bandeja.

A nº 2 é a mais frágil aqui: no Linux o mudo é pego em três camadas (`pactl`, ganho do ALSA e
nível do sinal) e no Windows sobram uma ou duas. **O watchdog de nível não pode ser enfraquecido
em hipótese nenhuma** — lá ele é a última linha, não a terceira. Dizer "não sei" num diagnóstico
que não existe é correto; inventar não é.

## O primeiro trabalho, antes de qualquer código de Windows

`src/dito/platform/__init__.py` está **vazio**. Não existe despacho por plataforma: o código
importa `linux_x11` direto, em oito lugares —

```
src/dito/app.py:34-37       audio_system, instance, notify, FocusBroker, HotkeyManager, Mode
src/dito/cli.py:23,264,265,379,390
src/dito/core/session.py:22 alsa_mixer, audio_system
```

Enquanto isso existir, `import dito.app` quebra no Windows antes de chegar a qualquer
funcionalidade. `platform/__init__.py` escolhe por `sys.platform` e reexporta; os oito pontos
passam a importar de `..platform`.

**Sem mudança de comportamento no Linux.** A suíte tem que seguir verde depois desse passo
sozinho, antes de você escrever a primeira linha de Windows.

`tests/test_instance.py` e `tests/test_hotkeys_x11.py` importam `linux_x11` direto de propósito —
eles testam o backend de Linux. Deixe.

## Dois vazamentos de X11 fora de `platform/`

1. `src/dito/bootstrap.py:188` decide modo headless por `os.environ.get("DISPLAY")`. No Windows
   `DISPLAY` nunca existe, então cairia **sempre** em headless e a tela de preparação nunca
   apareceria.
2. `src/dito/output/paste.py:40,60` acusa o `xclip` no texto do erro. O `pyperclip` funciona
   nativamente no Windows; a mensagem é que precisa parar de culpar um programa de Linux.

## `paths.py`

Hoje é XDG puro. No Windows: `%APPDATA%` para configuração, `%LOCALAPPDATA%` para estado.

**As gravações não vão para lá.** Desde 0.3.0 elas moram na biblioteca do usuário, arquivadas por
data — no Linux `~/Documentos/Dito/2026/08/16/07-42-13.json`. No Windows o equivalente é
`Documents\Dito`, e o `cfg.library_dir()` é quem decide. É pasta comum de propósito: qualquer
programa pega e usa como contexto sem saber nada do Dito.

Cuidado com a armadilha **5.4**, que vale nas duas plataformas: as variáveis podem estar
**definidas e vazias**, e aí `os.environ.get(var, default)` mente.

## A ordem, e prove cada passo antes do próximo

1. Fachada de plataforma. Suíte verde no Linux, sem código de Windows nenhum.
2. `paths.py` com ramo de Windows. Testes dos dois ramos.
3. `instance.py`: falta o `ControlServer` e o `send()` — é o que faz `dito status` responder.
   O `claim()` já existe, com mutex nomeado, **nunca executado**.
4. `hotkeys.py`. É o coração: F9 é o produto.
5. `notify.py` e `focus.py`.
6. `audio_system.py`, e a decisão honesta sobre o que não dá para medir.
7. Empacotamento.

Antes de implementar, leve o plano ao agente **`staff-reviewer`** e trate `REQUEST CHANGES` como
bloqueio. Antes de dizer que está pronto, **`verify-app`**. Antes de commitar, **`/grill`**.

## Como provar que está pronto

O portão do projeto, igual nas duas plataformas:

```
ruff check . ; python -m pytest -q
```

Os testes marcados `x11` injetam tecla num servidor X e não rodam no Windows (`-m "not x11"`).
Escreva os equivalentes com um marcador próprio.

Além do portão, prove **rodando**:

1. F9 segurado numa janela qualquer cola o texto.
2. F10 grava sem segurar e para no segundo toque; o cartão de revisão abre nos dois casos.
3. Microfone mudo no sistema → alarme em ~1 s, com forma, cor e som.
4. **Matar o processo no meio de uma gravação → o WAV no disco abre e toca.**
5. Duas instâncias: a segunda recusa. E não coexiste com o `defalt`.
6. Login: só o ícone da bandeja, nenhuma janela.

O item 4 é o motivo de o projeto existir. Não pule.

## Convenções que não se negociam

- **Comentário: no máximo 1 LINHA, em inglês**, e só quando carrega um *porquê* que o código não
  diz sozinho. Docstring igual. O porquê longo vai para `docs/armadilhas.md` e o comentário vira
  um ponteiro de uma linha.
- **Strings de interface são inglês no código**, via `gettext` (`from ..i18n import _`). Depois de
  mexer: `bash tools/i18n.sh all`, e traduza o que aparecer. **Nunca** português cravado.
- **`CHANGELOG.md`, `README.md` e `docs/`: pt-BR.**
- **Cor, espaço, raio e duração saem de `ui/theme.py`.** Hex ou px numa tela é bug, e há teste.
- **Commits em inglês**, `[TIPO]: assunto curto no imperativo`. **Nunca** co-autor. Publicar é
  commit + `git push` no branch principal — **nunca abra Pull Request**.
- Mudou comportamento? Registra no `CHANGELOG.md`: o quê, por quê, e **como foi verificado**, com
  o número que você mediu.

## O que NÃO fazer

- Não enfraqueça um teste para passar. Teste de Linux que falha no Windows é teste específico de
  plataforma: marque, não apague.
- Não renomeie o mutex (armadilha 5.1) e não descarte o handle do `claim()` (5.1b).
- Não empacote o modelo Whisper: são ~486 MB e ninguém baixa o instalador.
- Não faça o autostart abrir janela.
- **Não presuma.** Se não rodou, não afirme. Este projeto nasceu de uma falha silenciosa.
