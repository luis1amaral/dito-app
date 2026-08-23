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

    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    $linhasAntes = (Get-Content $log | Measure-Object -Line).Lines
}

Write-Host "FUMACA: PASSA - o app sobe nos dois modos e registra boot" -ForegroundColor Green
exit 0
