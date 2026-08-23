import 'dart:io';

import 'package:dito_app/config/config_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory tempDir;

  setUp(() {
    tempDir = Directory.systemTemp.createTempSync('dito_migration_test_');
  });

  tearDown(() {
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  String configPath() => '${tempDir.path}${Platform.pathSeparator}config.toml';

  void writeConfig(String folder) {
    // TOML literal string (single quotes) so a Windows backslash path is not treated as an escape.
    File(configPath()).writeAsStringSync("[library]\nfolder = '$folder'\n");
  }

  test('(a) migra quando o folder aponta pro default antigo e o novo nao existe', () async {
    final oldDefault = '${tempDir.path}${Platform.pathSeparator}old_docs${Platform.pathSeparator}Dito';
    final newDefault = '${tempDir.path}${Platform.pathSeparator}profile${Platform.pathSeparator}Dito';
    Directory(oldDefault).createSync(recursive: true);
    File('$oldDefault${Platform.pathSeparator}sample.json').writeAsStringSync('{}');
    // The profile root always exists on a real machine; rename() needs the parent to pre-exist.
    Directory('${tempDir.path}${Platform.pathSeparator}profile').createSync(recursive: true);
    writeConfig(oldDefault);

    final service = ConfigService(
      path: configPath(),
      oldDefaultLibrary: oldDefault,
      newDefaultLibrary: newDefault,
    );
    await service.load();

    expect(service.config.library.folder, isEmpty);
    expect(Directory(newDefault).existsSync(), isTrue);
    expect(File('$newDefault${Platform.pathSeparator}sample.json').existsSync(), isTrue);
    expect(Directory(oldDefault).existsSync(), isFalse);
  });

  test('(e) migra tambem quem estava no default implicito (folder vazio)', () async {
    final sep = Platform.pathSeparator;
    final oldDefault = '${tempDir.path}${sep}old_docs${sep}Dito';
    final newDefault = '${tempDir.path}${sep}profile${sep}Dito';
    Directory(oldDefault).createSync(recursive: true);
    File('$oldDefault${sep}sample.json').writeAsStringSync('{}');
    Directory('${tempDir.path}${sep}profile').createSync(recursive: true);
    writeConfig('');

    final service = ConfigService(
      path: configPath(),
      oldDefaultLibrary: oldDefault,
      newDefaultLibrary: newDefault,
    );
    await service.load();

    expect(File('$newDefault${sep}sample.json').existsSync(), isTrue,
        reason: 'quem nunca escolheu pasta seguia o default antigo; sem mover, o historico some');
    expect(Directory(oldDefault).existsSync(), isFalse);
    expect(service.config.library.folder, isEmpty);
  });

  test('(f) nao cria nada quando a pasta antiga nunca existiu', () async {
    final sep = Platform.pathSeparator;
    final oldDefault = '${tempDir.path}${sep}old_docs${sep}Dito';
    final newDefault = '${tempDir.path}${sep}profile${sep}Dito';
    writeConfig('');

    final service = ConfigService(
      path: configPath(),
      oldDefaultLibrary: oldDefault,
      newDefaultLibrary: newDefault,
    );
    await service.load();

    expect(Directory(newDefault).existsSync(), isFalse);
  });

  test('(b) nao migra quando o destino ja existe', () async {
    final oldDefault = '${tempDir.path}${Platform.pathSeparator}old_docs${Platform.pathSeparator}Dito';
    final newDefault = '${tempDir.path}${Platform.pathSeparator}profile${Platform.pathSeparator}Dito';
    Directory(oldDefault).createSync(recursive: true);
    Directory(newDefault).createSync(recursive: true);
    writeConfig(oldDefault);

    final service = ConfigService(
      path: configPath(),
      oldDefaultLibrary: oldDefault,
      newDefaultLibrary: newDefault,
    );
    await service.load();

    expect(service.config.library.folder, oldDefault);
    expect(Directory(oldDefault).existsSync(), isTrue);
  });

  test('(c) nao migra quando o folder e uma pasta escolhida pelo dono', () async {
    final oldDefault = '${tempDir.path}${Platform.pathSeparator}old_docs${Platform.pathSeparator}Dito';
    final newDefault = '${tempDir.path}${Platform.pathSeparator}profile${Platform.pathSeparator}Dito';
    final chosen = '${tempDir.path}${Platform.pathSeparator}minha_pasta';
    Directory(chosen).createSync(recursive: true);
    writeConfig(chosen);

    final service = ConfigService(
      path: configPath(),
      oldDefaultLibrary: oldDefault,
      newDefaultLibrary: newDefault,
    );
    await service.load();

    expect(service.config.library.folder, chosen);
    expect(Directory(chosen).existsSync(), isTrue);
  });

  test('(d) falha no move nao derruba o load()', () async {
    final oldDefault = '${tempDir.path}${Platform.pathSeparator}old_docs${Platform.pathSeparator}Dito';
    final newDefault = '${tempDir.path}${Platform.pathSeparator}profile${Platform.pathSeparator}Dito';
    Directory(oldDefault).createSync(recursive: true);
    // A file (not a directory) already sitting at newDefault makes the rename fail.
    Directory('${tempDir.path}${Platform.pathSeparator}profile').createSync(recursive: true);
    File(newDefault).writeAsStringSync('nao sou uma pasta');
    writeConfig(oldDefault);

    final service = ConfigService(
      path: configPath(),
      oldDefaultLibrary: oldDefault,
      newDefaultLibrary: newDefault,
    );
    await service.load();

    expect(service.config.library.folder, oldDefault);
    expect(Directory(oldDefault).existsSync(), isTrue);
  });
}
