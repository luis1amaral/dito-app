# Sobe o app compilado de verdade e exige prova de boot. Nenhum flutter test pega o que este pega:
# a 1.7.0 saiu com 220 testes verdes e morria em 0xC0000005 antes da primeira linha de log.
param(
    [string]$Bundle = "$PSScriptRoot\..\build\windows\x64\runner\Release",
    [int]$TimeoutSegundos = 40
)
$ErrorActionPreference = 'Stop'

$exe = Join-Path $Bundle 'dito_app.exe'
if (-not (Test-Path $exe)) { Write-Host "FUMACA: FALHA - nao achei $exe" -ForegroundColor Red; exit 1 }

$log = Join-Path $env:LOCALAPPDATA 'dito\logs\app.log'
$marca = 'boot completo'

# O tema nunca pinta preto puro (#0E0E13 e o fundo), entao preto puro e area que o swapchain
# nao apresentou -- a faixa morta que ninguem via ate abrir a janela e olhar. Ver armadilha 4.13.
function AreaMortaPorcento($processId) {
    Add-Type -AssemblyName System.Drawing
    if (-not ('WinGeo' -as [type])) {
        Add-Type @'
using System; using System.Runtime.InteropServices;
public class WinGeo {
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  public struct RECT { public int Left, Top, Right, Bottom; }
  public struct POINT { public int X, Y; }
}
'@
    }
    $h = (Get-Process -Id $processId).MainWindowHandle
    if ($h -eq 0) { return -1 }
    $r = New-Object WinGeo+RECT
    if (-not [WinGeo]::GetClientRect($h, [ref]$r)) { return -1 }
    $p = New-Object WinGeo+POINT
    if (-not [WinGeo]::ClientToScreen($h, [ref]$p)) { return -1 }
    $w = $r.Right - $r.Left; $ht = $r.Bottom - $r.Top
    if ($w -lt 100 -or $ht -lt 100) { return -1 }

    $bmp = New-Object System.Drawing.Bitmap $w, $ht
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($p.X, $p.Y, 0, 0, $bmp.Size)
    $pretos = 0; $total = 0
    for ($y = 0; $y -lt $ht; $y += 4) {
        for ($x = 0; $x -lt $w; $x += 4) {
            $c = $bmp.GetPixel($x, $y)
            if ($c.R -eq 0 -and $c.G -eq 0 -and $c.B -eq 0) { $pretos++ }
            $total++
        }
    }
    $g.Dispose(); $bmp.Dispose()
    if ($total -eq 0) { return -1 }
    return [math]::Round(100.0 * $pretos / $total, 1)
}

function Falhar($motivo, $pid_) {
    if ($pid_) { Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue }
    Write-Host "FUMACA: FALHA - $motivo" -ForegroundColor Red
    $evt = Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'; StartTime=(Get-Date).AddMinutes(-2)} -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($evt) { Write-Host "  modulo com falha: $((($evt.Message -split "`n") | Where-Object { $_ -match 'modulo com falha|faulting module' }) -join ' ')" -ForegroundColor Red }
    exit 1
}

# Uma instancia velha segura o mutex e o app novo sai sem abrir nada: mata antes de medir.
Get-Process dito_app, dito -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

$linhasAntes = if (Test-Path $log) { (Get-Content $log -ErrorAction SilentlyContinue | Measure-Object -Line).Lines } else { 0 }

foreach ($modo in @(@{ nome = 'bandeja'; args = @('--startup') }, @{ nome = 'janela'; args = @() })) {
    Write-Host "== fumaca: modo $($modo.nome)"
    $p = if ($modo.args.Count) { Start-Process $exe -ArgumentList $modo.args -PassThru } else { Start-Process $exe -PassThru }

    $bootou = $false
    for ($i = 0; $i -lt $TimeoutSegundos; $i++) {
        Start-Sleep -Seconds 1
        if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { Falhar "o app morreu no modo $($modo.nome)" $null }
        $linhas = if (Test-Path $log) { Get-Content $log -ErrorAction SilentlyContinue } else { @() }
        if ($linhas.Count -gt $linhasAntes -and ($linhas | Select-Object -Last ($linhas.Count - $linhasAntes)) -match $marca) { $bootou = $true; break }
    }
    if (-not $bootou) { Falhar "sem '$marca' no log em ${TimeoutSegundos}s (modo $($modo.nome))" $p.Id }

    if ($modo.nome -eq 'janela') {
        Start-Sleep -Seconds 2
        $morto = AreaMortaPorcento $p.Id
        if ($morto -lt 0) {
            Falhar "nao consegui medir a janela (sem handle ou pequena demais)" $p.Id
        }
        Write-Host ("   area morta (preto puro): {0}%" -f $morto)
        if ($morto -gt 3) { Falhar "faixa preta na janela: $morto% dos pixels sao preto puro" $p.Id }
    }

    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    $linhasAntes = (Get-Content $log | Measure-Object -Line).Lines
}

Write-Host "FUMACA: PASSA - o app sobe nos dois modos e registra boot" -ForegroundColor Green
exit 0
