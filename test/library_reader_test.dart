import 'dart:convert';
import 'dart:io';

import 'package:dito_app/library/library_reader.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory root;
  late LibraryReader reader;

  setUp(() {
    root = Directory.systemTemp.createTempSync('dito_lib');
    reader = LibraryReader();
  });

  tearDown(() {
    if (root.existsSync()) root.deleteSync(recursive: true);
  });

  /// Writes a session the way the engine does: YYYY/MM/DD/<HH-MM-SS>.json
  void writeSession(
    String y,
    String m,
    String d,
    String time, {
    String text = 'ola',
    String state = 'done',
    String mode = 'dictation',
    bool audio = false,
    bool brokenJson = false,
  }) {
    final dir = Directory('${root.path}/$y/$m/$d')..createSync(recursive: true);
    final json = File('${dir.path}/$time.json');
    if (brokenJson) {
      json.writeAsStringSync('{ isso nao e json');
    } else {
      json.writeAsStringSync(jsonEncode(<String, Object?>{
        'id': '$y-$m-${d}_$time',
        'mode': mode,
        'state': state,
        'seconds': 12.5,
        'text': text,
      }));
    }
    if (audio) {
      File('${dir.path}/$time.wav').writeAsBytesSync(List<int>.filled(44 + 32000, 0));
    }
  }

  group('layout', () {
    test('reads <HH-MM-SS>.json, which session.json never matched', () async {
      writeSession('2026', '08', '16', '07-42-13');
      await reader.load(root.path);

      expect(reader.sessions, hasLength(1));
      expect(reader.sessions.single.preview, 'ola');
    });

    test('the date comes from the path, not from the file', () async {
      writeSession('2025', '01', '02', '03-04-05');
      await reader.load(root.path);

      final started = reader.sessions.single.started;
      expect(started.year, 2025);
      expect(started.month, 1);
      expect(started.day, 2);
      expect(started.hour, 3);
      expect(started.minute, 4);
    });

    test('unreadable metadata still lists, marked unknown', () async {
      writeSession('2026', '08', '16', '07-42-13', brokenJson: true);
      await reader.load(root.path);

      expect(reader.sessions, hasLength(1));
      expect(reader.sessions.single.state, 'unknown');
      expect(reader.sessions.single.isDone, isFalse);
    });

    test('two sessions in the same folder both show', () async {
      writeSession('2026', '08', '16', '07-42-13');
      writeSession('2026', '08', '16', '09-10-11');
      await reader.load(root.path);

      expect(reader.sessions, hasLength(2));
      expect(reader.sessions.first.started.hour, 9, reason: 'mais recente primeiro');
    });

    test('a stray file is not a session', () async {
      Directory('${root.path}/2026/08/16').createSync(recursive: true);
      File('${root.path}/2026/08/16/anotacoes.md').writeAsStringSync('minhas notas');
      await reader.load(root.path);

      expect(reader.sessions, isEmpty);
    });

    test('an empty library is not an error', () async {
      await reader.load('${root.path}/nao-existe');
      expect(reader.sessions, isEmpty);
    });
  });

  group('sweep', () {
    test('keepDays 0 keeps everything', () async {
      writeSession('2020', '01', '01', '01-01-01', audio: true);
      final result = await reader.sweep(root.path, 0);

      expect(result.sessions, 0);
      await reader.load(root.path);
      expect(reader.sessions, hasLength(1));
    });

    test('old days go, recent days stay', () async {
      final old = DateTime.now().subtract(const Duration(days: 400));
      final recent = DateTime.now().subtract(const Duration(days: 1));
      String two(int v) => v.toString().padLeft(2, '0');

      writeSession('${old.year}', two(old.month), two(old.day), '01-01-01', audio: true);
      writeSession('${recent.year}', two(recent.month), two(recent.day), '02-02-02');

      final result = await reader.sweep(root.path, 30);

      expect(result.sessions, 1);
      expect(result.bytes, greaterThan(0));
      await reader.load(root.path);
      expect(reader.sessions, hasLength(1));
    });

    test('a note left beside a recording survives the sweep', () async {
      final old = DateTime.now().subtract(const Duration(days: 400));
      String two(int v) => v.toString().padLeft(2, '0');
      final y = '${old.year}';
      final m = two(old.month);
      final d = two(old.day);

      writeSession(y, m, d, '01-01-01');
      final note = File('${root.path}/$y/$m/$d/resumo.md')
        ..writeAsStringSync('escrito pelo dono');

      await reader.sweep(root.path, 30);

      expect(note.existsSync(), isTrue, reason: 'so apagamos o que o app escreve');
    });

    test('a folder that is not a date is never swept', () async {
      final dir = Directory('${root.path}/projeto-importante')..createSync();
      final file = File('${dir.path}/coisa.json')..writeAsStringSync('{}');

      await reader.sweep(root.path, 1);

      expect(file.existsSync(), isTrue);
    });
  });
}
