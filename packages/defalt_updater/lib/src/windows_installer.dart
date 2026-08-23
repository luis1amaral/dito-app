// Replaces the Windows install in place, no click beyond "Restart and update": a running process cannot overwrite its own .exe, so a detached script waits for our PID to die before copying (doc/PLATAFORMAS.md).
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'models.dart';

class WindowsInstaller {
  const WindowsInstaller(this.config);
  final UpdaterConfig config;

  /// Folder where the app is installed (next to the running .exe).
  static Directory get installDir => File(Platform.resolvedExecutable).parent;

  File get logFile => File('${Directory.systemTemp.path}\\${config.appId}-updater.log');

  /// Does the folder accept writes without elevation? (`C:\Program Files` does not.)
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

  /// Extracts the zip over the install and relaunches the app; NEVER RETURNS on success. Only closes once the updater PROVES it started (first log line), or throws [UpdateException] and stays OPEN — closing without updating is the worst outcome.
  Future<Never> applyAndRestart(File zip) async {
    await launchUpdater(
      zip,
      dest: installDir,
      exePath: Platform.resolvedExecutable,
      appPid: pid,
    );
    exit(0);
  }

  /// Launches the detached updater and only returns once it proves it started; split from [applyAndRestart] because the test exercises this part for real, and `exit(0)` there would kill the test process itself.
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
    if (logFile.existsSync()) await logFile.delete(); // cleared to detect the startup

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
      // Installed in a protected folder: ask for UAC once (the script itself does the copy).
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
      // Via `cmd /c start` on purpose: Process.start detached creates the process with NO console, and powershell.exe dies instantly like that; `start` gives it one.
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

  /// Waits for the updater to write the log's first line; it only waits for the app to die AFTER that, so the two never deadlock.
  Future<bool> _waitForUpdaterStart() async {
    for (var i = 0; i < 60; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 250));
      if (logFile.existsSync() && logFile.lengthSync() > 0) return true;
    }
    return false;
  }

  /// Writes the .ps1 and returns the file; public because the test runs the script for real.
  Future<File> writeScript({Directory? into}) async {
    final dir = into ?? await getTemporaryDirectory();
    final f = File('${dir.path}\\${config.appId}-updater.ps1');
    await f.writeAsString(script, encoding: utf8, flush: true);
    return f;
  }

  String get script => _template
      .replaceAll('@@LOG@@', '${config.appId}-updater.log')
      .replaceAll('@@NAME@@', config.name.replaceAll("'", "''"));

  // Shows a small progress window while swapping files (the app is closed then, so without it the person stares at nothing and assumes it broke); any step failing relaunches the OLD version instead.
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
