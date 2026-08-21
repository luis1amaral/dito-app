import 'package:dito_app/ui/review/review_sizing.dart';
import 'package:dito_app/ui/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const sizing = ReviewSizing();
  const style = TextStyle(fontSize: AppType.body, height: 1.4);
  const screen = 1080.0;

  String words(int count) => List<String>.filled(count, 'palavra').join(' ');

  group('growth', () {
    test('a short text still gets the minimum height', () {
      final metrics =
          sizing.measure(text: 'ola', style: style, screenHeight: screen);
      expect(metrics.lines, 3);
      expect(metrics.atCeiling, isFalse);
    });

    test('the card grows with the text instead of scrolling', () {
      final small = sizing.measure(text: words(5), style: style, screenHeight: screen);
      final big = sizing.measure(text: words(60), style: style, screenHeight: screen);

      expect(big.lines, greaterThan(small.lines));
      expect(big.editorHeight, greaterThan(small.editorHeight));
      // The test font is a square monospace, so line counts here are pessimistic on purpose.
      expect(big.atCeiling, isFalse, reason: 'ainda cabe na tela, sem rolagem');
    });

    test('the only ceiling is the screen', () {
      final metrics =
          sizing.measure(text: words(5000), style: style, screenHeight: screen);

      expect(metrics.atCeiling, isTrue);
      final maxHeight = screen - 2 * AppSize.screenMargin;
      expect(metrics.editorHeight, lessThan(maxHeight));
    });

    test('a smaller screen means a smaller ceiling', () {
      final tall = sizing.measure(text: words(2000), style: style, screenHeight: 2160);
      final short = sizing.measure(text: words(2000), style: style, screenHeight: 768);
      expect(tall.lines, greaterThan(short.lines));
    });

    test('the minimum survives even on a tiny screen', () {
      final metrics = sizing.measure(text: 'ola', style: style, screenHeight: 200);
      expect(metrics.lines, greaterThanOrEqualTo(3));
    });
  });

  group('width', () {
    test('the card is a fixed 560 and the text width follows from it', () {
      expect(sizing.width, AppSize.reviewWidth);
      expect(sizing.textWidth, AppSize.reviewWidth - 2 * AppSpacing.xl - 2 * AppSpacing.md - 2);
    });

    test('a longer line wraps instead of widening the card', () {
      final short = sizing.measure(text: 'uma linha', style: style, screenHeight: screen);
      final long = sizing.measure(text: words(40), style: style, screenHeight: screen);
      expect(long.cardWidth, short.cardWidth);
      expect(long.lines, greaterThan(short.lines));
    });
  });

  group('height maths', () {
    test('half a line of slack keeps the last line from being clipped', () {
      final height = sizing.editorHeight(4, 20);
      expect(height, 4 * 20 + 10 + AppSpacing.xl);
    });

    test('text scaling is honoured', () {
      final normal = sizing.measure(text: words(60), style: style, screenHeight: screen);
      final scaled = sizing.measure(
          text: words(60), style: style, screenHeight: screen, textScale: 1.5);
      expect(scaled.editorHeight, greaterThan(normal.editorHeight));
    });
  });
}
