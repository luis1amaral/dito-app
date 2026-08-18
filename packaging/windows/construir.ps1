# Monta o instalador do Dito para Windows, 100% nativo C++ e sem Python.
#
#   powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1
#
# Passos: portao (analyze + test) -> build Flutter (inclui C++ whisper) -> Inno Setup -> SHA256SUMS.txt

[CmdletBinding()]
param(
    [switch]$SemPortao,
    [switch]$SoBundle,
    [string]$Destino
)

$ErrorActionPreference = 'Stop'
trap {
    Write-Host ''
    Write-Host "FALHOU: $_" -ForegroundColor Red
    exit 1
}

$Raiz = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $Raiz

function Etapa($texto) {
    Write-Host ''
    Write-Host "== $texto" -ForegroundColor Cyan
}

# --- versao: uma fonte so ---------------------------------------------------
$pubspec = Get-Content (Join-Path $Raiz 'pubspec.yaml') -Raw
if ($pubspec -notmatch '(?m)^version:\s*([0-9]+\.[0-9]+\.[0-9]+)') {
    throw 'nao achei a versao no pubspec.yaml'
}
$Versao = $Matches[1]
Write-Host "Dito $Versao (Motor C++ Nativo)" -ForegroundColor Green

# --- portao -----------------------------------------------------------------
if (-not $SemPortao) {
    Etapa 'Portao: analyze e test'
    & flutter analyze
    if ($LASTEXITCODE -ne 0) { throw 'flutter analyze reprovou' }
    & flutter test --exclude-tags live
    if ($LASTEXITCODE -ne 0) { throw 'flutter test reprovou' }
}

# --- app --------------------------------------------------------------------
Etapa 'Compilando o app Flutter e plugins C++ nativos'
& flutter build windows --release
if ($LASTEXITCODE -ne 0) { throw 'flutter build reprovou' }

$Bundle = Join-Path $Raiz 'build\windows\x64\runner\Release'
if (-not (Test-Path (Join-Path $Bundle 'dito_app.exe'))) {
    throw "o bundle nao tem dito_app.exe: $Bundle"
}

$tamanho = [math]::Round((Get-ChildItem $Bundle -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "bundle nativo completo: $tamanho MB"

if ($SoBundle) { exit 0 }

# --- instalador -------------------------------------------------------------
Etapa 'Gerando o instalador Inno Setup'
$candidatos = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$ISCC = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ISCC) {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { $ISCC = $cmd.Source }
}
if (-not $ISCC) { throw 'Inno Setup 6 nao encontrado (ISCC.exe)' }

& $ISCC "/DMyAppVersion=$Versao" (Join-Path $PSScriptRoot 'dito.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup reprovou' }

$Instalador = Join-Path $Raiz "build\windows\installer\dito-$Versao-setup.exe"
if (-not (Test-Path $Instalador)) { throw "o instalador nao apareceu em $Instalador" }

# --- checksum ---------------------------------------------------------------
# O updater recusa instalar sem hash publicado, entao isto nao e opcional.
Etapa 'Calculando o SHA256'
$hash = (Get-FileHash -Algorithm SHA256 $Instalador).Hash.ToLower()
$nome = Split-Path $Instalador -Leaf
$sums = Join-Path $Raiz 'build\windows\installer\SHA256SUMS.txt'
"$hash  $nome" | Set-Content -Path $sums -Encoding ASCII

$mb = [math]::Round((Get-Item $Instalador).Length / 1MB, 1)
Write-Host ''
Write-Host "instalador: $Instalador ($mb MB)" -ForegroundColor Green
Write-Host "sha256: $hash"

# --- entrega ----------------------------------------------------------------
if ($Destino) {
    Etapa "Copiando para $Destino"
    New-Item -ItemType Directory -Force $Destino | Out-Null
    Copy-Item $Instalador $Destino -Force
    Copy-Item $sums $Destino -Force
    Write-Host "pronto em $Destino" -ForegroundColor Green
}
