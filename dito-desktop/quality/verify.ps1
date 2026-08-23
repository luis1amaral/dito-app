# Entrada unica do portao de qualidade. Tres estados, de proposito:
#   exit 0 = PASSA        tudo que existe foi provado
#   exit 1 = FALHA        alguma checagem reprovou
#   exit 2 = INCOMPLETO   ha camada que ainda nao pode ser provada -- NUNCA confundir com verde
param([switch]$Rapido)
$ErrorActionPreference = 'Continue'
$raiz = Split-Path $PSScriptRoot -Parent

$camadas = @(
    @{ nome = 'motor (regressao por fixture)'; cmd = { node "$PSScriptRoot\engine.mjs" } }
    @{ nome = 'mutacao (portao reprova?)';     cmd = { node "$PSScriptRoot\mutation.mjs" }; pular = $Rapido }
    @{ nome = 'nativo (hook instala?)';        cmd = { node "$PSScriptRoot/native.mjs" } }
    @{ nome = 'fumaca (o app sobe?)';          cmd = { pwsh -NoProfile -File "$PSScriptRoot\smoke.ps1" } }
    @{ nome = 'colagem (cmd.exe cru)';         cmd = { & "$PSScriptRoot\paste.ps1" } }
)

$resultados = @()
foreach ($c in $camadas) {
    if ($c.pular) { $resultados += @{ nome = $c.nome; estado = 'PULADO'; code = 0 }; continue }
    Write-Host ""
    Write-Host "########## $($c.nome)" -ForegroundColor Cyan
    & $c.cmd
    $code = $LASTEXITCODE
    $estado = switch ($code) { 0 { 'PASSA' } 2 { 'PENDENTE' } default { 'FALHA' } }
    $resultados += @{ nome = $c.nome; estado = $estado; code = $code }
}

Write-Host ""
Write-Host "================ resultado ================"
foreach ($r in $resultados) {
    $cor = switch ($r.estado) { 'PASSA' { 'Green' } 'FALHA' { 'Red' } 'PULADO' { 'DarkGray' } default { 'Yellow' } }
    Write-Host ("{0,-10} {1}" -f $r.estado, $r.nome) -ForegroundColor $cor
}

if ($resultados | Where-Object { $_.estado -eq 'FALHA' }) {
    Write-Host "`nVERIFICAR: FALHA" -ForegroundColor Red
    exit 1
}
if ($resultados | Where-Object { $_.estado -eq 'PENDENTE' }) {
    Write-Host "`nVERIFICAR: INCOMPLETO - ha camada sem prova. Isto NAO e verde." -ForegroundColor Yellow
    exit 2
}
Write-Host "`nVERIFICAR: PASSA" -ForegroundColor Green
exit 0
