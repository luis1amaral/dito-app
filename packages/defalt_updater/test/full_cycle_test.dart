// O ciclo inteiro, sem mock em lugar nenhum: um app na 1.12.0 pergunta a um servidor de
// verdade, descobre a 1.13.0, baixa o zip por streaming, confere o sha256 e roda o updater
// real, que troca os arquivos da instalacao e relanca a versao nova.
//
// Os outros testes provam as metades separadas. Este prova que elas se encaixam — e e o
// unico que responderia "sim" a pergunta "o update funciona de ponta a ponta?".
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:defalt_updater/defalt_updater.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('1.12.0 encontra a 1.13.0, baixa, confere e fica instalada', () async {
    final tmp = await Directory.systemTemp.createTemp('defalt_cycle');
    addTearDown(() {
      try {
        tmp.deleteSync(recursive: true);
      } on FileSystemException {
        // o updater pode ainda ter handle aberto; nao e falha do teste
      }
    });

    final install = Directory('${tmp.path}\\install')..createSync();
    final staged = Directory('${tmp.path}\\staged')..createSync();
    final work = Directory('${tmp.path}\\work')..createSync();
    final marker = File('${tmp.path}\\rodou.txt');

    String appBat(String v) => '@echo off\r\necho $v>>"${marker.path}"\r\n';

    // a instalacao "velha" que esta rodando hoje
    File('${install.path}\\app.bat').writeAsStringSync(appBat('1.12.0'));
    File('${install.path}\\core.txt').writeAsStringSync('1.12.0');
    File('${install.path}\\meus-dados.txt').writeAsStringSync('do usuario');

    // a release 1.13.0, empacotada como o script de release empacota (arquivos na RAIZ)
    File('${staged.path}\\app.bat').writeAsStringSync(appBat('1.13.0'));
    File('${staged.path}\\core.txt').writeAsStringSync('1.13.0');
    File('${staged.path}\\novidade.txt').writeAsStringSync('so existe na 1.13.0');

    final zip = File('${tmp.path}\\release.zip');
    final packed = await Process.run('powershell', [
      '-NoProfile',
      '-Command',
      "Compress-Archive -Path '${staged.path}\\*' -DestinationPath '${zip.path}' -Force",
    ]);
    expect(packed.exitCode, 0, reason: '${packed.stderr}');

    final bytes = zip.readAsBytesSync();
    final hash = sha256.convert(bytes).toString();

    // o worker: manifesto + binario
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    server.listen((req) async {
      if (req.uri.path.endsWith('/latest')) {
        req.response
          ..headers.contentType = ContentType.json
          ..write(jsonEncode({
            'version': '1.13.0',
            'notes': 'o que mudou',
            'windows': {'size': bytes.length, 'sha256': hash},
          }));
      } else {
        req.response.add(bytes);
      }
      await req.response.close();
    });

    final base = 'http://${server.address.host}:${server.port}';
    final updater = DefaltUpdater(
      config: UpdaterConfig(
        appId: 'ciclo',
        displayName: 'Ciclo',
        manifestUrl: '$base/api/app/latest',
        downloadUrl: '$base/api/app/download',
      ),
      currentVersionReader: () async => '1.12.0',
      workDir: () async => work,
    );

    // 1) descobre
    final info = await updater.check();
    expect(info, isNotNull, reason: 'a 1.13.0 tinha que ser encontrada');
    expect(info!.version, '1.13.0');
    expect(info.current, '1.12.0');
    expect(info.integrity, IntegrityCheck.sha256);
    expect(updater.delivery, UpdateDelivery.inAppDownload);

    // 2) baixa e confere
    final baixado = await updater.download(info);
    expect(baixado.existsSync(), isTrue);
    expect(await DefaltUpdater.sha256OfFile(baixado), hash);

    // 3) aplica — o updater de verdade, sobre a instalacao de verdade
    final appAntigo =
        await Process.start('powershell', ['-NoProfile', '-Command', 'Start-Sleep -Seconds 120']);
    await const WindowsInstaller(UpdaterConfig(
      appId: 'ciclo',
      displayName: 'Ciclo',
      manifestUrl: '',
      downloadUrl: '',
    )).launchUpdater(
      baixado,
      dest: install,
      exePath: '${install.path}\\app.bat',
      appPid: appAntigo.pid,
      scriptDir: tmp,
    );
    appAntigo.kill();
    await appAntigo.exitCode;

    final pronto = await _waitUntil(
      () => marker.existsSync() && File('${install.path}\\novidade.txt').existsSync(),
    );
    expect(pronto, isTrue, reason: 'o updater nao concluiu a troca');

    // 4) a instalacao agora E a 1.13.0
    expect(File('${install.path}\\core.txt').readAsStringSync().trim(), '1.13.0');
    expect(File('${install.path}\\novidade.txt').existsSync(), isTrue);
    expect(File('${install.path}\\meus-dados.txt').existsSync(), isTrue,
        reason: 'nada do usuario pode ser apagado na troca');
    expect(marker.readAsStringSync(), contains('1.13.0'),
        reason: 'quem reabriu tem que ser a versao nova');
  }, timeout: const Timeout(Duration(minutes: 2)), skip: _skipUnlessWindows);
}

final String? _skipUnlessWindows =
    Platform.isWindows ? null : 'o ciclo com troca de arquivos so existe no Windows';

Future<bool> _waitUntil(bool Function() ok, {int tries = 120}) async {
  for (var i = 0; i < tries; i++) {
    if (ok()) return true;
    await Future<void>.delayed(const Duration(milliseconds: 500));
  }
  return ok();
}
