# Medição — qual método realmente cola no Windows, por classe de janela

Feita em 2026-08-22 com `tool/sonda_colagem.ps1` nesta máquina (Windows 10 build 19045, conhost
`ForceV2=1`). Cada alvo em modo cru foi **fixado** no mesmo `GetConsoleMode` da sessão real do Claude
Code antes de medir, senão a tabela não valeria.

## O que a sessão real do Claude Code usa

Lido com `AttachConsole` (só leitura) do `claude.exe` rodando em `cmd.exe`:

```
0x0208  -processed -line -echo -quickedit VT_INPUT
```

Contra um `cmd.exe` comum: `0x01E7  PROCESSED LINE ECHO QUICKEDIT -vt_input`.

Com `ENABLE_PROCESSED_INPUT` e `ENABLE_QUICK_EDIT_MODE` desligados, **o conhost deixa de interceptar
o `Ctrl+V`** e entrega o caractere de controle `0x16` (SYN) direto ao aplicativo. É o mesmo defeito
da armadilha 6.3 no Linux, na outra plataforma.

O `setRawMode(true)` do Node sozinho dá `0x0008` — **sem `VT_INPUT`**. Só isso já invalidaria a
medição; a sonda por isso força o modo para `0x0208` e aborta o alvo se não conseguir.

## Tabela

Amostras: **curta** (frase com acentos pt-BR), **multi** (3 linhas), **longa** (~2100 caracteres).
`Enter na ordem` = o texto completo chegou **antes** do Enter que o app manda 250 ms depois.

| Janela | Classe | `Ctrl+V` | `Ctrl+Shift+V` | `Shift+Insert` | `WM_COMMAND 0xFFF1` | `SendInput` UNICODE |
|---|---|---|---|---|---|---|
| Bloco de Notas *(controle)* | `Notepad` | **cola** | cola | cola | nada *(é de console)* | **cola** |
| **cmd.exe / conhost** | `ConsoleWindowClass` | **só `0x16`** | **só `0x16`** | parcial | cola curta/longa, falha multi | **cola as três** |
| Windows Terminal | `CASCADIA_HOSTING_WINDOW_CLASS` | **cola** *(bracketed)* | cola *(bracketed)* | cola *(bracketed)* | não se aplica | cola |
| Git Bash | `mintty` | **cola** | parcial | cola | não se aplica | cola |

### Enter na ordem — o sintoma original, reproduzido

No conhost, com `Ctrl+V`, a coluna `Enter na ordem` deu **NÃO** nas três amostras: o texto nunca
chega e **só o Enter é enviado**. É exatamente o relato do dono ao ditar no Claude Code.
Com `SendInput` UNICODE deu **sim** nas três.

### Bracketed paste (`ESC[200~` / `ESC[201~`)

| Janela | Embrulha a colagem? |
|---|---|
| Windows Terminal | **sim** — texto de 3 linhas chega como **uma** colagem |
| conhost | **não** — 3 linhas viram **3 envios** no CLI |
| mintty | **não** — idem |

É este número, e não uma suposição, que justifica juntar as quebras de linha quando o destino é
console/terminal.

## Conclusão que o código segue

**Só o conhost está quebrado.** Windows Terminal, Git Bash e as janelas GUI já colam com `Ctrl+V`
hoje — não se toca em nenhuma delas. A correção é cirúrgica:

| Classe da janela alvo | O que fazer | Muda em relação a hoje? |
|---|---|---|
| `ConsoleWindowClass` (conhost) | digitar com `SendInput` + `KEYEVENTF_UNICODE` | **sim** — é o conserto |
| todo o resto (WT, mintty, GUI, VS Code) | `Ctrl+V`, como sempre foi | **não** |

O terminal integrado do VS Code compartilha o **mesmo HWND** do editor (`Chrome_WidgetWin_1`), então
classe de janela nunca vai distinguir os dois — e não precisa: o `Ctrl+V` do VS Code cola nos dois
contextos, e é o que já acontece hoje. Fica validado no roteiro manual, não pela sonda.

## Corrigido em relação ao que a documentação afirmava

A armadilha 6.4 traz a linha *"Colagem — Windows: `Ctrl+V` (universal)"*, e o `docs/WINDOWS.md` diz
que na 1.6.8 o `SendInput` com `Ctrl+V` *"funciona universalmente ... inclusive Windows Terminal,
PowerShell e CMD"*. **É falso para o conhost em modo cru**, que é justamente onde o Claude Code e o
Gemini CLI rodam. A afirmação nunca tinha sido medida: o `tool/spike_paste.dart` prova a colagem
contra um controle EDIT do Win32 criado pelo próprio app, nunca contra um console.

## Como repetir

```powershell
pwsh -File tool/sonda_colagem.ps1                                  # todos os alvos
pwsh -Command "& ./tool/sonda_colagem.ps1 -Alvos cmd-cru"          # só o conhost
pwsh -Command "& ./tool/sonda_colagem.ps1 -Manual"                 # inspeciona a janela que você focar
```

A sonda sobe os próprios alvos descartáveis e **nunca** mira uma sessão real. Ainda assim ela digita
em janelas de verdade: não use o teclado enquanto ela roda.
