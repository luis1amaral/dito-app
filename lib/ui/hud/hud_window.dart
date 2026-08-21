import 'dart:async';

import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:dito_win32/dito_win32.dart';
import 'package:flutter/material.dart';

import '../../core/logbook.dart';
import '../../platform/window_bus.dart';
import '../../state/hud_commands.dart';
import '../../l10n/app_strings.dart';
import '../theme.dart';
import '../window_shot.dart';
import '../tokens.dart';
import 'hud_pill.dart';
import 'hud_state.dart';

/// Entry point of the HUD window; it renders signals and reports intents, nothing more.
Future<void> runHudWindow(WindowController controller, String ownerId) async {
  final state = HudState();
  final bus = MultiWindowBus(controller);

  runApp(_HudApp(state: state, bus: bus, controller: controller, ownerId: ownerId));

  // The styles were set at creation; this only makes sure we stay out of the taskbar.
  await DitoWin32.adoptAsHud();
}

class _HudApp extends StatefulWidget {
  const _HudApp({
    required this.state,
    required this.bus,
    required this.controller,
    required this.ownerId,
  });

  final HudState state;
  final MultiWindowBus bus;
  final WindowController controller;
  final String ownerId;

  @override
  State<_HudApp> createState() => _HudAppState();
}

class _HudAppState extends State<_HudApp> {
  final _log = Logbook('hud_window');
  String _theme = 'auto';
  String _locale = 'auto';
  bool _placed = false;
  bool _visible = false;
  final GlobalKey _pill = GlobalKey();
  final GlobalKey _canvas = GlobalKey();
  Rect? _hit;

  @override
  void initState() {
    super.initState();
    widget.state.addListener(_onStateChanged);
    widget.bus.onMessage(_onMessage);
    unawaited(_askAppearance());
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_apply()));
  }

  Future<Object?> _onMessage(String method, Map<String, Object?> data) async {
    if (method == 'hudRect') {
      final rect = await DitoWin32.windowRect();
      return '${rect.left},${rect.top},${rect.right},${rect.bottom}';
    }
    if (method == 'hudProbe') {
      final view = View.of(context);
      final box = _pill.currentContext?.findRenderObject() as RenderBox?;
      return 'visual=${widget.state.visual.name} mostrado=$_visible '
          'acao=${widget.state.action.name} dpr=${view.devicePixelRatio} '
          'view=${view.physicalSize} pilula=${box?.size} '
          'pos=${box?.localToGlobal(Offset.zero)}';
    }
    if (method == 'hudShot') return shootBoundary(_canvas, data['path'] as String);
    if (method == 'appearance') {
      _applyAppearance(data);
      return null;
    }
    if (method != 'hud') return null;
    widget.state.apply(HudMessage.fromMap(data));
    return null;
  }

  /// Asks the owner instead of waiting: the broadcast may have gone out before we existed.
  /// Retried because giving up leaves the window on the system locale, not the configured one.
  Future<void> _askAppearance() async {
    for (var attempt = 0; attempt < 10; attempt++) {
      if (!mounted) return;
      final raw = await widget.bus.request(widget.ownerId, 'appearance', <String, Object?>{});
      if (raw is Map) {
        _applyAppearance(Map<String, Object?>.from(raw));
        return;
      }
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    _log('sem resposta de appearance: janela fica no idioma e tema do sistema');
  }

  void _applyAppearance(Map<String, Object?> data) {
    if (!mounted) return;
    setState(() {
      _theme = data['theme'] as String? ?? 'auto';
      _locale = data['locale'] as String? ?? 'auto';
    });
  }

  void _onStateChanged() {
    setState(() {});
    unawaited(_apply());
  }

  /// Runs one native window call best-effort: logs on failure instead of hiding it.
  Future<void> _tryNative(String what, Future<void> Function() call) async {
    try {
      await call();
    } catch (e) {
      _log('$what falhou: $e');
    }
  }

  /// Places the fixed canvas once, then only shows and hides it.
  Future<void> _apply() async {
    if (!mounted) return;
    final ratio = View.of(context).devicePixelRatio;

    if (!_placed) {
      _placed = true;
      await DitoWin32.setBottomCenter(
        width: AppSize.hudCanvasWidth,
        height: AppSize.hudCanvasHeight,
        devicePixelRatio: ratio,
        margin: AppSize.screenMargin,
      );
    }

    final shouldShow = widget.state.isOnScreen;
    if (shouldShow && !_visible) {
      _visible = true;
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        await _clipToPill();
        if (_visible) {
          await _tryNative('show', widget.controller.show);
          await _tryNative('showNoActivate', DitoWin32.showNoActivate);
          _hit = null;
          await _clipToPill();
        }
      });
    } else if (!shouldShow && _visible) {
      _visible = false;
      await _tryNative('hide', widget.controller.hide);
      await _tryNative('hideWindow', DitoWin32.hideWindow);
    } else if (shouldShow) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _hit = null;
        unawaited(_clipToPill());
      });
    }
  }

  /// The region is the pill's visible shape: it clips the canvas and bounds the clicks.
  Future<void> _clipToPill() async {
    if (!mounted) return;
    final box = _pill.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    // Region matches the pill surface exactly to avoid black edge cuts.
    final rect = (box.localToGlobal(Offset.zero) & box.size)
        .deflate(AppShadow.margin);
    if (rect.isEmpty || rect == _hit) return;
    _hit = rect;
    await DitoWin32.setHitRect(
      rect: rect,
      devicePixelRatio: View.of(context).devicePixelRatio,
      radius: AppRadius.overlay,
    );
  }

  void _onAction() {
    final intent = widget.state.visual == HudVisual.dead
        ? HudIntent.fixRequested
        : HudIntent.stopRequested;
    widget.bus.send(widget.ownerId, 'hudIntent', <String, Object?>{'intent': intent.name});
  }

  @override
  void dispose() {
    widget.state.removeListener(_onStateChanged);
    unawaited(_log.close());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: appTheme(Brightness.light),
        darkTheme: appTheme(Brightness.dark),
        themeMode: themeModeFrom(_theme),
        localizationsDelegates: AppStrings.localizationsDelegates,
        supportedLocales: AppStrings.supportedLocales,
        locale: localeFromCode(_locale),
        home: Scaffold(
          backgroundColor: Colors.transparent,
          // Fixed transparent canvas; the pill sizes itself and sits at the bottom.
          // No IntrinsicWidth here: it inflated the pill to the whole canvas width.
          body: RepaintBoundary(
            key: _canvas,
            child: Align(
              alignment: Alignment.bottomCenter,
              child: HudPill(key: _pill, state: widget.state, onAction: _onAction),
            ),
          ),
        ),
      );
}
