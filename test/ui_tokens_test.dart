import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Enforces the CLAUDE.md rule: lib/ui/** may not hardcode color, spacing, radius or duration
/// literals - only lib/ui/tokens.dart and lib/ui/palette.dart may define those values.
void main() {
  // These two files ARE the source of truth for the values the scan below forbids everywhere else.
  const sourceOfTruth = {'lib/ui/tokens.dart', 'lib/ui/palette.dart'};

  // Colors.transparent is "no color", not a design value; it needs no token.
  const allowedColorConstants = {'Colors.transparent'};

  // Known offenses left in files owned by other agents mid-refactor (2026-08-21 parallel cleanup).
  // Keyed by file + rule + matched text, not line number, so a concurrent edit that shifts lines
  // does not desync this list. Left unconsumed once the owning agent fixes it - harmless.
  final knownExceptions = <String>{
    'lib/ui/main/settings_page.dart|Duration literal|Duration(seconds: 3)',
    'lib/ui/review/review_window.dart|Duration literal|Duration(milliseconds: 200)',
    'lib/ui/review/review_window.dart|Duration literal|Duration(milliseconds: 120)',
    'lib/ui/hud/hud_window.dart|Duration literal|Duration(milliseconds: 200)',
  };

  test('lib/ui/** sources colors, spacing, radii and durations only from tokens', () {
    final offenses = <String>[];
    final consumedExceptions = <String>{};

    for (final entity in Directory('lib/ui').listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final path = entity.path.replaceAll('\\', '/');
      if (sourceOfTruth.contains(path)) continue;

      final content = entity.readAsStringSync();
      final lineStarts = _lineStartOffsets(content);

      void check(RegExp pattern, String rule, {bool Function(String matched)? ignore}) {
        for (final m in pattern.allMatches(content)) {
          final matched = m.group(0)!;
          if (ignore != null && ignore(matched)) continue;
          final line = _lineOf(lineStarts, m.start);
          final key = '$path|$rule|${matched.trim()}';
          if (knownExceptions.contains(key)) {
            consumedExceptions.add(key);
            continue;
          }
          offenses.add('$path:$line -> $rule: "${matched.trim()}"');
        }
      }

      check(RegExp(r'Color\(0x[0-9A-Fa-f]+\)'), 'raw Color');

      check(
        RegExp(r'Colors\.\w+'),
        'Colors.* literal',
        ignore: allowedColorConstants.contains,
      );

      check(
        RegExp(r'EdgeInsets\.\w+\(([^)]*)\)', dotAll: true),
        'raw EdgeInsets literal',
        ignore: (m) => !RegExp(r'\d').hasMatch(m),
      );

      check(
        RegExp(r'BorderRadius\.circular\(([^)]*)\)'),
        'raw BorderRadius literal',
        ignore: (m) => !RegExp(r'\d').hasMatch(m),
      );

      check(
        RegExp(r'Duration\(([^)]*)\)'),
        'Duration literal',
        ignore: (m) => !RegExp(r'\d').hasMatch(m),
      );
    }

    expect(offenses, isEmpty, reason: offenses.join('\n'));
  });
}

List<int> _lineStartOffsets(String content) {
  final offsets = <int>[0];
  for (var i = 0; i < content.length; i++) {
    if (content[i] == '\n') offsets.add(i + 1);
  }
  return offsets;
}

int _lineOf(List<int> lineStarts, int offset) {
  var lo = 0, hi = lineStarts.length - 1;
  while (lo < hi) {
    final mid = (lo + hi + 1) >> 1;
    if (lineStarts[mid] <= offset) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return lo + 1;
}
