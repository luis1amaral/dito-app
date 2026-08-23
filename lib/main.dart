import 'dart:async';
import 'dart:io';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

import 'app/boot.dart';
import 'core/logbook.dart';
import 'ui/dito_root_app.dart';

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  final crash = Logbook('crash');

  FlutterError.onError = (details) => crash('FlutterError: ${details.exception}\n${details.stack}');
  PlatformDispatcher.instance.onError = (error, stack) {
    crash('erro nao tratado: $error\n$stack');
    return true;
  };

  final startHidden = Platform.isLinux
      ? !args.contains('--janela')
      : args.contains('--startup') ||
          args.contains('--minimized') ||
          args.contains('--tray') ||
          args.contains('listen') ||
          args.contains('--hidden');

  // Must precede runApp or window_manager dereferences a null view; see armadilha 4.11.
  await windowManager.ensureInitialized();

  final app = DitoApp();
  runApp(DitoRootApp(app: app));
  unawaited(app.start(startHidden: startHidden));
}
