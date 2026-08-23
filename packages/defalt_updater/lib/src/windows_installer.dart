// Troca a instalacao do Windows por cima, sem clique nenhum alem do "Reiniciar e atualizar".
//
// Um processo nao consegue sobrescrever o proprio .exe enquanto roda, entao a troca e
// delegada a um script: o app lanca o updater DESTACADO, morre, e o script espera o PID
// sumir pra copiar. O zip da release tem os arquivos na RAIZ, entao extrair e copiar por
// cima e o suficiente. Detalhes e historico: doc/PLATAFORMAS.md.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'models.dart';

class WindowsInstaller {
  const WindowsInstaller(this.config);
  final UpdaterConfig config;

  /// Pasta onde o app esta instalado (ao lado do .exe em execucao).
  static Directory get installDir => File(Platform.resolvedExecutable).parent;

  File get logFile => File('${Directory.systemTemp.path}\\${config.appId}-updater.log');

  /// A pasta aceita escrita sem elevacao? (`C:\Program Files` nao aceita.)
  bool _canWrite(Directory dir) {
    try {
      final probe = File('${dir.path}\\.${config.appId}_update_probe');
      probe.writeAsStringSync('x');
      probe.deleteSync();
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Extrai o zip por cima da instalacao e relanca o app. NAO RETORNA em sucesso.
  ///
  /// So encerra o app depois que o updater PROVAR que subiu (ele grava a primeira linha
  /// do log antes de qualquer outra coisa). Sem essa prova, lanca [UpdateException] e o
  /// app CONTINUA ABERTO: fechar sozinho e nao atualizar nada e o pior resultado possivel.
  Future<Never> applyAndRestart(File zip) async {
    await launchUpdater(
      zip,
      dest: installDir,
      exePath: Platform.resolvedExecutable,
      appPid: pid,
    );
    exit(0);
  }

  /// Sobe o updater destacado e so volta depois que ele provar que arrancou.
  ///
  /// Separado de [applyAndRestart] porque o teste exercita esta parte de verdade — com
  /// `exit(0)` junto ele mataria o proprio processo de teste.
  @visibleForTesting
  Future<void> launchUpdater(
    File zip, {
    required Directory dest,
    required String exePath,
    required int appPid,
    Directory? scriptDir,
  }) async {
    final needsElevation = !_canWrite(dest);
    final script = await writeScript(into: scriptDir);
    if (logFile.existsSync()) await logFile.delete(); // zera pra detectar o arranque

    final psArgs = <String>[
      '-NoProfile',
      '-ExecutionPolicy',
      'Bypass',
      '-File',
      script.path,
      '-AppPid',
      '$appPid',
      '-Zip',
      zip.path,
      '-Dest',
      dest.path,
      '-Exe',
      exePath,
    ];

    if (needsElevation) {
      // instalado em pasta protegida: pede UAC uma vez (o proprio script faz a copia)
      final quoted = psArgs.map((a) => "'${a.replaceAll("'", "''")}'").join(',');
      await Process.start(
        'cmd',
        [
          '/c', 'start', '', '/min', 'powershell', '-NoProfile', '-Command',
          'Start-Process powershell -Verb RunAs -ArgumentList $quoted',
        ],
        mode: ProcessStartMode.detached,
      );
    } else {
      // Via `cmd /c start` de proposito: Process.start detached cria o processo SEM
      // console, e o powershell.exe morre na hora nesse estado. O `start` cria o console.
      await Process.start(
        'cmd',
        ['/c', 'start', '', '/min', 'powershell', ...psArgs],
        mode: ProcessStartMode.detached,
      );
    }

    if (!await _waitForUpdaterStart()) {
      throw const UpdateException(
        'o atualizador nao iniciou — nada foi alterado, o app segue na versao atual',
      );
    }
  }

  /// Espera o updater escrever a primeira linha do log. Ele so espera o app morrer
  /// DEPOIS disso, entao nao ha impasse entre os dois.
  Future<bool> _waitForUpdaterStart() async {
    for (var i = 0; i < 60; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 250));
      if (logFile.existsSync() && logFile.lengthSync() > 0) return true;
    }
    return false;
  }

  /// Grava o .ps1 e devolve o arquivo. Publico porque o teste roda o script de verdade.
  Future<File> writeScript({Directory? into}) async {
    final dir = into ?? await getTemporaryDirectory();
    final f = File('${dir.path}\\${config.appId}-updater.ps1');
    await f.writeAsString(script, encoding: utf8, flush: true);
    return f;
  }

  String get script => _template
      .replaceAll('@@LOG@@', '${config.appId}-updater.log')
      .replaceAll('@@NAME@@', config.name.replaceAll("'", "''"));

  // Mostra uma janelinha de progresso enquanto troca os arquivos (o app esta fechado
  // nessa hora, entao sem ela a pessoa fica olhando pra nada e acha que quebrou).
  // Falha em qualquer etapa => relanca a versao ANTIGA: ficar sem app aberto seria pior
  // do que ficar sem a atualizacao.
  static const _template = r'''
param(
  [int]$AppPid,
  [string]$Zip,
  [string]$Dest,
  [string]$Exe
)
$ErrorActionPreference = 'Stop'
$log = Join-Path $env:TEMP '@@LOG@@'
function Log($m) { "$(Get-Date -Format s) $m" | Out-File -FilePath $log -Append -Encoding utf8 }
Log 'updater iniciado'

# O console existe so porque o powershell precisa de um pra subir (ver applyAndRestart);
# esconde ele, quem a pessoa ve e a janela de progresso abaixo.
try {
  Add-Type -Name Win -Namespace DefaltUpd -MemberDefinition '
    [DllImport("kernel32.dll")] public static extern System.IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int c);'
  [DefaltUpd.Win]::ShowWindow([DefaltUpd.Win]::GetConsoleWindow(), 0) | Out-Null
} catch { Log "nao consegui esconder o console: $_" }

$form = $null
$status = $null
try {
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing
  $form = New-Object Windows.Forms.Form
  $form.Text = '@@NAME@@'
  $form.Size = New-Object Drawing.Size(420, 150)
  $form.StartPosition = 'CenterScreen'
  $form.FormBorderStyle = 'FixedDialog'
  $form.MaximizeBox = $false
  $form.MinimizeBox = $false
  $form.ControlBox = $false
  $form.TopMost = $true
  $form.BackColor = [Drawing.Color]::FromArgb(20, 22, 27)

  $title = New-Object Windows.Forms.Label
  $title.Text = 'Atualizando o @@NAME@@'
  $title.ForeColor = [Drawing.Color]::FromArgb(243, 245, 248)
  $title.Font = New-Object Drawing.Font('Segoe UI', 12, [Drawing.FontStyle]::Bold)
  $title.SetBounds(24, 22, 360, 26)
  $form.Controls.Add($title)

  $status = New-Object Windows.Forms.Label
  $status.Text = 'Preparando...'
  $status.ForeColor = [Drawing.Color]::FromArgb(151, 160, 174)
  $status.Font = New-Object Drawing.Font('Segoe UI', 9)
  $status.SetBounds(24, 52, 360, 20)
  $form.Controls.Add($status)

  $bar = New-Object Windows.Forms.ProgressBar
  $bar.Style = 'Marquee'
  $bar.MarqueeAnimationSpeed = 30
  $bar.SetBounds(24, 80, 360, 12)
  $form.Controls.Add($bar)

  $form.Show()
  [Windows.Forms.Application]::DoEvents()
} catch { Log "sem janela de progresso: $_" }

function Say($t) {
  Log $t
  if ($status) { $status.Text = $t; [Windows.Forms.Application]::DoEvents() }
}

try {
  Say 'Fechando o aplicativo...'
  try { Wait-Process -Id $AppPid -Timeout 30 -ErrorAction Stop } catch { Log "pid ja encerrado ou timeout: $_" }
  Start-Sleep -Milliseconds 500

  if ($Zip -like '*.exe') {
    Say 'Instalando a nova versao...'
    $proc = Start-Process -FilePath $Zip -ArgumentList '/SILENT' -PassThru -Wait
    if ($proc.ExitCode -ne 0) { throw "instalador falhou com codigo $($proc.ExitCode)" }
  } else {
    $tmp = Join-Path $env:TEMP ('defalt-update-' + [guid]::NewGuid().ToString('N'))
    Say 'Extraindo a nova versao...'
    Expand-Archive -LiteralPath $Zip -DestinationPath $tmp -Force

    Say 'Instalando...'
    # /E copia subpastas; SEM /MIR pra nao apagar nada que o usuario tenha na pasta.
    # Codigos < 8 sao sucesso no robocopy.
    robocopy $tmp $Dest /E /R:3 /W:1 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy falhou com codigo $LASTEXITCODE" }

    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  }
  Remove-Item $Zip -Force -ErrorAction SilentlyContinue
  Say 'Pronto! Reabrindo...'
  Start-Sleep -Milliseconds 900
} catch {
  Log "ERRO: $_"
  Say 'Nao deu pra atualizar. Reabrindo a versao atual...'
  Start-Sleep -Seconds 4
}

if ($form) { $form.Close() }
Log "relancando $Exe"
Start-Process -FilePath $Exe -WorkingDirectory $Dest
''';
}
