import 'dart:async';
import 'dart:ui';

import 'package:dito_win32/dito_win32.dart';
import 'package:flutter/foundation.dart';
import 'package:window_manager/window_manager.dart';

import '../core/logbook.dart';
import 'tokens.dart';

const WindowOptions _bootOptions = WindowOptions(
  size: Size(880, 760),
  minimumSize: Size(720, 620),
  center: true,
  title: 'Dito',
  titleBarStyle: TitleBarStyle.normal,
);

enum AppWindowMode {
  hidden,
  overlay,
  mainWindow,
}

/// Controls the single native window geometry, placement, and focus.
class WindowOrchestrator extends ChangeNotifier {
  WindowOrchestrator() : _log = Logbook('window_orchestrator');

  final Logbook _log;
  AppWindowMode _mode = AppWindowMode.hidden;
  AppWindowMode get mode => _mode;

  bool _isInitialized = false;
  bool _busy = false;

  Future<void> init({bool startHidden = true}) async {
    if (_isInitialized) return;
    _isInitialized = true;

    // waitUntilReadyToShow is the ONLY place window_manager CoCreates its ITaskbarList3, and
    // setSkipTaskbar dereferences it unguarded; skipping it segfaults on boot. Armadilha 4.12.
    await windowManager.waitUntilReadyToShow(_bootOptions, () async {
      await windowManager.setPreventClose(true);
      if (startHidden) {
        _mode = AppWindowMode.hidden;
        await windowManager.setSkipTaskbar(true);
        await windowManager.hide();
      } else {
        await showMainWindow();
      }
    });
  }

  Future<void> showOverlay({required double dpr}) async {
    if (_mode == AppWindowMode.mainWindow) {
      return;
    }
    _mode = AppWindowMode.overlay;
    notifyListeners();

    if (_busy) return;
    _busy = true;
    try {
      await windowManager.setAlwaysOnTop(true);
      await windowManager.setSkipTaskbar(true);
      await DitoWin32.setBottomCenter(
        width: AppSize.hudCanvasWidth,
        height: AppSize.hudCanvasHeight,
        devicePixelRatio: dpr,
        margin: AppSize.screenMargin,
      );
      await DitoWin32.showNoActivate();
    } catch (e) {
      _log('showOverlay error: $e');
    } finally {
      _busy = false;
    }
  }

  Future<void> hideOverlay() async {
    if (_mode != AppWindowMode.overlay) return;
    _mode = AppWindowMode.hidden;
    notifyListeners();

    try {
      await DitoWin32.setHitRect(
        rect: Rect.zero,
        devicePixelRatio: 1.0,
      );
      await windowManager.hide();
    } catch (e) {
      _log('hideOverlay error: $e');
    }
  }

  Future<void> showMainWindow() async {
    _mode = AppWindowMode.mainWindow;
    notifyListeners();

    try {
      await DitoWin32.setFocusable(true);
      await windowManager.setAlwaysOnTop(false);
      await windowManager.setSkipTaskbar(false);
      await windowManager.setSize(const Size(880, 760));
      await windowManager.setMinimumSize(const Size(720, 620));
      await windowManager.center();
      await windowManager.show();
      await windowManager.focus();
    } catch (e) {
      _log('showMainWindow error: $e');
    }
  }

  Future<void> hideMainWindow() async {
    _mode = AppWindowMode.hidden;
    notifyListeners();

    try {
      await windowManager.setSkipTaskbar(true);
      await windowManager.hide();
    } catch (e) {
      _log('hideMainWindow error: $e');
    }
  }
}
