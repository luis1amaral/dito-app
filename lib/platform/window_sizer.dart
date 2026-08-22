import 'dart:async';

import 'package:dito_win32/dito_win32.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

import '../ui/tokens.dart';

/// Sizes a borderless window to its own content, bottom-centred.
///
/// The content must be measured UNCONSTRAINED. Measuring it inside the window we are about to
/// resize is a feedback loop: the window shrinks, the content shrinks with it, and the next
/// frame shrinks again - the review card collapsed to 19px tall that way.
class WindowSizer {
  WindowSizer({required this.margin, WindowPlacer? placer})
      : _placer = placer ?? const NativeWindowPlacer();

  final double margin;
  final WindowPlacer _placer;

  Size _applied = Size.zero;
  bool _visible = false;
  bool _busy = false;

  Size get appliedSize => _applied;
  bool get isVisible => _visible;

  /// True when the size moved enough to be worth a native call.
  static bool changed(Size a, Size b) =>
      (a.width - b.width).abs() > 0.5 || (a.height - b.height).abs() > 0.5;

  /// Applies the content size to the window, showing or hiding it as needed.
  Future<void> sync({
    required Size content,
    required double devicePixelRatio,
    required bool shouldShow,
    double minWidth = 0,
    double minHeight = 0,
  }) async {
    if (_busy) return;
    _busy = true;
    try {
      if (shouldShow) {
        // A height below the floor means the layout has not settled; applying it is what
        // starts the shrink spiral.
        if (content.height < minHeight) return;

        final width = content.width < minWidth ? minWidth : content.width;
        final size = Size(width, content.height);
        if (changed(size, _applied)) {
          _applied = size;
          await _placer.place(
            width: size.width,
            height: size.height,
            devicePixelRatio: devicePixelRatio,
            margin: margin,
          );
        }
        if (!_visible && _applied.height >= minHeight && _applied.height > 0) {
          _visible = true;
          await _placer.show();
        }
      } else if (_visible) {
        _visible = false;
        _applied = Size.zero;
        await _placer.hide();
      }
    } finally {
      _busy = false;
    }
  }
}

/// The native side of placing a window; an interface so sizing can be tested without Windows.
abstract class WindowPlacer {
  Future<void> place({
    required double width,
    required double height,
    required double devicePixelRatio,
    required double margin,
  });

  Future<void> show();
  Future<void> hide();
}

class NativeWindowPlacer implements WindowPlacer {
  const NativeWindowPlacer();

  @override
  Future<void> place({
    required double width,
    required double height,
    required double devicePixelRatio,
    required double margin,
  }) =>
      DitoWin32.setBottomCenter(
        width: width,
        height: height,
        devicePixelRatio: devicePixelRatio,
        margin: margin,
      );

  @override
  Future<void> show() => DitoWin32.showNoActivate();

  @override
  Future<void> hide() => DitoWin32.hideWindow();
}

/// Reports its child's natural size, measured free of the window's own constraints.
class MeasuredContent extends StatelessWidget {
  const MeasuredContent({
    super.key,
    required this.child,
    required this.onMeasured,
    this.minWidth = AppSize.hudMinWidth,
  });

  final Widget child;
  final void Function(Size size) onMeasured;
  final double minWidth;

  @override
  Widget build(BuildContext context) => Align(
        alignment: Alignment.bottomCenter,
        child: OverflowBox(
          alignment: Alignment.bottomCenter,
          minWidth: 0,
          maxWidth: double.infinity,
          minHeight: 0,
          maxHeight: double.infinity,
          child: _SizeReporter(
            onMeasured: onMeasured,
            child: ConstrainedBox(
              constraints: BoxConstraints(minWidth: minWidth),
              child: IntrinsicWidth(child: child),
            ),
          ),
        ),
      );
}

class _SizeReporter extends SingleChildRenderObjectWidget {
  const _SizeReporter({required this.onMeasured, required super.child});

  final void Function(Size size) onMeasured;

  @override
  _RenderSizeReporter createRenderObject(BuildContext context) =>
      _RenderSizeReporter(onMeasured);

  @override
  void updateRenderObject(BuildContext context, _RenderSizeReporter renderObject) {
    renderObject.onMeasured = onMeasured;
  }
}

class _RenderSizeReporter extends RenderProxyBox {
  _RenderSizeReporter(this.onMeasured);

  void Function(Size size) onMeasured;
  Size _reported = Size.zero;

  @override
  void performLayout() {
    super.performLayout();
    final current = hasSize ? size : Size.zero;
    if (!WindowSizer.changed(current, _reported)) return;
    _reported = current;
    // Reporting during layout would mutate the tree mid-flight.
    scheduleMicrotask(() => onMeasured(_reported));
  }
}
