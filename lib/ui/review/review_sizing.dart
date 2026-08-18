import 'package:flutter/material.dart';

import '../tokens.dart';

/// How tall the review card must be to show the whole text without ever scrolling.
///
/// Measured with a TextPainter rather than from the widget: before it has been shown the
/// viewport lies, and the document reports a single line.
class ReviewSizing {
  const ReviewSizing({
    this.width = AppSize.reviewWidth,
    this.minLines = 3,
    this.chrome = 200,
  });

  final double width;

  /// The card never shrinks below this, however short the text.
  final int minLines;

  /// Everything around the editor: title, hint, switch and buttons.
  final double chrome;

  /// Usable text width: the card minus its padding and the editor's own inset.
  double get textWidth => width - 2 * AppSpacing.xl - 2 * AppSpacing.md - 2 * AppSize.hairline;

  /// Lines the text needs at this width.
  int linesFor(String text, TextStyle style, {double textScale = 1.0}) {
    final painter = TextPainter(
      text: TextSpan(text: text.isEmpty ? ' ' : text, style: style),
      textDirection: TextDirection.ltr,
      textScaler: TextScaler.linear(textScale),
    )..layout(maxWidth: textWidth);

    final lineHeight = painter.preferredLineHeight;
    if (lineHeight <= 0) return minLines;
    return (painter.height / lineHeight).ceil();
  }

  /// How many lines still fit on screen once the card's own chrome is accounted for.
  int ceilingFor(double screenHeight, double lineHeight) {
    if (lineHeight <= 0) return minLines;
    final room = screenHeight - 2 * AppSize.screenMargin - chrome;
    final fits = (room / lineHeight).floor();
    return fits < minLines ? minLines : fits;
  }

  /// Final editor height, with half a line of slack so the last line is never clipped.
  double editorHeight(int lines, double lineHeight) =>
      lines * lineHeight + lineHeight / 2 + AppSpacing.xl;

  /// The whole computation in one call.
  ReviewMetrics measure({
    required String text,
    required TextStyle style,
    required double screenHeight,
    double textScale = 1.0,
  }) {
    final painter = TextPainter(
      text: TextSpan(text: text.isEmpty ? ' ' : text, style: style),
      textDirection: TextDirection.ltr,
      textScaler: TextScaler.linear(textScale),
    )..layout(maxWidth: textWidth);

    final lineHeight = painter.preferredLineHeight;
    final needed = lineHeight <= 0 ? minLines : (painter.height / lineHeight).ceil();
    final ceiling = ceilingFor(screenHeight, lineHeight);
    final lines = needed.clamp(minLines, ceiling);

    return ReviewMetrics(
      lines: lines,
      lineHeight: lineHeight,
      editorHeight: editorHeight(lines, lineHeight),
      cardWidth: width,
      atCeiling: needed > ceiling,
    );
  }
}

class ReviewMetrics {
  const ReviewMetrics({
    required this.lines,
    required this.lineHeight,
    required this.editorHeight,
    required this.cardWidth,
    required this.atCeiling,
  });

  final int lines;
  final double lineHeight;
  final double editorHeight;
  final double cardWidth;

  /// True only when the text is taller than the screen; the single case that may scroll.
  final bool atCeiling;
}
