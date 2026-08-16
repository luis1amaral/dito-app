# Monta o instalador .exe do Dito, do zero.
#
#   powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1
#   ... -SemPortao   pula ruff e pytest (só quando você acabou de rodar)
#   ... -SoBundle    para no PyInstaller e não compila o instalador
#
# Sai em build\windows\installer\dito-<versao>-setup.exe, com o SHA256SUMS.txt ao lado — esse
# arquivo NÃO é enfeite: src/dito/update.py se recusa a rodar um instalador sem hash publicado.

[CmdletBinding()]
param(
    [switch]$SemPortao,
    [switch]$SoBundle
)

$ErrorActionPreference = 'Stop'

$Raiz      = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Py        = Join-Path $Raiz '.venv\Scripts\python.exe'
$Saida     = Join-Path $Raiz 'build\windows'
$Bundle    = Join-Path $Saida 'dist\Dito'
$Instalador = Join-Path $Saida 'installer'

function Passo($t) { Write-Host "`n» $t" -ForegroundColor White }
function Ok($t)    { Write-Host "  + $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "  ! $t" -ForegroundColor Yellow }

function Achar-Iscc {
    $candidatos = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    foreach ($c in $candidatos) { if ($c -and (Test-Path $c)) { return $c } }
    $doPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($doPath) { return $doPath.Source }
    return $null
}

if (-not (Test-Path $Py)) { throw "sem venv de desenvolvimento em $Raiz\.venv" }

Passo 'Conferindo que a árvore está sã'
if ($SemPortao) {
    Aviso 'portão pulado a pedido'
} else {
    & (Join-Path $Raiz '.venv\Scripts\ruff.exe') check $Raiz | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'ruff reprovou' }
    Ok 'lint limpo'
    & $Py -m pytest -q -m 'not x11 and not winkeys' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'a suíte reprovou' }
    Ok 'testes verdes'
}

$Versao = & $Py -c "import tomllib,pathlib;print(tomllib.loads(pathlib.Path(r'$Raiz/pyproject.toml').read_text('utf-8'))['project']['version'])"
if ($LASTEXITCODE -ne 0 -or -not $Versao) { throw 'não consegui ler a versão do pyproject.toml' }
Ok "versão $Versao"

Passo 'Montando o bundle (PyInstaller)'
# O .spec repete o --noconsole, os hidden imports e os .mo; nada disso vira flag aqui.
& (Join-Path $Raiz '.venv\Scripts\pyinstaller.exe') --noconfirm `
    --distpath (Join-Path $Saida 'dist') `
    --workpath (Join-Path $Saida 'work') `
    (Join-Path $PSScriptRoot 'dito.spec')
if ($LASTEXITCODE -ne 0) { throw 'o PyInstaller reprovou' }

foreach ($exigido in @('dito.exe', 'ditow.exe', '_internal\dito\locales\pt_BR\LC_MESSAGES\dito.mo')) {
    if (-not (Test-Path (Join-Path $Bundle $exigido))) { throw "o bundle saiu sem $exigido" }
}
$tamanho = (Get-ChildItem $Bundle -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Ok ("bundle com {0:N0} MB, com os dois .exe e o catálogo pt_BR" -f $tamanho)

if ($SoBundle) {
    Write-Host ''
    Write-Host "  Bundle em $Bundle" -ForegroundColor Green
    Write-Host ''
    exit 0
}

Passo 'Compilando o instalador (Inno Setup)'
$Iscc = Achar-Iscc
if (-not $Iscc) { throw 'ISCC.exe não encontrado — instale o Inno Setup 6' }
& $Iscc "/DMyAppVersion=$Versao" (Join-Path $PSScriptRoot 'dito.iss') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'o Inno Setup reprovou' }

$Exe = Join-Path $Instalador "dito-$Versao-setup.exe"
if (-not (Test-Path $Exe)) { throw "o Inno Setup não deixou $Exe" }

Passo 'Publicando o hash'
$hash = (Get-FileHash $Exe -Algorithm SHA256).Hash.ToLower()
"$hash  $(Split-Path $Exe -Leaf)" | Set-Content -Path (Join-Path $Instalador 'SHA256SUMS.txt') -Encoding ASCII
Ok "sha256 $hash"

Write-Host ''
Write-Host ("  Pronto: $Exe ({0:N0} MB)" -f ((Get-Item $Exe).Length / 1MB)) -ForegroundColor Green
Write-Host '  Suba os DOIS arquivos no release do GitHub: o .exe e o SHA256SUMS.txt' -ForegroundColor Green
Write-Host ''
