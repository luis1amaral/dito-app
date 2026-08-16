# Porte para Windows

O porte **está feito e rodando**. Este arquivo passou de plano a registro: o que ficou pronto, o
que foi provado numa máquina de verdade, e o que ainda falta.

| onde | o quê |
|---|---|
| `src/dito/platform/windows/README.md` | módulo a módulo, e as armadilhas do adaptador |
| `packaging/windows/README.md` | como se instala hoje, e o instalador de distribuição que falta |
| `docs/armadilhas.md` | tudo que já custou depuração, com números — 2.12, 2.13 e 7.16 nasceram aqui |
| `CLAUDE.md` | as regras do projeto |

## Como está dividido

`src/dito/platform/__init__.py` escolhe o backend por `sys.platform` e reexporta. Acima dessa linha
ninguém nomeia plataforma: `app.py`, `cli.py` e `core/session.py` pedem `instance` ou `hotkeys` e
recebem o que a máquina tem.

O que é **um conhecimento só** mora fora dos dois backends:

| arquivo | o quê |
|---|---|
| `platform/hotkeys_core.py` | a máquina de estados hold/toggle, com a carência e o debounce do toggle |
| `platform/control.py` | o protocolo de controle (`show`, `ping`, `quit`, `status`) e o nome da trava |
| `platform/source_health.py` | a regra de "isto impede de gravar" |
| `platform/mixer.py` | o que é um controle de ganho de captura |

Cada backend só implementa o que de fato muda: como ler a tecla, como consumi-la, como falar com a
instância viva, como perguntar ao sistema se o microfone está mudo.

## As quatro garantias, no Windows

1. **Áudio nunca se perde** — provado: `taskkill /F` no meio de uma gravação deixou **5,80 s** de
   WAV que abre e toca.
2. **Quando não está captando, ele grita** — provado: `dito selftest --source zeros` alarmou em
   **1,20 s**.
3. **A gravação não tem limite de tempo** — o `TOGGLE` só para no segundo toque, com teste que
   injeta tecla de verdade.
4. **Nada aparece no login** além do ícone da bandeja — o atalho de autostart chama
   `ditow.exe listen`, sem console e sem janela. **Não verificado com um login de verdade.**

Sobre a nº 2: no Linux o mudo é pego em três camadas. No Windows são duas — o WASAPI
(`audio_system.py`, mudo e volume da entrada padrão) e o watchdog de nível. Não existe equivalente
do ganho de hardware do ALSA, e o `alsa_mixer.py` do Windows responde honestamente "não dá para
checar" em vez de inventar.

## O que foi provado nesta máquina

Windows 10 Pro 19045, Python 3.13.3, PySide6 6.11.1, GTX 1650.

| prova | resultado |
|---|---|
| `ruff check .` + `pytest -m "not x11 and not winkeys"` | 300 passam, 9 pulados (só-Linux) |
| `pytest -m winkeys` (injeta tecla por `SendInput`) | 6 passam |
| `dito doctor` | config, biblioteca, microfone, mudo, volume e modelo |
| `dito selftest --source zeros` | alarme em 1,20 s |
| `dito selftest --source mic` | 100 blocos, WAV de 5,0 s |
| `taskkill /F` no meio da gravação | 5,80 s de WAV íntegro |
| trava de instância única com o daemon vivo | recusou; um segundo `listen` não virou outro processo |
| `dito status` / `dito stop` pelo pipe nomeado | respondem na hora |
| motor Whisper (fala sintetizada → texto) | transcreveu a frase inteira, 100% das palavras |

## O que ainda NÃO foi verificado

Dito com todas as letras, porque este projeto nasceu de uma falha silenciosa:

- **A cadeia completa com fala humana**: segurar F9, falar, soltar, e o texto aparecer na janela de
  onde você chamou. As peças foram provadas separadas (tecla, captura, WAV, motor, colagem), a
  emenda não.
- **O toast do Windows** (`notify.py` → bandeja) não foi visto na tela.
- **`focus.py`** — devolver o foco depois do cartão de revisão — não foi exercitado.
- **O autostart num login de verdade.**
- **A suíte de X11 no Linux** depois da extração do `hotkeys_core.py`. Aqui não há servidor X, e
  `tests/test_hotkeys_x11.py` pula. Rodar no Linux antes de confiar.

## Os dois caminhos de instalação

O **instalador de distribuição** (PyInstaller + Inno Setup) existe: `packaging/windows/construir.ps1`
o monta, e `packaging/windows/README.md` explica cada peça. O **`instalar.ps1`** continua para quem
tem Python e o repositório.

A **GPU está ligada** e medida numa GTX 1650: `small` em float16 transcreve 6,30 s de fala em
**1,66 s (RTF 0,26)** com o modelo quente, contra 5,91 s (RTF 0,94) na CPU em int8 — **3,6×**.

Como ela chega até lá depende do caminho, e **os dois dividem o mesmo marcador**
`%LOCALAPPDATA%\dito\state\gpu-ready`:

| | quem baixa | para onde |
|---|---|---|
| `instalar.ps1` (venv) | `pip`, no primeiro uso | `site-packages/nvidia/*/bin` da venv |
| `.exe` (bundle) | `dito gpu --install`, marcado na instalação | `%LOCALAPPDATA%\dito\cuda` |

O bundle **não tem `pip`**, e por isso não é o `bootstrap.install_gpu_extras()` que roda lá —
é `platform/windows/cuda_pack.py`, que baixa o wheel do PyPI e o extrai na mão. O porquê inteiro
está em `docs/armadilhas.md` **3.11**. São **1,3 GB baixados e 1,9 GB em disco**, uma vez só.

## Convenções que não se negociam

- **Comentário: no máximo 1 LINHA, em inglês**, e só quando carrega um *porquê* que o código não
  diz sozinho. O porquê longo vai para `docs/armadilhas.md` e o comentário vira um ponteiro.
- **Strings de interface são inglês no código**, via `gettext`. Depois de mexer:
  `bash tools/i18n.sh all`, e traduza **uma a uma** o que aparecer como `fuzzy` (armadilha 7.15).
- **`CHANGELOG.md`, `README.md` e `docs/`: pt-BR.**
- **Cor, espaço, raio e duração saem de `ui/theme.py`.**
- **Commits em inglês**, `[TIPO]: assunto curto no imperativo`. **Nunca** co-autor, **nunca** PR.
- Mudou comportamento? `CHANGELOG.md`: o quê, por quê, e **como foi verificado**, com o número.
