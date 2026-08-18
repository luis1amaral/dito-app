// Runs inside the app process to check the hook end to end, safely: it focuses OUR window
// first and refuses to inject otherwise.
import 'dart:io';

import 'package:dito_win32/dito_win32.dart';
import 'package:flutter/material.dart';

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MaterialApp(home: Scaffold(body: SizedBox.shrink())));
  await Future<void>.delayed(const Duration(seconds: 1));

  await DitoWin32.bindKey(name: 'dictation', key: 'f9', suppress: true);
  await DitoWin32.focusWindow();
  await Future<void>.delayed(const Duration(milliseconds: 600));

  if (!await DitoWin32.ownsForeground()) {
    stderr.writeln('ABORTADO: a janela do teste nao esta em primeiro plano');
    exit(2);
  }

  await DitoWin32.injectKeyForTest('f9', down: true);
  await Future<void>.delayed(const Duration(milliseconds: 300));
  final held = await DitoWin32.keySnapshot();
  await DitoWin32.injectKeyForTest('f9', down: false);
  await Future<void>.delayed(const Duration(milliseconds: 300));
  final released = await DitoWin32.keySnapshot();

  stdout.writeln('segurando: $held');
  stdout.writeln('solto:     $released');
  exit(0);
}
