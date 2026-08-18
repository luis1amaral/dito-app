import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../tokens.dart';

/// Pulsing dot inside a fixed box, so the row never shifts as it breathes.
class StatusDot extends StatelessWidget {
  const StatusDot({
    super.key,
    required this.color,
    required this.repaint,
    required this.phase,
    this.pulsing = true,
  });

  final Color color;
  final Listenable repaint;

  /// 0..1 around the cosine period; the owner advances it.
  final double Function() phase;
  final bool pulsing;

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: CustomPaint(
          size: const Size.square(AppSize.dotBox),
          painter: _DotPainter(
            color: color,
            pulsing: pulsing,
            phase: phase,
            repaint: repaint,
          ),
        ),
      );
}

class _DotPainter extends CustomPainter {
  _DotPainter({
    required this.color,
    required this.pulsing,
    required this.phase,
    required Listenable repaint,
  }) : super(repaint: repaint);

  final Color color;
  final bool pulsing;
  final double Function() phase;

  @override
  void paint(Canvas canvas, Size size) {
    final t = pulsing ? 0.5 - 0.5 * math.cos(2 * math.pi * phase()) : 1.0;
    final diameter = AppSize.dotMin + (AppSize.dotMax - AppSize.dotMin) * t;
    // Float geometry, or the circle jitters as it grows.
    canvas.drawCircle(
      Offset(size.width / 2, size.height / 2),
      diameter / 2,
      Paint()..color = color,
    );
  }

  @override
  bool shouldRepaint(_DotPainter old) => old.color != color || old.pulsing != pulsing;
}
