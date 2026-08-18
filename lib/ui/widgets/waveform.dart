import 'package:flutter/material.dart';

import '../../motion/waveform_model.dart';
import '../tokens.dart';

/// The 13 bars, or one flat line when the microphone is dead.
///
/// Repaints straight off a Listenable so a 20 Hz signal never causes a rebuild.
class Waveform extends StatelessWidget {
  const Waveform({
    super.key,
    required this.model,
    required this.repaint,
    required this.color,
  });

  final WaveformModel model;
  final Listenable repaint;
  final Color color;

  static const double width =
      AppSize.waveBars * AppSize.waveBarWidth + (AppSize.waveBars - 1) * AppSize.waveBarGap;

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: CustomPaint(
          size: const Size(width, AppSize.waveHeight),
          painter: _WavePainter(model: model, color: color, repaint: repaint),
        ),
      );
}

class _WavePainter extends CustomPainter {
  _WavePainter({required this.model, required this.color, required Listenable repaint})
      : super(repaint: repaint);

  final WaveformModel model;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = color;
    final middle = size.height / 2;

    if (model.flat) {
      // A straight 2px line says "nothing is arriving" without depending on colour.
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(0, middle - 1, size.width, 2),
          const Radius.circular(1),
        ),
        paint,
      );
      return;
    }

    for (var i = 0; i < AppSize.waveBars; i++) {
      final height = model.heightAt(i);
      final x = i * (AppSize.waveBarWidth + AppSize.waveBarGap);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(x, middle - height / 2, AppSize.waveBarWidth, height),
          const Radius.circular(AppSize.waveBarWidth / 2),
        ),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_WavePainter old) => old.color != color || old.model != model;
}
