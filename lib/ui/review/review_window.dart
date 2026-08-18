import 'dart:async';

import 'package:dito_win32/dito_win32.dart';
import 'package:flutter/material.dart';

import '../../platform/window_bus.dart';
import '../../l10n/app_strings.dart';
import '../theme.dart';
import '../window_shot.dart';
import '../tokens.dart';
import 'review_card.dart';

/// The review card in its own window: takes focus on purpose, hands it back before pasting.
class ReviewWindow extends StatefulWidget {
  const ReviewWindow({super.key, required this.bus, required this.ownerId});

  final WindowBus bus;
  final String ownerId;

  @override
  State<ReviewWindow> createState() => _ReviewWindowState();
}

class _ReviewWindowState extends State<ReviewWindow> {
  String? _text;
  bool _meeting = false;
  String _theme = 'auto';
  String _locale = 'auto';
  bool _placed = false;
  bool _visible = false;
  final GlobalKey _canvas = GlobalKey();
  final GlobalKey _card = GlobalKey();
  StreamSubscription<KeySignal>? _keySub;
  Rect? _hit;

  @override
  void initState() {
    super.initState();
    widget.bus.onMessage(_onMessage);
    _keySub = DitoWin32.keys.listen(_onGlobalKey);
    unawaited(_askAppearance());
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_apply()));
  }

  void _onGlobalKey(KeySignal signal) {
    if (signal is! KeyDown || _text == null || !_visible) return;
    final k = signal.key.toLowerCase();
    if (k == 'enter' || k == 'return' || k == 'numpadenter' || k == 'numpad enter') {
      unawaited(_send(_text ?? '', toVault: false));
    } else if (k == 'tab' || k == 'escape' || k == 'esc') {
      unawaited(_discard());
    }
  }

  @override
  void dispose() {
    _keySub?.cancel();
    super.dispose();
  }

  Future<Object?> _onMessage(String method, Map<String, Object?> data) async {
    if (method == 'reviewProbe') {
      final box = _card.currentContext?.findRenderObject() as RenderBox?;
      return 'mostrado=$_visible texto=${_text?.length ?? 0} '
          'view=${View.of(context).physicalSize} '
          'dpr=${View.of(context).devicePixelRatio} cartao=${box?.size}';
    }
    if (method == 'reviewShot') return shootBoundary(_canvas, data['path'] as String);
    if (method == 'appearance') {
      _applyAppearance(data);
      return null;
    }
    if (method == 'reviewHide') {
      await _finish();
      return null;
    }
    if (method != 'review') return null;
    setState(() {
      _text = data['text'] as String? ?? '';
      _meeting = data['meeting'] == true;
    });
    await _apply();
    return null;
  }

  /// Asks the owner instead of waiting: the broadcast may have gone out before we existed.
  Future<void> _askAppearance() async {
    final raw = await widget.bus.request(widget.ownerId, 'appearance', <String, Object?>{});
    if (raw is Map) _applyAppearance(Map<String, Object?>.from(raw));
  }

  void _applyAppearance(Map<String, Object?> data) {
    if (!mounted) return;
    setState(() {
      _theme = data['theme'] as String? ?? 'auto';
      _locale = data['locale'] as String? ?? 'auto';
    });
  }

  /// Places the fixed canvas once, then only shows and hides it.
  Future<void> _apply() async {
    if (!mounted) return;
    if (!_placed) {
      _placed = true;
      await DitoWin32.setBottomCenter(
        width: AppSize.reviewCanvasWidth,
        height: AppSize.reviewCanvasHeight,
        devicePixelRatio: View.of(context).devicePixelRatio,
        margin: AppSize.screenMargin,
      );
    }

    final shouldShow = _text != null;
    if (shouldShow && !_visible) {
      _visible = true;
      // Clip BEFORE showing to prevent flash, then re-clip AFTER showing to align with final HWND.
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        await _clipToCard();
        if (!_visible) return;
        await DitoWin32.showNoActivate();
        _hit = null;
        await _clipToCard();
        await DitoWin32.takeFocus();
        await DitoWin32.focusWindow();
        await Future<void>.delayed(const Duration(milliseconds: 120));
        if (_visible) {
          _hit = null;
          await _clipToCard();
          await DitoWin32.focusWindow();
        }
      });
    } else if (!shouldShow && _visible) {
      _visible = false;
      await DitoWin32.hideWindow();
    } else if (shouldShow) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _hit = null;
        unawaited(_clipToCard());
      });
    }
  }

  /// The region is the card's visible shape: it clips the canvas and bounds the clicks.
  Future<void> _clipToCard() async {
    if (!mounted) return;
    final box = _card.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    // Leave 1px clearance outside the surface so GDI clipping does not truncate anti-aliasing.
    final rect = (box.localToGlobal(Offset.zero) & box.size)
        .deflate(AppShadow.margin - 1);
    if (rect.isEmpty || rect == _hit) return;
    _hit = rect;
    await DitoWin32.setHitRect(
      rect: rect,
      devicePixelRatio: View.of(context).devicePixelRatio,
      radius: AppRadius.overlay,
    );
  }

  Future<void> _finish() async {
    setState(() => _text = null);
    await _apply();
    // Focus goes back BEFORE the caller pastes, or the text lands in this card.
    await DitoWin32.giveBackFocus();
  }

  Future<void> _send(String text, {required bool toVault}) async {
    await _finish();
    await widget.bus.send(widget.ownerId, 'reviewSend', <String, Object?>{
      'text': text,
      'toVault': toVault,
    });
  }

  Future<void> _discard() async {
    await _finish();
    await widget.bus.send(widget.ownerId, 'reviewDiscard', <String, Object?>{});
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
          // Fixed transparent canvas; the card sits at the bottom of it.
          body: RepaintBoundary(
            key: _canvas,
            child: Align(
              alignment: Alignment.bottomCenter,
              child: _text == null
                  ? const SizedBox.shrink()
                  : ReviewCard(
                      key: _card,
                      text: _text!,
                      meeting: _meeting,
                      onSend: (t, {required toVault}) =>
                          unawaited(_send(t, toVault: toVault)),
                      onDiscard: () => unawaited(_discard()),
                      // Cada mudanca de tamanho re-recorta a janela: sem isto o cartao crescia mas
                      // a regiao antiga cortava as linhas novas (parecia "nao cresce pra cima").
                      onContentChanged: () => WidgetsBinding.instance
                          .addPostFrameCallback((_) => unawaited(_clipToCard())),
                    ),
            ),
          ),
        ),
      );
}
