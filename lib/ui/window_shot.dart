import 'dart:io';
import 'dart:ui';

import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

/// Dumps what an overlay window actually composited, as a PNG with its alpha intact.
///
/// A screen grab cannot verify these windows: they carry per-pixel alpha through DWM, and
/// both BitBlt and PrintWindow come back black. The window has to photograph itself.
Future<String> shootBoundary(GlobalKey key, String path) async {
  final context = key.currentContext;
  final object = context?.findRenderObject();
  if (context == null || object is! RenderRepaintBoundary) return 'sem boundary';

  final image = await object.toImage(pixelRatio: View.of(context).devicePixelRatio);
  final bytes = await image.toByteData(format: ImageByteFormat.png);
  image.dispose();
  if (bytes == null) return 'sem bytes';

  await File(path).writeAsBytes(bytes.buffer.asUint8List());
  return path;
}
