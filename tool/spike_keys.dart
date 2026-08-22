// Proves the hook: hold timing survives auto-repeat, and a bound key never reaches the app.
//
// The app's own window is the target, so "did the key get through" is read from Flutter's
// keyboard instead of from another program's text box, which can lie.
import 'dart:io';

import 'package:dito_app/keys/hotkey_machine.dart';
import 'package:dito_app/keys/native_key_source.dart';
import 'package:dito_win32/dito_win32.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

final File _result = File('${Directory.current.path}/spike_keys_result.txt');

void _say(String line) =>
    _result.writeAsStringSync('$line\n', mode: FileMode.append, flush: true);

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  if (_result.existsSync()) _result.deleteSync();
  _say('== espinho do hook de teclado ==');
  runApp(const _Spike());
}

class _Spike extends StatefulWidget {
  const _Spike();
  @override
  State<_Spike> createState() => _SpikeState();
}

class _SpikeState extends State<_Spike> {
  int _reachedApp = 0;

  bool _onKey(KeyEvent event) {
    if (event is KeyDownEvent && event.logicalKey == LogicalKeyboardKey.space) {
      _reachedApp++;
    }
    return false;
  }

  @override
  void initState() {
    super.initState();
    HardwareKeyboard.instance.addHandler(_onKey);
    WidgetsBinding.instance.addPostFrameCallback((_) => _run());
  }

  Future<void> _run() async {
    final source = NativeKeySource();
    final events = <String>[];
    final stopwatch = Stopwatch();

    final machine = HotkeyMachine(
      source: source,
      onStart: (a) {
        stopwatch
          ..reset()
          ..start();
        events.add('start:$a@0');
        return true;
      },
      onStop: (a) {
        stopwatch.stop();
        events.add('stop:$a@${stopwatch.elapsedMilliseconds}ms');
      },
    )
      ..bind(<HotkeyBinding>[
        const HotkeyBinding(action: 'dictation', key: 'space', mode: HotkeyMode.hold),
      ])
      ..start();

    var hookStatus = 'sem noticia';
    DitoWin32.keys.listen((signal) {
      if (signal is HookStatus) hookStatus = signal.status;
    });

    await Future<void>.delayed(const Duration(milliseconds: 1200));
    // SendInput is refused to a process without the foreground, so claim it first.
    await DitoWin32.focusWindow();
    await Future<void>.delayed(const Duration(milliseconds: 500));

    // Round 1: bound and suppressed. The key must not reach this window.
    await DitoWin32.bindKey(name: 'dictation', key: 'space', suppress: true);
    await Future<void>.delayed(const Duration(milliseconds: 300));
    _say('hook ........................ $hookStatus');
    _say('snapshot apos bind .......... ${await DitoWin32.keySnapshot()}');
    _reachedApp = 0;

    final accepted = await DitoWin32.injectKeyForTest('space', down: true);
    _say('SendInput aceito ............ $accepted');
    for (var i = 0; i < 30; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await DitoWin32.injectKeyForTest('space', down: true); // auto-repeat
    }
    _say('snapshot segurando .......... ${await DitoWin32.keySnapshot()}');
    await DitoWin32.injectKeyForTest('space', down: false);
    await Future<void>.delayed(const Duration(milliseconds: 900));

    final leaked = _reachedApp;
    _say('teclas que vazaram .......... $leaked');
    _say('supressao ................... ${leaked == 0 ? "OK" : "FALHOU"}');

    final starts = events.where((e) => e.startsWith('start:')).length;
    final stops = events.where((e) => e.startsWith('stop:')).toList();
    _say('eventos ..................... ${events.join("  ")}');
    _say('um unico start .............. ${starts == 1 ? "OK" : "FALHOU ($starts)"}');

    final holdMs = stops.isEmpty
        ? -1
        : int.tryParse(stops.first.split('@').last.replaceAll('ms', '')) ?? -1;
    // The trap: with the hook as authority this is ~3.3 s; trusting GetAsyncKeyState on a
    // suppressed key would give exactly the 300 ms grace instead.
    final holdOk = holdMs >= 2800 && holdMs <= 4200;
    _say('duracao do hold ............. ${holdMs}ms ${holdOk ? "OK" : "FALHOU"}');

    // Round 2: unbound. The very same key must reach the window again.
    await DitoWin32.unbindAll();
    await Future<void>.delayed(const Duration(milliseconds: 400));
    _reachedApp = 0;
    await DitoWin32.injectKeyForTest('space', down: true);
    await DitoWin32.injectKeyForTest('space', down: false);
    await Future<void>.delayed(const Duration(milliseconds: 800));

    final passthrough = _reachedApp > 0;
    _say('tecla solta chega ao app .... ${passthrough ? "OK" : "FALHOU ($_reachedApp)"}');

    final pass = leaked == 0 && starts == 1 && holdOk && passthrough;
    _say('VEREDITO .................... ${pass ? "PASSA" : "FALHA"}');
    _say('== fim ==');

    await machine.dispose();
    await source.dispose();
    exit(pass ? 0 : 1);
  }

  @override
  Widget build(BuildContext context) => const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Scaffold(body: Center(child: Text('espinho de teclas…'))),
      );
}
