<#
.SYNOPSIS
  Mede QUAL metodo de injecao realmente cola texto em cada tipo de janela no Windows.

.DESCRIPTION
  O `tool/spike_paste.dart` so prova a colagem contra um controle EDIT do Win32. Esta sonda cobre o
  que faltava: consoles e terminais, inclusive em MODO CRU -- o modo em que o Claude Code e o Gemini
  CLI colocam o console (medido: 0x0208, sem PROCESSED_INPUT e sem QUICK_EDIT), e onde a colagem
  falha hoje.

  Alem de "chegou / nao chegou", mede o que decide o codigo:
    - multilinha: quantas quebras chegam, e se ha bracketed paste (ESC[200~ / ESC[201~);
    - ordem e tempo: com texto longo, o Enter chega DEPOIS do texto? com quanta folga?
    - controle conhecido (Bloco de Notas), sem o qual o instrumento mente com cara de dado;
    - validacao do proxy: o alvo em modo cru tem de reproduzir o mesmo GetConsoleMode da sessao real.

  Trava de seguranca: nenhuma tecla e injetada sem que a janela em primeiro plano seja exatamente o
  alvo que a sonda subiu. Alvo alheio = a rodada e abortada. A sonda nunca mira a sessao real.

.EXAMPLE
  pwsh -File tool/sonda_colagem.ps1
  pwsh -File tool/sonda_colagem.ps1 -Alvos notepad,cmd-cru
  pwsh -File tool/sonda_colagem.ps1 -Manual            # so inspeciona a janela que voce focar
  pwsh -File tool/sonda_colagem.ps1 -Manual -Injetar   # ... e tambem injeta nela
#>
[CmdletBinding()]
param(
    [string[]]$Alvos = @('notepad', 'cmd-cru', 'wt-cru', 'mintty-cru'),
    [switch]$Manual,
    [switch]$Injetar,
    [int]$SegundosParaFocar = 5,
    [string]$ModoEsperado = '0x0208'
)

$ErrorActionPreference = 'Stop'

# Frase curta com acento pt-BR: prova que o metodo nao corrompe caractere.
$Curta = "A" + [char]0xE7 + [char]0xE3 + "o e cora" + [char]0xE7 + [char]0xE3 + "o: hoje " + [char]0xE0 + "s 5, n" + [char]0xE3 + "o " + [char]0xE9 + "? " + [char]0xD3 + "timo."
# Tres linhas: mede quantos envios um texto multilinha vira num CLI.
$Multi = "primeira linha`nsegunda linha`nterceira linha"
# Texto longo: mede se o Enter ultrapassa o texto no caminho assincrono.
$Longo = (1..40 | ForEach-Object { "bloco $_ de texto ditado para medir a ordem de chegada" }) -join ' '

$Tmp = Join-Path $env:TEMP 'sonda_colagem'
$null = New-Item -ItemType Directory -Force -Path $Tmp

# ---------------------------------------------------------------- P/Invoke --
if (-not ('Sonda.Win' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;

namespace Sonda {
  [StructLayout(LayoutKind.Sequential)]
  public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)]
  public struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Explicit)]
  public struct InputUnion { [FieldOffset(0)] public MOUSEINPUT mi; [FieldOffset(0)] public KEYBDINPUT ki; }
  [StructLayout(LayoutKind.Sequential)]
  public struct INPUT { public uint type; public InputUnion U; }

  public static class Win {
    const uint INPUT_KEYBOARD = 1;
    const uint KEYEVENTF_KEYUP = 0x0002;
    const uint KEYEVENTF_UNICODE = 0x0004;
    const ushort VK_CONTROL = 0x11, VK_SHIFT = 0x10, VK_INSERT = 0x2D;

    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string title);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder b, int max);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder b, int max);
    [DllImport("user32.dll", SetLastError = true)] public static extern uint SendInput(uint n, INPUT[] p, int cb);
    [DllImport("user32.dll", SetLastError = true)] public static extern IntPtr SendMessageTimeout(IntPtr h, uint msg, IntPtr wp, IntPtr lp, uint flags, uint ms, out IntPtr res);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr wp, StringBuilder lp);


    public static string ClasseDe(IntPtr h) { var b = new StringBuilder(256); GetClassName(h, b, 256); return b.ToString(); }
    public static string TituloDe(IntPtr h) { var b = new StringBuilder(512); GetWindowText(h, b, 512); return b.ToString(); }

    // Mesma danca do plugin do Dito (ForceForeground): o Windows exige anexar as filas de entrada.
    public static bool TrazerParaFrente(IntPtr alvo) {
      if (IsIconic(alvo)) ShowWindow(alvo, 9);
      uint meu = GetCurrentThreadId();
      uint pid; uint dele = GetWindowThreadProcessId(alvo, out pid);
      bool anexou = (meu != dele) && AttachThreadInput(meu, dele, true);
      bool ok = SetForegroundWindow(alvo);
      if (anexou) AttachThreadInput(meu, dele, false);
      return ok;
    }

    static INPUT Tecla(ushort vk, bool up) {
      var i = new INPUT(); i.type = INPUT_KEYBOARD;
      i.U.ki.wVk = vk; i.U.ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
      return i;
    }

    // Devolve quantos eventos o SendInput inseriu de fato -- 0 significa recusado (UIPI, por ex).
    public static uint Acorde(bool ctrl, bool shift, ushort vk) {
      var l = new System.Collections.Generic.List<INPUT>();
      if (ctrl) l.Add(Tecla(VK_CONTROL, false));
      if (shift) l.Add(Tecla(VK_SHIFT, false));
      l.Add(Tecla(vk, false)); l.Add(Tecla(vk, true));
      if (shift) l.Add(Tecla(VK_SHIFT, true));
      if (ctrl) l.Add(Tecla(VK_CONTROL, true));
      var a = l.ToArray();
      return SendInput((uint)a.Length, a, Marshal.SizeOf(typeof(INPUT)));
    }

    public static uint ShiftInsert() { return Acorde(false, true, VK_INSERT); }

    public static uint Enter() { return Acorde(false, false, 0x0D); }

    // Digita como unidades UTF-16: nao depende de atalho nenhum do destino.
    // Em blocos, reconferindo o foreground entre eles: uma digitacao longa que perde o foco no meio
    // despeja o resto na janela do usuario -- ja aconteceu, e e o motivo desta guarda existir.
    public static uint Digitar(IntPtr alvo, string texto) {
      const int BLOCO = 32;
      uint total = 0;
      for (int i = 0; i < texto.Length; i += BLOCO) {
        if (GetForegroundWindow() != alvo) return 0;
        string parte = texto.Substring(i, Math.Min(BLOCO, texto.Length - i));
        var l = new System.Collections.Generic.List<INPUT>();
        foreach (char c in parte) {
          var d = new INPUT(); d.type = INPUT_KEYBOARD; d.U.ki.wScan = c; d.U.ki.dwFlags = KEYEVENTF_UNICODE;
          var u = new INPUT(); u.type = INPUT_KEYBOARD; u.U.ki.wScan = c; u.U.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
          l.Add(d); l.Add(u);
        }
        var a = l.ToArray();
        total += SendInput((uint)a.Length, a, Marshal.SizeOf(typeof(INPUT)));
        System.Threading.Thread.Sleep(15);
      }
      return total;
    }

    // Todo acorde tambem so sai com o alvo em primeiro plano.
    public static uint AcordeSeguro(IntPtr alvo, bool ctrl, bool shift, ushort vk) {
      if (GetForegroundWindow() != alvo) return 0;
      return Acorde(ctrl, shift, vk);
    }

    // 0xFFF1 = ID_CONSOLE_PASTE, o "Colar" do menu de sistema do conhost.
    // SendMessageTimeout e nao PostMessage: o BOOL do Post so diz que entrou na fila.
    public static string ColarPeloMenuDoConsole(IntPtr h) {
      IntPtr res;
      IntPtr ok = SendMessageTimeout(h, 0x0111, new IntPtr(0xFFF1), IntPtr.Zero, 0x0002, 1500, out res);
      return ok == IntPtr.Zero ? "timeout/erro" : "entregue";
    }

    public static string TextoDoEdit(IntPtr hEdit) {
      var b = new StringBuilder(65536);
      SendMessage(hEdit, 0x000D /*WM_GETTEXT*/, new IntPtr(65536), b);
      return b.ToString();
    }

  }
}
'@
}

# ------------------------------------------------------------------ apoio ---
function Passo($t) { Write-Host ''; Write-Host "== $t" -ForegroundColor Cyan }
function Nota($t) { Write-Host "   $t" -ForegroundColor DarkGray }
function Alerta($t) { Write-Host "   $t" -ForegroundColor Yellow }

function Aguardar([scriptblock]$cond, [int]$ms = 8000) {
    $fim = [Environment]::TickCount + $ms
    while ([Environment]::TickCount -lt $fim) {
        if (& $cond) { return $true }
        Start-Sleep -Milliseconds 120
    }
    return $false
}

# Le o JSONL do alvo cru e devolve os eventos ainda nao consumidos.
function LerEventos($arquivo) {
    if (-not (Test-Path $arquivo)) { return @() }
    $l = Get-Content $arquivo -ErrorAction SilentlyContinue
    if (-not $l) { return @() }
    @($l | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ })
}

# Delegado a um processo separado: AttachConsole exige FreeConsole, que destruiria o console daqui.
function ModoDoConsole([int]$alvo, [uint32]$definir = 0) {
    $arq = Join-Path $Tmp "modo_$alvo.txt"
    Remove-Item $arq -ErrorAction SilentlyContinue
    $ps1 = Join-Path $PSScriptRoot 'ler_modo_console.ps1'
    & pwsh -NoProfile -File $ps1 -Alvo $alvo -Saida $arq -Definir $definir *> $null
    if (Test-Path $arq) { return (Get-Content $arq -Raw).Trim() }
    return '(nao consegui ler)'
}

function Normalizar([string]$t) { return ($t -replace "`r`n", "`n") }

function Resumir($eventos, $esperado) {
    $texto = ($eventos | ForEach-Object { $_.texto }) -join ''
    $hex = ($eventos | ForEach-Object { $_.hex }) -join ''
    [pscustomobject]@{
        Texto     = $texto
        Chegou    = (Normalizar $texto).Contains((Normalizar $esperado))
        Bracketed = $hex.Contains('1b5b3230307e')          # ESC[200~
        Enters    = ([regex]::Matches($texto, "[`r`n]")).Count
        Ctrl_V_cru = ($hex -split '(..)' | Where-Object { $_ -eq '16' }).Count -gt 0  # 0x16 = SYN
        Chunks    = $eventos.Count
        PrimeiroMs = if ($eventos.Count) { $eventos[0].ms } else { $null }
        UltimoMs   = if ($eventos.Count) { $eventos[-1].ms } else { $null }
    }
}

# --------------------------------------------------------------- alvos ------
$node = (Get-Command node -ErrorAction SilentlyContinue).Source
$scriptCru = Join-Path $PSScriptRoot 'sonda_alvo_cru.js'
$mintty = 'C:\Program Files\Git\usr\bin\mintty.exe'
$wt = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\wt.exe'

# Um .bat por alvo: passar caminho com aspas por Start-Process + cmd /k perde as aspas no caminho.
function BatDoAlvo($id, $saida) {
    $bat = Join-Path $Tmp "subir_$id.bat"
    @"
@echo off
chcp 65001 >nul
"$node" "$scriptCru" "$saida"
"@ | Set-Content -Path $bat -Encoding ASCII
    return $bat
}

function SubirAlvo($id, $saida) {
    switch ($id) {
        'notepad'    { return Start-Process notepad.exe -PassThru }
        'cmd-cru'    { return Start-Process cmd.exe -ArgumentList '/k', (BatDoAlvo $id $saida) -PassThru }
        'wt-cru'     { Start-Process $wt -ArgumentList 'cmd.exe', '/k', (BatDoAlvo $id $saida) | Out-Null; return $null }
        'mintty-cru' { return Start-Process $mintty -ArgumentList '-h', 'always', '-e', $node, $scriptCru, $saida -PassThru }
        default      { throw "alvo desconhecido: $id" }
    }
}

# O wt e o mintty nao devolvem janela no processo que o Start-Process entrega: o wt.exe do
# WindowsApps e um lancador, e o mintty abre a janela num processo irmao. Procurar por nome.
function AcharJanela($id, $proc) {
    $porNome = @{ 'wt-cru' = 'WindowsTerminal'; 'mintty-cru' = 'mintty' }[$id]
    if ($porNome) {
        # Laco direto: um scriptblock passado a outra funcao nao enxerga a variavel local desta.
        $fim = [Environment]::TickCount + 20000
        while ([Environment]::TickCount -lt $fim) {
            $p = Get-Process $porNome -ErrorAction SilentlyContinue |
                 Where-Object { $_.MainWindowHandle -ne 0 } |
                 Sort-Object StartTime -Descending | Select-Object -First 1
            if ($p) { return @{ h = $p.MainWindowHandle; proc = $p } }
            Start-Sleep -Milliseconds 200
        }
        return $null
    }
    [void](Aguardar { $proc.Refresh(); $proc.MainWindowHandle -ne 0 } 20000)
    $proc.Refresh()
    if ($proc.MainWindowHandle -eq 0) { return $null }
    return @{ h = $proc.MainWindowHandle; proc = $proc }
}

# Qual processo dentro do alvo tem o console cru (o node), para conferir o GetConsoleMode.
function PidDoNode($janelaPid, $saida) {
    $alvo = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
            Where-Object { $_.CommandLine -and $_.CommandLine.Contains($saida) }
    if ($alvo) { return ($alvo | Select-Object -First 1).ProcessId }
    return $janelaPid
}

function Inspecionar($h) {
    $procId = 0
    [void][Sonda.Win]::GetWindowThreadProcessId($h, [ref]$procId)
    $nome = try { (Get-Process -Id $procId).ProcessName } catch { '?' }
    [pscustomobject]@{
        Classe = [Sonda.Win]::ClasseDe($h)
        Titulo = [Sonda.Win]::TituloDe($h)
        Proc   = "$nome ($procId)"
        ProcId = $procId
    }
}

$Metodos = @(
    @{ nome = 'Ctrl+V';            exec = { param($h, $t) [Sonda.Win]::AcordeSeguro($h, $true, $false, 0x56) } }
    @{ nome = 'Ctrl+Shift+V';      exec = { param($h, $t) [Sonda.Win]::AcordeSeguro($h, $true, $true, 0x56) } }
    @{ nome = 'Shift+Insert';      exec = { param($h, $t) [Sonda.Win]::AcordeSeguro($h, $false, $true, 0x2D) } }
    @{ nome = 'WM_COMMAND 0xFFF1'; exec = { param($h, $t) [Sonda.Win]::ColarPeloMenuDoConsole($h) } }
    @{ nome = 'SendInput UNICODE'; exec = { param($h, $t) [Sonda.Win]::Digitar($h, $t) } }
)

# ------------------------------------------------------------- MANUAL -------
if ($Manual) {
    Passo 'Modo manual: foque a janela que voce quer inspecionar'
    for ($i = $SegundosParaFocar; $i -gt 0; $i--) { Write-Host "   $i..."; Start-Sleep -Seconds 1 }
    $h = [Sonda.Win]::GetForegroundWindow()
    $info = Inspecionar $h
    $info | Format-List
    Nota ('modo do console: ' + (ModoDoConsole $info.ProcId))
    if (-not $Injetar) { Nota 'somente inspecao (use -Injetar para tambem injetar nesta janela)'; return }
    Set-Clipboard -Value $Curta
    foreach ($m in $Metodos) {
        Start-Sleep -Milliseconds 400
        Write-Host ("   {0,-22} -> {1}" -f $m.nome, (& $m.exec $h $Curta))
        Start-Sleep -Milliseconds 900
    }
    Nota 'confira a olho o que chegou na janela alvo'
    return
}

# ------------------------------------------------------------ AUTOMATICO ----
Write-Host ''
Write-Host 'SONDA DE COLAGEM -- qual metodo realmente cola, por classe de janela' -ForegroundColor Green
Nota "node: $node"
Nota "modo de console esperado no alvo cru: $ModoEsperado (medido na sessao real do Claude Code)"

$linhas = @()

foreach ($id in $Alvos) {
    Passo "alvo: $id"
    $saida = Join-Path $Tmp "$id.jsonl"
    Remove-Item $saida -ErrorAction SilentlyContinue

    $proc = SubirAlvo $id $saida
    Start-Sleep -Milliseconds 1800
    $j = AcharJanela $id $proc
    if (-not $j) { Alerta 'NAO achei a janela do alvo -- pulando'; continue }

    $info = Inspecionar $j.h
    Nota "classe=$($info.Classe)  processo=$($info.Proc)"

    $cru = $id -ne 'notepad'
    $modo = '(n/a)'
    if ($cru) {
        $pidNode = PidDoNode $info.ProcId $saida
        # O Node so tira LINE/ECHO/PROCESSED; o VT_INPUT do Claude Code entra aqui.
        $modo = ModoDoConsole $pidNode ([Convert]::ToUInt32($ModoEsperado, 16))
        Nota "modo do console (pid $pidNode): $modo"
        [void](Aguardar { Test-Path $saida } 15000)
        if (-not (Test-Path $saida)) {
            Alerta "ALVO MORTO: o node nao subiu (sem $saida). Nada a medir aqui -- pulando."
            if ($j.proc) { Stop-Process -Id $j.proc.Id -Force -ErrorAction SilentlyContinue }
            continue
        }
        if (-not $modo.StartsWith($ModoEsperado)) {
            Alerta "PROXY INVALIDO: esperava $ModoEsperado, veio $modo. A tabela deste alvo NAO vale -- pulando."
            if ($j.proc) { Stop-Process -Id $j.proc.Id -Force -ErrorAction SilentlyContinue }
            continue
        }
    }

    # No Bloco de Notas o texto e lido do controle EDIT filho.
    $edit = [IntPtr]::Zero
    if ($id -eq 'notepad') {
        $edit = [Sonda.Win]::FindWindowEx($j.h, [IntPtr]::Zero, 'Edit', $null)
        if ($edit -eq [IntPtr]::Zero) { $edit = [Sonda.Win]::FindWindowEx($j.h, [IntPtr]::Zero, 'RichEditD2DPT', $null) }
    }

    $abortou = $false
    foreach ($amostra in @(
            @{ rotulo = 'curta';  texto = $Curta },
            @{ rotulo = 'multi';  texto = $Multi },
            @{ rotulo = 'longa';  texto = $Longo })) {

        if ($abortou) { break }
        foreach ($m in $Metodos) {
            Set-Clipboard -Value $amostra.texto
            Start-Sleep -Milliseconds 250

            # TRAVA: so injeta se o alvo estiver mesmo em primeiro plano.
            # Retentativa porque o Windows bloqueia SetForegroundWindow em rajada sem input do usuario.
            for ($tent = 0; $tent -lt 4; $tent++) {
                if ([Sonda.Win]::GetForegroundWindow() -eq $j.h) { break }
                [void][Sonda.Win]::TrazerParaFrente($j.h)
                Start-Sleep -Milliseconds 350
            }
            if ([Sonda.Win]::GetForegroundWindow() -ne $j.h) {
                $linhas += [pscustomobject]@{ Alvo = $id; Classe = $info.Classe; Amostra = $amostra.rotulo
                                              Metodo = $m.nome; Retorno = '-'; Chegou = 'ABORTADO (sem foco)'
                                              Quebras = '-'; Bracketed = '-'; MsTexto = '-'; EnterDepois = '-' }
                continue
            }

            $antes = (LerEventos $saida).Count
            $ret = & $m.exec $j.h $amostra.texto
            # Mesmo intervalo do app (PasteService.beforeEnter = 250 ms) antes do Enter.
            Start-Sleep -Milliseconds 250
            if ([Sonda.Win]::GetForegroundWindow() -ne $j.h) {
                Alerta 'O FOCO ESCAPOU durante a injecao -- rodada abortada, nenhum Enter enviado.'
                $abortou = $true
                break
            }
            [void][Sonda.Win]::Enter()
            Start-Sleep -Milliseconds 1500

            if ($id -eq 'notepad') {
                $lido = if ($edit -ne [IntPtr]::Zero) { [Sonda.Win]::TextoDoEdit($edit) } else { '(sem edit)' }
                $ok = (Normalizar $lido).Contains((Normalizar $amostra.texto))
                $linhas += [pscustomobject]@{ Alvo = $id; Classe = $info.Classe; Amostra = $amostra.rotulo
                                              Metodo = $m.nome; Retorno = $ret
                                              Chegou = $(if ($ok) { 'CHEGOU' } elseif ($lido.Length) { 'PARCIAL' } else { 'nada' })
                                              Quebras = ([regex]::Matches($lido, "`n")).Count
                                              Bracketed = 'n/a'; MsTexto = '-'; EnterDepois = 'n/a' }
                # limpa o campo para a proxima amostra
                [void][Sonda.Win]::Acorde($true, $false, 0x41)  # Ctrl+A
                [void][Sonda.Win]::Acorde($false, $false, 0x2E) # Delete
                Start-Sleep -Milliseconds 200
            }
            else {
                $todos = LerEventos $saida
                $novos = if ($todos.Count -gt $antes) { $todos[$antes..($todos.Count - 1)] } else { @() }
                $r = Resumir $novos $amostra.texto
                # Reconstroi o fluxo ate o primeiro CR: era o texto completo, ou um Enter vazio?
                $antesDoEnter = ''
                foreach ($e in $novos) {
                    if (($e.hex -split '(..)' | Where-Object { $_ -eq '0d' }).Count -gt 0) { break }
                    $antesDoEnter += $e.texto
                }
                $textoAntesDoEnter = (Normalizar $antesDoEnter).Contains((Normalizar $amostra.texto))
                $linhas += [pscustomobject]@{ Alvo = $id; Classe = $info.Classe; Amostra = $amostra.rotulo
                                              Metodo = $m.nome; Retorno = $ret
                                              Chegou = $(if ($r.Chegou) { 'CHEGOU' }
                                                         elseif ($r.Ctrl_V_cru) { 'so 0x16 (SYN)' }
                                                         elseif ($r.Texto.Length) { 'PARCIAL' }
                                                         else { 'nada' })
                                              Quebras = $r.Enters
                                              Bracketed = $(if ($r.Bracketed) { 'sim' } else { 'nao' })
                                              MsTexto = $(if ($null -ne $r.UltimoMs) { $r.UltimoMs } else { '-' })
                                              EnterDepois = $(if ($textoAntesDoEnter) { 'sim' } else { 'NAO' }) }
            }
            Write-Host ("   {0,-7} {1,-22} ret={2,-9} -> {3}" -f $amostra.rotulo, $m.nome, $ret, $linhas[-1].Chegou)
        }
    }

    if ($j.proc) { Stop-Process -Id $j.proc.Id -Force -ErrorAction SilentlyContinue }
    # O node e filho do cmd e sobrevivia a morte do pai, virando alvo orfao.
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains('sonda_alvo_cru') } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-Process WindowsTerminal, notepad -ErrorAction SilentlyContinue |
        Where-Object { $_.StartTime -gt (Get-Date).AddMinutes(-3) } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

Passo 'TABELA'
$linhas | Format-Table -AutoSize | Out-String -Width 220 | Write-Host
$csv = Join-Path $Tmp 'resultado.csv'
$linhas | Export-Csv -Path $csv -NoTypeInformation -Encoding UTF8
Nota "tabela salva em $csv"
