// Prova de ponta a ponta do caminho do Windows: monta uma instalacao "velha", publica
// um zip "novo" e roda o updater DE VERDADE (o mesmo .ps1 que o app dispara), com um
// processo cobaia no lugar do app. Assere o que importa: os arquivos foram trocados, o
// que era do usuario sobreviveu, o zip foi limpo e o executavel foi relancado.
//
// So roda no Windows — nas outras plataformas o teste e pulado, nao mascarado.
import 'dart:io';

import 'package:defalt_updater/defalt_updater.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory tmp;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('defalt_win_apply');
  });

  tearDown(() {
    if (tmp.existsSync()) {
      try {
        tmp.deleteSync(recursive: true);
      } on FileSystemException {
        // o updater ainda pode ter handle aberto no diretorio; nao e falha do teste
      }
    }
  });

  test('o updater troca a instalacao por cima e relanca o app', () async {
    const config = UpdaterConfig(
      appId: 'defalt-test-app',
      manifestUrl: 'http://localhost/latest',
      downloadUrl: 'http://localhost/download',
      displayName: 'Defalt Test App',
    );
    const installer = WindowsInstaller(config);

    final install = Directory('${tmp.path}\\install')..createSync();
    final staged = Directory('${tmp.path}\\staged')..createSync();
    final marker = File('${tmp.path}\\relaunched.txt');

    // o "app": um .bat que so registra que foi aberto — o relance fica provado por ele
    String appBat(String versao) =>
        '@echo off\r\necho $versao>>"${marker.path}"\r\n';

    File('${install.path}\\app.bat').writeAsStringSync(appBat('v1'));
    File('${install.path}\\core.txt').writeAsStringSync('velho');
    File('${install.path}\\meus-dados.txt').writeAsStringSync('nao pode sumir');

    File('${staged.path}\\app.bat').writeAsStringSync(appBat('v2'));
    File('${staged.path}\\core.txt').writeAsStringSync('novo');
    File('${staged.path}\\extra.txt').writeAsStringSync('arquivo que so existe na v2');

    final zip = File('${tmp.path}\\update.zip');
    final compress = await Process.run('powershell', [
      '-NoProfile',
      '-Command',
      "Compress-Archive -Path '${staged.path}\\*' -DestinationPath '${zip.path}' -Force",
    ]);
    expect(compress.exitCode, 0, reason: 'nao consegui montar o zip: ${compress.stderr}');
    expect(zip.existsSync(), isTrue);

    // cobaia no lugar do app: o updater espera ESTE pid morrer antes de copiar
    final cobaia = await Process.start('powershell', ['-NoProfile', '-Command', 'Start-Sleep -Seconds 120']);

    await installer.launchUpdater(
      zip,
      dest: install,
      exePath: '${install.path}\\app.bat',
      appPid: cobaia.pid,
      scriptDir: tmp,
    );

    // launchUpdater so retorna depois que o updater provou que subiu
    expect(installer.logFile.existsSync(), isTrue);

    cobaia.kill(); // e o app fechando
    await cobaia.exitCode;

    final trocou = await _waitUntil(() =>
        marker.existsSync() && File('${install.path}\\extra.txt').existsSync());
    expect(trocou, isTrue,
        reason: 'updater nao concluiu. log:\n${installer.logFile.readAsStringSync()}');

    expect(File('${install.path}\\core.txt').readAsStringSync().trim(), 'novo',
        reason: 'arquivo existente tem que ser sobrescrito');
    expect(File('${install.path}\\extra.txt').existsSync(), isTrue,
        reason: 'arquivo novo tem que aparecer');
    expect(File('${install.path}\\meus-dados.txt').existsSync(), isTrue,
        reason: 'robocopy sem /MIR: nada do usuario pode ser apagado');
    expect(marker.readAsStringSync(), contains('v2'),
        reason: 'quem foi relancado tem que ser a versao NOVA');
    expect(zip.existsSync(), isFalse, reason: 'o zip baixado tem que ser limpo');
  }, timeout: const Timeout(Duration(minutes: 2)), skip: _skipUnlessWindows);
}

final String? _skipUnlessWindows =
    Platform.isWindows ? null : 'o updater por .ps1 so existe no Windows';

Future<bool> _waitUntil(bool Function() ok, {int tries = 120}) async {
  for (var i = 0; i < tries; i++) {
    if (ok()) return true;
    await Future<void>.delayed(const Duration(milliseconds: 500));
  }
  return ok();
}
