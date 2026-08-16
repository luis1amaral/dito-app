# Instala o Dito nesta máquina Windows, fora do repositório.
#
#   powershell -ExecutionPolicy Bypass -File packaging\windows\instalar.ps1
#   ... -ComWindows      liga o "iniciar com o Windows" (desligado por padrão)
#   ... -SemPortao       pula ruff e pytest (só quando você acabou de rodar)
#   ... -Desinstalar     remove atalhos, PATH e a venv — NUNCA as gravações
#
# O equivalente do tools/instalar.sh do Linux, sem .deb: cria uma venv própria em
# %LOCALAPPDATA%\dito\venv e instala o projeto nela, para o app não depender de onde o
# repositório está. O instalador de distribuição (PyInstaller + Inno Setup) é outro assunto:
# ver packaging/windows/README.md.

[CmdletBinding()]
param(
    [switch]$ComWindows,
    [switch]$SemPortao,
    [switch]$Desinstalar
)

$ErrorActionPreference = 'Stop'

$Raiz     = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Base     = Join-Path $env:LOCALAPPDATA 'dito'
$Venv     = Join-Path $Base 'venv'
$Bin      = Join-Path $Base 'bin'
$Scripts  = Join-Path $Venv 'Scripts'
$MenuDir  = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$Atalho   = Join-Path $MenuDir 'Dito.lnk'
$Startup  = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\Dito.lnk'

function Passo($t) { Write-Host "`n» $t" -ForegroundColor White }
function Ok($t)    { Write-Host "  + $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "  ! $t" -ForegroundColor Yellow }

function Parar-Dito {
    $exe = Join-Path $Scripts 'dito.exe'
    if (Test-Path $exe) { & $exe stop 2>&1 | Out-Null }
    Get-Process -Name 'dito', 'ditow' -ErrorAction SilentlyContinue | Stop-Process -Force
}

function Novo-Atalho($caminho, $alvo, $argumentos, $descricao) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($caminho)
    $lnk.TargetPath = $alvo
    $lnk.Arguments = $argumentos
    $lnk.WorkingDirectory = Split-Path $alvo
    $lnk.Description = $descricao
    $lnk.Save()
}

# ---------------------------------------------------------------- desinstalar

if ($Desinstalar) {
    Passo 'Encerrando o Dito'
    Parar-Dito
    Ok 'parado'

    Passo 'Removendo atalhos e PATH'
    foreach ($a in @($Atalho, $Startup)) {
        if (Test-Path $a) { Remove-Item $a -Force; Ok "removi $(Split-Path $a -Leaf)" }
    }
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($userPath -and $userPath.Split(';') -contains $Bin) {
        $novo = ($userPath.Split(';') | Where-Object { $_ -and $_ -ne $Bin }) -join ';'
        [Environment]::SetEnvironmentVariable('Path', $novo, 'User')
        Ok 'tirei o bin do PATH do usuário'
    }

    Passo 'Removendo a venv'
    foreach ($d in @($Venv, $Bin)) {
        if (Test-Path $d) { Remove-Item $d -Recurse -Force; Ok "removi $d" }
    }

    # The recordings and the transcriptions stay, exactly like the .deb's postrm on Linux.
    Write-Host ''
    Aviso "as gravações NÃO foram apagadas: $(Join-Path $Base 'state')"
    Aviso "a biblioteca NÃO foi apagada: $(Join-Path $env:USERPROFILE 'Documents\Dito')"
    Write-Host ''
    exit 0
}

# ------------------------------------------------------------------- instalar

Passo 'Conferindo que a árvore está sã'
if ($SemPortao) {
    Aviso 'portão pulado a pedido'
} else {
    $repoPy = Join-Path $Raiz '.venv\Scripts\python.exe'
    if (-not (Test-Path $repoPy)) { throw "sem venv de desenvolvimento em $Raiz\.venv" }
    & (Join-Path $Raiz '.venv\Scripts\ruff.exe') check $Raiz | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'ruff reprovou' }
    Ok 'lint limpo'
    & $repoPy -m pytest -q -m 'not x11 and not winkeys' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'a suíte reprovou' }
    Ok 'testes verdes'
}

Passo 'Encerrando o Dito que está rodando'
Parar-Dito
Ok 'parado'

Passo "Preparando a venv em $Venv"
if (-not (Test-Path $Venv)) {
    $py = (Get-Command py -ErrorAction SilentlyContinue)
    if ($py) { & py -3 -m venv $Venv } else { & python -m venv $Venv }
    Ok 'venv criada'
} else {
    Ok 'venv já existia'
}
& (Join-Path $Scripts 'python.exe') -m pip install --upgrade pip --quiet
& (Join-Path $Scripts 'python.exe') -m pip install --upgrade $Raiz --quiet
if ($LASTEXITCODE -ne 0) { throw 'a instalação na venv falhou' }
$versao = (& (Join-Path $Scripts 'dito.exe') --version) -join ' '
Ok "instalado: $versao"

Passo "Deixando o comando `dito` no PATH"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
# A shim instead of a copy: the .exe launchers carry the venv path baked in and do not relocate.
@"
@echo off
"$(Join-Path $Scripts 'dito.exe')" %*
"@ | Set-Content -Path (Join-Path $Bin 'dito.cmd') -Encoding ASCII
Ok 'dito.cmd criado'

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $userPath) { $userPath = '' }
if ($userPath.Split(';') -notcontains $Bin) {
    [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $Bin), 'User')
    Ok 'bin adicionado ao PATH do usuário (vale em terminal novo)'
} else {
    Ok 'bin já estava no PATH'
}

Passo 'Atalho no Menu Iniciar'
Novo-Atalho $Atalho (Join-Path $Scripts 'ditow.exe') 'ui' 'Dito — ditado por voz offline'
Ok 'Dito.lnk criado'

Passo 'Iniciar com o Windows'
if ($ComWindows) {
    # `listen` and not `ui`: at login only the tray icon may appear, never a window.
    Novo-Atalho $Startup (Join-Path $Scripts 'ditow.exe') 'listen' 'Dito — ditado por voz'
    Ok 'ligado — sobe calado, só o ícone da bandeja'
} else {
    if (Test-Path $Startup) { Remove-Item $Startup -Force }
    Aviso 'desligado (padrão). Para ligar: -ComWindows'
}

Write-Host ''
Write-Host '  Pronto. Num terminal NOVO:' -ForegroundColor Green
Write-Host '    dito doctor     diagnostica microfone, mudo e modelo'
Write-Host '    dito listen     sobe o ditado (bandeja, sem janela)'
Write-Host '    dito status     responde na hora'
Write-Host ''
