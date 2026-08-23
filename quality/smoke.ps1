# Sobe o app EMPACOTADO e exige prova de boot. Nenhum teste unitario pega o que este pega:
# a 1.7.0 saiu com 220 testes verdes e morria em 0xC0000005 antes da primeira linha de log.
# Portado de dito-app/tool/smoke.ps1, generalizado para o binario Electron.
param(
    [string]$Exe = "$PSScriptRoot\..\dist\win-unpacked\Dito.exe",
    [string]$Log = "$env:APPDATA\dito\logs\app.log",
    [string]$Marca = 'boot completo',
    [int]$TimeoutSegundos = 40,
    [int]$TetoPretoPorcento = 3
)
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Exe)) {
    Write-Host "FUMACA: PENDENTE - nao existe binario em $Exe (o app ainda nao foi empacotado)" -ForegroundColor Yellow
    exit 2
}

Add-Type -AssemblyName System.Drawing

# MEDIDO nesta maquina: PrintWindow(PW_RENDERFULLCONTENT) devolve a janela VAZIA no Electron -- a
# superficie e composta na GPU e nao entra no DC, e CopyFromScreen mede janela alheia por cima.
# O quadro do proprio Chromium (capturePage, ligado por --capture) e a unica medida honesta.
# Duas reprovacoes:
#   preto puro > teto  = area que o compositor nao apresentou (armadilha 4.13)
#   uma cor so > 97%   = pagina em branco ou erro de JS: nao desenhou nada
function AnalisarQuadro($arquivo) {
    if (-not (Test-Path $arquivo)) { return @{ erro = "o app nao salvou o quadro em $arquivo" } }
    $bmp = New-Object System.Drawing.Bitmap $arquivo
    $pretos = 0
    $total = 0
    $cores = @{}
    for ($y = 0; $y -lt $bmp.Height; $y += 4) {
        for ($x = 0; $x -lt $bmp.Width; $x += 4) {
            $c = $bmp.GetPixel($x, $y)
            if ($c.R -eq 0 -and $c.G -eq 0 -and $c.B -eq 0) { $pretos++ }
            $k = "$($c.R),$($c.G),$($c.B)"
            $cores[$k] = 1 + $cores[$k]
            $total++
        }
    }
    $tam = "$($bmp.Width)x$($bmp.Height)"
    $bmp.Dispose()
    if ($total -eq 0) { return @{ erro = 'quadro vazio' } }
    $dominante = ($cores.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1)
    return @{
        preto     = [math]::Round(100.0 * $pretos / $total, 1)
        dominante = [math]::Round(100.0 * $dominante.Value / $total, 1)
        cor       = $dominante.Key
        tamanho   = $tam
    }
}

function Falhar($motivo, $pid_) {
    if ($pid_) { Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue }
    Write-Host "FUMACA: FALHA - $motivo" -ForegroundColor Red
    $evt = Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'; StartTime=(Get-Date).AddMinutes(-2)} -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($evt) { Write-Host "  modulo com falha: $((($evt.Message -split "`n") | Where-Object { $_ -match 'modulo com falha|faulting module' }) -join ' ')" -ForegroundColor Red }
    exit 1
}

# Uma instancia velha segura o lock e o app novo sai sem abrir nada. Esperar um tempo fixo e
# corrida: espera ate a ultima morrer de verdade, ou reprova dizendo por que.
function MatarTodas() {
    Get-Process Dito, dito, dito_app, electron -ErrorAction SilentlyContinue | Stop-Process -Force
    $fim = [Environment]::TickCount + 10000
    while ([Environment]::TickCount -lt $fim) {
        $vivos = @(Get-Process Dito, dito, dito_app, electron -ErrorAction SilentlyContinue)
        if ($vivos.Count -eq 0) { return $true }
        Start-Sleep -Milliseconds 200
    }
    return $false
}
if (-not (MatarTodas)) {
    Write-Host "FUMACA: FALHA - sobrou instancia viva; a medida seria de outro processo" -ForegroundColor Red
    exit 1
}

$quadro = "$env:TEMP\dito_page.png"

foreach ($modo in @(@{ nome = 'bandeja'; args = @('--startup') }, @{ nome = 'janela'; args = @('--capture') })) {
    Write-Host "== fumaca: modo $($modo.nome)"
    Remove-Item $quadro -ErrorAction SilentlyContinue
    $p = Start-Process $Exe -ArgumentList $modo.args -PassThru

    # Contagem de linhas casa com marca de rodada VELHA e o portao segue cedo demais. A prova e
    # o segmento do log que comeca no 'starting' DESTE pid.
    $bootou = $false
    for ($i = 0; $i -lt $TimeoutSegundos; $i++) {
        Start-Sleep -Seconds 1
        if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { Falhar "o app morreu no modo $($modo.nome)" $null }
        $linhas = if (Test-Path $Log) { @(Get-Content $Log -ErrorAction SilentlyContinue) } else { @() }
        $inicio = -1
        for ($j = $linhas.Count - 1; $j -ge 0; $j--) {
            if ($linhas[$j] -match "starting . pid $($p.Id) ") { $inicio = $j; break }
        }
        if ($inicio -ge 0 -and ($linhas[$inicio..($linhas.Count - 1)] -match $Marca)) { $bootou = $true; break }
    }
    if (-not $bootou) { Falhar "sem '$Marca' no log em ${TimeoutSegundos}s (modo $($modo.nome))" $p.Id }

    if ($modo.nome -eq 'bandeja') {
        # Modo bandeja NAO pode abrir janela: e a armadilha 4.15.
        Start-Sleep -Seconds 2
        if ((Get-Process -Id $p.Id).MainWindowHandle -ne 0) { Falhar "modo bandeja abriu janela" $p.Id }
        Write-Host "   sem janela no modo bandeja: OK"
    }

    if ($modo.nome -eq 'janela') {
        $fim = [Environment]::TickCount + 15000
        while ([Environment]::TickCount -lt $fim -and -not (Test-Path $quadro)) { Start-Sleep -Milliseconds 300 }
        $r = AnalisarQuadro $quadro
        if ($r.erro) { Falhar $r.erro $p.Id }
        Write-Host ("   quadro {0} · preto puro {1}% · cor dominante {2}% ({3})" -f $r.tamanho, $r.preto, $r.dominante, $r.cor)
        if ($r.preto -gt $TetoPretoPorcento) { Falhar "faixa preta: $($r.preto)% dos pixels sao preto puro" $p.Id }
        if ($r.dominante -gt 97) { Falhar "a janela nao desenhou nada: $($r.dominante)% dos pixels sao a mesma cor" $p.Id }

        # Erro de JS nao muda um pixel sequer: a tela desenha e as partes vivas ficam mortas.
        # O app registra o console do renderer no log; qualquer erro aqui reprova.
        $todas = @(Get-Content $Log)
        $inicioPid = -1
        for ($j = $todas.Count - 1; $j -ge 0; $j--) {
            if ($todas[$j] -match "starting . pid $($p.Id) ") { $inicioPid = $j; break }
        }
        $novas = if ($inicioPid -ge 0) { $todas[$inicioPid..($todas.Count - 1)] } else { @() }
        $erros = $novas | Where-Object { $_ -match '\[console\].*(Uncaught|Error|TypeError|ReferenceError)' }
        if ($erros) { Falhar "erro de JS no renderer: $($erros[0])" $p.Id }
        Write-Host "   sem erro de JS no renderer: OK"
    }

    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    [void](MatarTodas)
}

Write-Host "FUMACA: PASSA - o app sobe nos dois modos, registra boot e desenha a tela" -ForegroundColor Green
exit 0
