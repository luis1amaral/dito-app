# Entrada unica do portao de qualidade. Tres estados, de proposito:
#   exit 0 = PASSA        tudo que existe foi provado
#   exit 1 = FALHA        alguma checagem reprovou
#   exit 2 = INCOMPLETO   ha camada que ainda nao pode ser provada -- NUNCA confundir com verde
param([switch]$Rapido)
$ErrorActionPreference = 'Continue'
$raiz = Split-Path $PSScriptRoot -Parent

# An env var set for one layer leaked into every layer after it: the app wrote to another data dir
# and the gates read the wrong log. Set it, run, always put it back.
function RodarIsolado([scriptblock]$corpo, [hashtable]$vars) {
    $antigo = @{}
    foreach ($k in $vars.Keys) {
        $antigo[$k] = [Environment]::GetEnvironmentVariable($k)
        [Environment]::SetEnvironmentVariable($k, $vars[$k])
    }
    try { & $corpo }
    finally {
        foreach ($k in $vars.Keys) {
            # Restoring as an empty string is not the same as removing it: the app would read '' and
            # write its data to a relative path inside the project.
            if ([string]::IsNullOrEmpty($antigo[$k])) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
            else { [Environment]::SetEnvironmentVariable($k, $antigo[$k]) }
        }
    }
}

$camadas = @(
    @{ nome = 'typecheck (o contrato compila?)'; cmd = { npx tsc --noEmit } }
    @{ nome = 'lint (oxlint)';                   cmd = { npx oxlint } }
    @{ nome = 'regras do projeto';               cmd = { npx tsx "$PSScriptRoot\code-quality.ts" } }
    @{ nome = 'motor (regressao por fixture)';   cmd = { node "$PSScriptRoot\engine.mjs" } }
    @{ nome = 'mutacao (portao reprova?)';       cmd = { node "$PSScriptRoot\mutation.mjs" }; pular = $Rapido }
    @{ nome = 'modelos (baixa e trava?)';        cmd = { RodarIsolado { npx tsx "$PSScriptRoot\models.mts" } @{ DITO_APPDATA = "$env:TEMP\dito-gate" } } }
    @{ nome = 'cortador (corta no silencio?)'; cmd = { npx tsx "$PSScriptRoot\chunker.ts" } }
    @{ nome = 'nativo (hook instala?)';          cmd = { node "$PSScriptRoot\native.mjs" } }
    @{ nome = 'tecla (a tecla dita mesmo?)';     cmd = { node "$PSScriptRoot\hotkey.mjs" } }
    @{ nome = 'segurar (5 ciclos e teto)';       cmd = { node "$PSScriptRoot\hold.mjs" } }
    @{ nome = 'fumaca (o app sobe?)';            cmd = { pwsh -NoProfile -File "$PSScriptRoot\smoke.ps1" } }
    @{ nome = 'colagem (console cru)';           cmd = { node "$PSScriptRoot\paste-wiring.mjs" } }
    @{ nome = 'colagem (via gui)';               cmd = { node "$PSScriptRoot\paste-targets.mjs" } }
    @{ nome = 'feed (o app acha a versao?)';     cmd = { node "$PSScriptRoot\update-feed.mjs" } }
)

Push-Location $raiz
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
Pop-Location

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
