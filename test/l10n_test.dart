import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The catalogue is the single source of wording; these keep it honest.
void main() {
  Map<String, dynamic> ler(String nome) =>
      jsonDecode(File('lib/l10n/$nome').readAsStringSync()) as Map<String, dynamic>;

  final en = ler('app_en.arb');
  final pt = ler('app_pt.arb');
  Set<String> chaves(Map<String, dynamic> arb) =>
      arb.keys.where((k) => !k.startsWith('@')).toSet();

  test('both languages carry exactly the same keys', () {
    expect(chaves(pt).difference(chaves(en)), isEmpty, reason: 'sobrando em pt');
    expect(chaves(en).difference(chaves(pt)), isEmpty, reason: 'faltando em pt');
  });

  test('no entry is empty or left untranslated', () {
    for (final chave in chaves(en)) {
      expect((en[chave] as String).trim(), isNotEmpty, reason: '$chave vazio em en');
      expect((pt[chave] as String).trim(), isNotEmpty, reason: '$chave vazio em pt');
    }
  });

  test('placeholders match between the two languages', () {
    final marca = RegExp(r'\{(\w+)\}');
    for (final chave in chaves(en)) {
      final naEn = marca.allMatches(en[chave] as String).map((m) => m.group(1)!).toSet();
      final naPt = marca.allMatches(pt[chave] as String).map((m) => m.group(1)!).toSet();
      // A placeholder dropped in translation is a message that renders half-built.
      expect(naPt, naEn, reason: '$chave usa marcadores diferentes');
    }
  });

  test('the screens hold no visible literal string', () {
    // Text('...') and Text("...") with letters in it: the wording belongs in the ARB.
    final literal = RegExp('''Text\\(\\s*['"]([^'"\$]{3,})['"]''');
    final letra = RegExp('[A-Za-zÀ-ÿ]{3}');
    final ofensas = <String>[];

    for (final entidade in Directory('lib/ui').listSync(recursive: true)) {
      if (entidade is! File || !entidade.path.endsWith('.dart')) continue;
      final linhas = entidade.readAsLinesSync();
      for (var i = 0; i < linhas.length; i++) {
        for (final achado in literal.allMatches(linhas[i])) {
          final texto = achado.group(1)!;
          if (letra.hasMatch(texto)) {
            ofensas.add('${entidade.path}:${i + 1} "$texto"');
          }
        }
      }
    }

    expect(ofensas, isEmpty, reason: ofensas.join(' | '));
  });
}
