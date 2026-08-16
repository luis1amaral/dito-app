# Adaptador do Windows

Nasceu com as assinaturas prontas e **não foi exercitado**. Não há máquina Windows aqui, e nada
neste diretório será dado como funcionando antes de rodar numa.

## O que já está portado

| Arquivo | Estado |
|---|---|
| `instance.py` | mutex nomeado, completo. **O nome é contrato com o projeto `defalt` — não renomear.** |
| `cuda_dlls.py` | registro das DLLs de cuBLAS, completo (ver a armadilha abaixo) |

## O que falta

- **A fachada de plataforma, antes de tudo.** `src/dito/platform/__init__.py` está vazio: `app.py`,
  `cli.py` e `core/session.py` importam `linux_x11` direto, em oito lugares, então `import
  dito.app` quebra no Windows antes de chegar a qualquer funcionalidade. Ver `docs/porte-windows.md`.
- `hotkeys.py` — no Windows o caminho é o `win32_event_filter` do pynput com `suppress_event()`,
  que **só existe lá**. É mais simples que no X11: não há auto-repeat entregando pares
  Release+Press, então o vigia de estado físico não é necessário. As constantes `VK_*` que a
  versão antiga tinha estão no histórico do repositório `dev`.
- `paste.py` — igual ao do Linux (clipboard + Ctrl+V pelo pynput); só não depende de `xclip`.
- `audio_system.py` — não há `pactl`. O equivalente é WASAPI via `pycaw` ou a API `IAudioEndpointVolume`.
  **Enquanto não existir, o watchdog de nível continua cobrindo sozinho** — ele é o detector que
  dá a verdade de qualquer forma.
- Instalador: PyInstaller + Inno Setup.

## Armadilhas conhecidas, antes de começar

1. **As DLLs de cuBLAS ficam onde o Windows não procura.** O pip as instala em
   `site-packages/nvidia/*/bin`. E `os.add_dll_directory` **não basta**: ele só cobre
   `LoadLibraryEx` com as flags de diretório de busca, e o ctranslate2 resolve cuBLAS com um
   `LoadLibrary` simples, que lê o `PATH` e nada mais. É preciso prefixar o `PATH` também.
   Já está resolvido em `cuda_dlls.py`.

2. **O erro de cuBLAS só aparece no primeiro encode.** Construir o `WhisperModel` com
   `device="cuda"` não toca na biblioteca. Sem forçar um encode de 1 s dentro do `try`, o
   construtor passa e o erro estoura na primeira transcrição de verdade — quando o fallback para
   CPU já não roda mais. Resolvido em `stt/engine.py`.

3. **Os wheels queriam Python ≤ 3.12.** O `ctranslate2` não tinha wheel para 3.14 quando isto foi
   escrito. Conferir antes de escolher a versão do Python do instalador.

4. **`WS_EX_NOACTIVATE` briga com `focus_force`.** A pílula não pode tomar foco, mas o diálogo de
   revisão precisa do teclado. No Qt isso é `Qt.Tool` + `WA_ShowWithoutActivating` para a pílula e
   uma janela separada para o diálogo — mesma divisão do Linux, mas o comportamento precisa ser
   revalidado lá.

## Como validar quando houver máquina

Os mesmos critérios do Linux, na ordem:

```
dito doctor                              # microfone, mute, modelo
dito selftest --source zeros --seconds 5 # alarme em ~1 s
dito selftest --source mic --seconds 5   # WAV íntegro em %LOCALAPPDATA%
```
Depois: segurar a tecla por 40 s sem a gravação se partir, e conferir que a trava impede coexistir
com o `defalt`.
