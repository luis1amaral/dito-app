import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Guards against the glyph boxes the owner kept seeing on screen.
///
/// Accented letters are fine - a system font has them. What drew as a square was the
/// typographic set: em dash, ellipsis, return arrow, middle dot, box drawing.
void main() {
  test('no source string uses a glyph a system font may lack', () {
    final offenses = <String>[];

    for (final entity in Directory('lib').listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      // Generated code carries Flutter's own boilerplate comments; its wording is the ARB.
      if (entity.path.endsWith('.g.dart')) continue;
      final lines = entity.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        for (final rune in lines[i].runes) {
          if (rune >= 0x2000) {
            final hex = rune.toRadixString(16).toUpperCase();
            offenses.add('${entity.path}:${i + 1} U+$hex em "${lines[i].trim()}"');
          }
        }
      }
    }

    for (final name in <String>['app_en.arb', 'app_pt.arb']) {
      final arb = jsonDecode(File('lib/l10n/$name').readAsStringSync()) as Map<String, dynamic>;
      for (final entry in arb.entries) {
        if (entry.key.startsWith('@') || entry.value is! String) continue;
        for (final rune in (entry.value as String).runes) {
          if (rune >= 0x2000) {
            offenses.add('$name/${entry.key} U+${rune.toRadixString(16).toUpperCase()}');
          }
        }
      }
    }

    expect(offenses, isEmpty, reason: 'use ASCII: ${offenses.take(5).join(" | ")}');
  });

  test('the installer script keeps its BOM', () {
    final iss = File('packaging/windows/dito.iss');
    final bytes = iss.readAsBytesSync();
    // Inno reads plain UTF-8 as ANSI and mangles every accent in the wizard.
    expect(bytes.take(3), <int>[0xEF, 0xBB, 0xBF]);
  });
}
