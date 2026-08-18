import 'package:flutter/material.dart';

import '../tokens.dart';

/// Rounded card with a hand-painted shadow.
///
/// Painted by hand because a drop-shadow effect does not show on a frameless translucent
/// window; the alpha falls off quadratically, since linear reads as visible banding.
class FloatingSurface extends StatelessWidget {
  const FloatingSurface({
    super.key,
    required this.child,
    required this.fill,
    this.border,
    this.radius = AppRadius.overlay,
  });

  final Widget child;
  final Color fill;
  final Color? border;
  final double radius;

  @override
  Widget build(BuildContext context) => CustomPaint(
        painter: _SurfacePainter(fill: fill, border: border, radius: radius),
        child: Padding(
          padding: const EdgeInsets.all(AppShadow.margin),
          child: child,
        ),
      );
}

class _SurfacePainter extends CustomPainter {
  const _SurfacePainter({required this.fill, required this.border, required this.radius});

  final Color fill;
  final Color? border;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    const margin = AppShadow.margin;
    final card = Rect.fromLTWH(
      margin,
      margin,
      size.width - margin * 2,
      size.height - margin * 2,
    );
    if (card.isEmpty) return;

    for (var i = 0; i < AppShadow.layers; i++) {
      final t = i / AppShadow.layers;
      final alpha = (AppShadow.alpha * (1 - t) * (1 - t)).round() + 2;
      final grow = AppShadow.spread * t;
      final rect = RRect.fromRectAndRadius(
        card.inflate(grow).translate(0, AppShadow.offset * t),
        Radius.circular(radius + grow),
      );
      canvas.drawRRect(rect, Paint()..color = Color.fromARGB(alpha, 0, 0, 0));
    }

    final body = RRect.fromRectAndRadius(card, Radius.circular(radius));
    canvas.drawRRect(body, Paint()..color = fill);

    if (border != null) {
      canvas.drawRRect(
        body,
        Paint()
          ..color = border!
          ..style = PaintingStyle.stroke
          ..strokeWidth = AppSize.hairline,
      );
    }
  }

  @override
  bool shouldRepaint(_SurfacePainter old) =>
      old.fill != fill || old.border != border || old.radius != radius;
}
