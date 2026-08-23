# Instala o setup.exe de verdade e exige que o app INSTALADO suba. O portao anterior media o
# bundle, nao o instalador -- e foi por essa fresta que a 1.7.0 chegou ao dono sem abrir.
param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [switch]$ManterInstalado
)
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Setup)) { Write-Host "INSTALADOR: FALHA - nao achei $Setup" -ForegroundColor Red; exit 1 }

$destino = Join-Path $env:LOCALAPPDATA 'Programs\Dito'
$exe = Join-Path $destino 'dito_app.exe'

Get-Process dito_app, dito -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

Write-Host "== instalando em silencio: $(Split-Path $Setup -Leaf)"
$proc = Start-Process $Setup -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCANCEL' -Wait -PassThru
if ($proc.ExitCode -ne 0) { Write-Host "INSTALADOR: FALHA - setup saiu com $($proc.ExitCode)" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $exe)) { Write-Host "INSTALADOR: FALHA - $exe nao existe apos instalar" -ForegroundColor Red; exit 1 }

$versao = (Get-Item $exe).VersionInfo.FileVersion
Write-Host "== instalado: $destino (versao $versao)"

# Arquivo que saiu do pacote e ficou para tras envenena a instalacao seguinte.
$orfaos = @('desktop_multi_window_plugin.dll', 'hotkey_manager_windows_plugin.dll', 'system_tray_plugin.dll')
foreach ($o in $orfaos) {
    if (Test-Path (Join-Path $destino $o)) {
        Write-Host "INSTALADOR: FALHA - sobrou $o da instalacao anterior" -ForegroundColor Red
        exit 1
    }
}

# O app instalado tem de subir; reaproveita o mesmo criterio do portao de bundle.
& (Join-Path $PSScriptRoot 'fumaca.ps1') -Bundle $destino
if ($LASTEXITCODE -ne 0) { Write-Host "INSTALADOR: FALHA - o app instalado nao sobe" -ForegroundColor Red; exit 1 }

if (-not $ManterInstalado) {
    $unins = Get-ChildItem $destino -Filter 'unins*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($unins) { Start-Process $unins.FullName -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait }
}

Write-Host "INSTALADOR: PASSA - instala, nao deixa orfao, e o app instalado sobe" -ForegroundColor Green
exit 0
