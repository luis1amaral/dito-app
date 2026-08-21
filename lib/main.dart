import 'dart:async';
import 'dart:ui';

import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

import 'app/boot.dart';
import 'core/logbook.dart';
import 'ui/hud/hud_window.dart';
import 'ui/main/main_window.dart';
import 'ui/review/review_window.dart';

/// One entry point for every window; the role arrives as the sub-window argument.
Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  final crash = Logbook('crash');

  FlutterError.onError = (details) => crash('FlutterError: ${details.exception}\n${details.stack}');
  PlatformDispatcher.instance.onError = (error, stack) {
    crash('erro nao tratado: $error\n$stack');
    return true;
  };

  final controller = await WindowController.fromCurrentEngine();
  final parts = controller.arguments.split(':');
  final role = parts.first.isEmpty ? WindowRole.main : parts.first;
  final ownerId = parts.length > 1 ? parts[1] : '';

  switch (role) {
    case WindowRole.hud:
      await runHudWindow(controller, ownerId);
    case WindowRole.review:
      await runReviewWindow(controller, ownerId);
    default:
      // Boot com o Windows passa --startup (ver dito.iss): o app sobe pronto, mas na bandeja,
      // sem abrir a janela na cara de quem acabou de ligar o PC. Abrir manual = janela normal.
      final startHidden = args.contains('--startup') ||
          args.contains('--minimized') ||
          args.contains('--tray') ||
          args.contains('listen') ||
          args.contains('--hidden');
      await _runMainWindow(startHidden: startHidden);
  }
}

Future<void> _runMainWindow({bool startHidden = false}) async {
  await windowManager.ensureInitialized();
  await windowManager.setPreventClose(true);

  final app = DitoApp();
  runApp(DitoMainApp(app: app));

  const options = WindowOptions(
    size: Size(880, 760),
    minimumSize: Size(720, 620),
    center: true,
    title: 'Dito',
    backgroundColor: Colors.transparent,
    titleBarStyle: TitleBarStyle.normal,
  );

  // Size and centre it even while hidden, or it opens as whatever strip Windows remembered.
  await windowManager.waitUntilReadyToShow(options, () async {
    await windowManager.setSize(const Size(880, 760));
    await windowManager.center();
    if (startHidden) {
      // Fica pronto na bandeja: sem barra de tarefas e sem roubar foco no boot. O runner
      // (flutter_window.cpp) tambem segura o Show() quando ha --startup, para nao piscar.
      await windowManager.setSkipTaskbar(true);
      await windowManager.hide();
    } else {
      await windowManager.show();
      await windowManager.focus();
    }
  });

  app.onOpenWindow = () async {
    if (!await windowManager.isVisible()) {
      await windowManager.setSize(const Size(880, 760));
      await windowManager.center();
    }
    // Voltar da bandeja: reaparece na barra de tarefas de novo.
    await windowManager.setSkipTaskbar(false);
    await windowManager.show();
    await windowManager.focus();
  };

  unawaited(app.start());
}
