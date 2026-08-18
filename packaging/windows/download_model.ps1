param(
    [Parameter(Mandatory=$true)]
    [string]$Model
)

$ErrorActionPreference = 'Stop'
$destDir = Join-Path $env:LOCALAPPDATA 'dito\models'
New-Item -ItemType Directory -Force $destDir | Out-Null
$clean = $Model.Trim().ToLower()
$fileName = if ($clean.EndsWith('.bin')) { $clean } else { "ggml-$clean.bin" }
$target = Join-Path $destDir $fileName

if ((Test-Path $target) -and ((Get-Item $target).Length -gt 1048576)) {
    Write-Host "Modelo $fileName já existe em $target."
    exit 0
}

$url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$fileName"
$tmp = "$target.tmp"
if (Test-Path $tmp) {
    try { Remove-Item $tmp -Force } catch {}
}

Write-Host "Baixando $fileName de $url..."
curl.exe -f -L -o $tmp $url
if ($LASTEXITCODE -eq 0 -and (Test-Path $tmp) -and ((Get-Item $tmp).Length -gt 1048576)) {
    Move-Item $tmp $target -Force
    Write-Host "Modelo $fileName salvo com sucesso."
    exit 0
} else {
    if (Test-Path $tmp) {
        try { Remove-Item $tmp -Force } catch {}
    }
    throw "Falha ao baixar modelo $Model de $url"
}
