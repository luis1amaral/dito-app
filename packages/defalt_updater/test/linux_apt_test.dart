// O formato do arquivo Packages e fragil por natureza ("Chave: valor" com blocos
// separados por linha em branco), entao o parser merece teste com um Packages de verdade.
import 'package:defalt_updater/defalt_updater.dart';
import 'package:flutter_test/flutter_test.dart';

const _packagesReal = '''
Package: hidden
Version: 1.7.2
Architecture: amd64
Description: Chat privado estilo Discord (voz, video e tela)

Package: slime-animes
Version: 1.12.10
Architecture: amd64
Description: Assistir animes

Package: system-task
Version: 6.11.0
Architecture: amd64
Description: Gerenciador de tarefas
''';

void main() {
  group('LinuxApt.versionOf', () {
    test('acha a versao do pacote certo entre varios', () {
      expect(LinuxApt.versionOf(_packagesReal, 'slime-animes'), '1.12.10');
      expect(LinuxApt.versionOf(_packagesReal, 'hidden'), '1.7.2');
      expect(LinuxApt.versionOf(_packagesReal, 'system-task'), '6.11.0');
    });

    test('devolve null para pacote ausente, em vez de chutar o primeiro', () {
      expect(LinuxApt.versionOf(_packagesReal, 'nao-existe'), isNull);
    });

    test('nao confunde prefixo: "slime" nao casa com "slime-animes"', () {
      expect(LinuxApt.versionOf(_packagesReal, 'slime'), isNull);
    });

    test('aguenta CRLF e linha em branco com espacos', () {
      final sujo =
          _packagesReal.replaceAll('\n', '\r\n').replaceAll('\r\n\r\n', '\r\n  \r\n');
      expect(LinuxApt.versionOf(sujo, 'slime-animes'), '1.12.10');
    });
  });

  group('UpdaterConfig', () {
    test('debPackage cai no appId quando nao ha aptPackage', () {
      const c = UpdaterConfig(appId: 'hidden', manifestUrl: 'x', downloadUrl: 'y');
      expect(c.debPackage, 'hidden');
      expect(c.name, 'hidden');
    });

    test('aptPackage e displayName sobrescrevem o appId', () {
      const c = UpdaterConfig(
        appId: 'system-app',
        manifestUrl: 'x',
        downloadUrl: 'y',
        aptPackage: 'system-task',
        displayName: 'System Task',
      );
      expect(c.debPackage, 'system-task');
      expect(c.name, 'System Task');
    });

    test('Android fica de fora por padrao — app de loja nao pode se auto-instalar', () {
      const c = UpdaterConfig(appId: 'a', manifestUrl: 'x', downloadUrl: 'y');
      expect(c.platforms, isNot(contains('android')));
      expect(c.platforms, containsAll(['windows', 'linux']));
    });

    test('quem esta fora da loja opta por Android explicitamente', () {
      const c = UpdaterConfig(
        appId: 'slime-animes',
        manifestUrl: 'x',
        downloadUrl: 'y',
        platforms: {'windows', 'linux', 'android'},
      );
      expect(c.platforms, contains('android'));
    });

    test('downloadUri carimba a plataforma sem perder a query existente', () {
      const c = UpdaterConfig(
        appId: 'a',
        manifestUrl: 'https://e/api/app/latest',
        downloadUrl: 'https://e/api/app/download?flavor=stable',
      );
      expect(c.downloadUri.queryParameters['platform'], UpdaterConfig.platformKey);
      expect(c.downloadUri.queryParameters['flavor'], 'stable');
    });
  });
}
