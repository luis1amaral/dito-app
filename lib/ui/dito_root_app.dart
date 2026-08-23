import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:dito_win32/dito_win32.dart';

import '../app/boot.dart';
import '../l10n/app_strings.dart';
import 'hud/hud_state.dart';
import 'main/main_window.dart';
import 'overlay_policy.dart';
import 'overlay_stack.dart';
import 'theme.dart';
import 'tokens.dart';
import 'window_orchestrator.dart';

class DitoRootApp extends StatefulWidget {
  const DitoRootApp({super.key, required this.app});

  final DitoApp app;

  @override
  State<DitoRootApp> createState() => _DitoRootAppState();
}

class _DitoRootAppState extends State<DitoRootApp> {
  final GlobalKey _pill = GlobalKey();
  final GlobalKey _canvas = GlobalKey();
  final OverlayPolicy _policy = const OverlayPolicy();
  Rect? _hit;

  @override
  void initState() {
    super.initState();
    widget.app.hudState.addListener(_onHudChanged);
    widget.app.reviewEvent.addListener(_onReviewChanged);
    widget.app.orchestrator.addListener(_onOrchestratorChanged);
  }

  @override
  void dispose() {
    widget.app.hudState.removeListener(_onHudChanged);
    widget.app.reviewEvent.removeListener(_onReviewChanged);
    widget.app.orchestrator.removeListener(_onOrchestratorChanged);
    super.dispose();
  }

  void _onOrchestratorChanged() {
    if (mounted) setState(() {});
  }

  OverlayDecision _decide() => _policy.decide(
        hudOnScreen: widget.app.hudState.isOnScreen,
        reviewActive: widget.app.reviewEvent.value != null,
        mode: widget.app.orchestrator.mode,
      );

  void _onHudChanged() {
    if (!mounted) return;
    final decision = _decide();
    final orchestrator = widget.app.orchestrator;

    if (decision.showOverlay) {
      final dpr = View.of(context).devicePixelRatio;
      orchestrator.showOverlay(dpr: dpr);
      WidgetsBinding.instance.addPostFrameCallback((_) => _clipToPill());
    } else if (decision.hideOverlay) {
      orchestrator.hideOverlay();
    }
    setState(() {});
  }

  void _onReviewChanged() {
    if (!mounted) return;
    final decision = _decide();
    final orchestrator = widget.app.orchestrator;

    // Only the review path steals or gives back OS focus; the hud alone never types.
    if (decision.takeFocus) {
      final dpr = View.of(context).devicePixelRatio;
      orchestrator.showOverlay(dpr: dpr);
      DitoWin32.setFocusable(true);
      DitoWin32.focusWindow();
      WidgetsBinding.instance.addPostFrameCallback((_) => _clipToPill());
    } else if (decision.giveFocus) {
      DitoWin32.setFocusable(false);
      DitoWin32.giveBackFocus();
      orchestrator.hideOverlay();
    }
    setState(() {});
  }

  Future<void> _clipToPill() async {
    if (!mounted) return;
    final orchestrator = widget.app.orchestrator;
    if (orchestrator.mode != AppWindowMode.overlay) return;

    final box = _pill.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) {
      _hit = null;
      await DitoWin32.setHitRect(
        rect: const Rect.fromLTWH(0, 0, AppSize.hudCanvasWidth, AppSize.hudCanvasHeight),
        devicePixelRatio: View.of(context).devicePixelRatio,
      );
      return;
    }

    final rect = (box.localToGlobal(Offset.zero) & box.size).deflate(AppShadow.margin);
    if (rect.isEmpty || rect == _hit) return;
    _hit = rect;
    await DitoWin32.setHitRect(
      rect: rect,
      devicePixelRatio: View.of(context).devicePixelRatio,
      radius: AppRadius.overlay,
    );
  }

  void _onHudAction() {
    final hud = widget.app.hudState;
    if (hud.visual == HudVisual.dead) {
      // Retry mic
      widget.app.controller.onHotkeyStart('dictation');
    } else {
      widget.app.controller.onHotkeyStop('meeting');
    }
  }

  @override
  Widget build(BuildContext context) {
    final config = widget.app.config;
    final orchestrator = widget.app.orchestrator;

    return ListenableBuilder(
      listenable: config,
      builder: (_, _) => ChangeNotifierProvider.value(
        value: widget.app.updateController,
        child: MaterialApp(
          title: 'Dito',
          debugShowCheckedModeBanner: false,
          theme: appTheme(Brightness.light),
          darkTheme: appTheme(Brightness.dark),
          themeMode: themeModeFrom(config.config.ui.theme),
          localizationsDelegates: AppStrings.localizationsDelegates,
          supportedLocales: AppStrings.supportedLocales,
          locale: localeFromCode(config.config.ui.language),
          home: Scaffold(
            backgroundColor: orchestrator.mode == AppWindowMode.mainWindow
                ? Theme.of(context).scaffoldBackgroundColor
                : Colors.transparent,
            body: orchestrator.mode == AppWindowMode.mainWindow
                ? MainWindow(app: widget.app)
                : OverlayStack(
                    canvasKey: _canvas,
                    pillKey: _pill,
                    hudState: widget.app.hudState,
                    review: widget.app.reviewEvent.value,
                    onHudAction: _onHudAction,
                    onReviewSend: (text, {required toVault}) async {
                      final review = widget.app.reviewEvent.value!;
                      await widget.app.controller.onReviewSend(
                        text,
                        toVault: toVault,
                        sessionId: review.sessionId,
                      );
                      widget.app.reviewEvent.value = null;
                    },
                    onReviewDiscard: () {
                      final review = widget.app.reviewEvent.value!;
                      widget.app.controller.onReviewDiscard(sessionId: review.sessionId);
                      widget.app.reviewEvent.value = null;
                    },
                    onReviewContentChanged: () => WidgetsBinding.instance
                        .addPostFrameCallback((_) => _clipToPill()),
                  ),
          ),
        ),
      ),
    );
  }
}
