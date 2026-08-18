import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Guards against the glyph boxes the owner kept seeing on screen.
///
/// Accented letters are fine - a system font has them. What drew as a square was the
/// typographic set: em dash, ellipsis, return arrow, middle dot, box drawing.
void main() {
  test('no source string uses a glyph a system font may lack', () {
    final ofensas = <String>[];

    for (final entidade in Directory('lib').listSync(recursive: true)) {
      if (entidade is! File || !entidade.path.endsWith('.dart')) continue;
      // Generated code carries Flutter's own boilerplate comments; its wording is the ARB.
      if (entidade.path.endsWith('.g.dart')) continue;
      final linhas = entidade.readAsLinesSync();
      for (var i = 0; i < linhas.length; i++) {
        for (final rune in linhas[i].runes) {
          if (rune >= 0x2000) {
            final hex = rune.toRadixString(16).toUpperCase();
            ofensas.add('${entidade.path}:${i + 1} U+$hex em "${linhas[i].trim()}"');
          }
        }
      }
    }

    for (final nome in <String>['app_en.arb', 'app_pt.arb']) {
      final arb = jsonDecode(File('lib/l10n/$nome').readAsStringSync()) as Map<String, dynamic>;
      for (final entrada in arb.entries) {
        if (entrada.key.startsWith('@') || entrada.value is! String) continue;
        for (final rune in (entrada.value as String).runes) {
          if (rune >= 0x2000) {
            ofensas.add('$nome/${entrada.key} U+${rune.toRadixString(16).toUpperCase()}');
          }
        }
      }
    }

    expect(ofensas, isEmpty, reason: 'use ASCII: ${ofensas.take(5).join(" | ")}');
  });

  test('the installer script keeps its BOM', () {
    final iss = File('packaging/windows/dito.iss');
    final bytes = iss.readAsBytesSync();
    // Inno reads plain UTF-8 as ANSI and mangles every accent in the wizard.
    expect(bytes.take(3), <int>[0xEF, 0xBB, 0xBF]);
  });
}
