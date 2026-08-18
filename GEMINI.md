# Dito — regras deste projeto

Valem junto com o `~/.claude/CLAUDE.md`. Onde houver conflito, o global manda.

## Comentário: no máximo 1 LINHA

Sem exceção, e vale para docstring também. O porquê longo **não mora no código** — mora em
`docs/armadilhas.md`, e o comentário vira um ponteiro de uma linha:

```python
# See docs/armadilhas.md 1.4: the stdlib `wave` writer only fixes sizes on close.
self._patch_sizes()
```

Motivo: parágrafo dentro do código envelhece junto com ele e ninguém revisa. Em `docs/` alguém lê.

## O que este projeto garante (e nenhuma mudança pode enfraquecer)

1. **Áudio nunca se perde.** Vai para o disco desde o primeiro bloco e o WAV é válido a qualquer
   instante, inclusive depois de `kill -9`. Nada apaga áudio sem antes conseguir ler a substituição.
2. **Quando não está captando, ele grita** — em ~1 s, por forma, cor e som. Falha silenciosa é o
   defeito que originou o projeto (99 s de fala perdidos).
3. **A reunião não tem limite de tempo.** Grava até mandarem parar.
4. **Nada aparece no login** além do ícone da bandeja.

Mexeu em `audio/`, `core/session.py` ou `audio/level.py`? Rode `tests/test_session.py`,
`test_writer.py` e `test_watchdog.py` — eles existem porque cada um desses pontos já quebrou.

## Camadas

```
ui/  app.py  cli.py        ← podem conhecer qualquer coisa abaixo
core/ stt/ output/ audio/ platform/   ← não conhecem ui/ nem app.py. NUNCA.
```

`platform/linux_x11/` é o único lugar com X11, `pactl`, `amixer` ou `pynput`. Vazou para fora, é bug.

## Cor, espaço, raio, duração

Saem de `ui/theme.py`, sempre. Hex ou px escrito numa tela é bug — há teste que reprova.
A pílula flutuante tem paleta própria (`hud_*`), igual nos dois temas, porque a superfície dela é
escura independente do tema do sistema.

## Antes de dizer que está pronto

```bash
.venv/bin/ruff check . && .venv/bin/python -m pytest -q
```

Teste de X11 injeta tecla de verdade; `pytest -m "not x11"` pula. Para ver a interface sem abrir o
app: `python tools/render_ui.py`.
