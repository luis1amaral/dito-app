// Proves a sub-window opens, keeps WS_EX_NOACTIVATE and never takes the foreground.
import 'dart:ffi';
import 'dart:io';

import 'package:desktop_multi_window/desktop_multi_window.dart';
import 'package:ffi/ffi.dart';
import 'package:flutter/material.dart';
import 'package:win32/win32.dart';

const String kHudArgument = 'hud';

// Sub-windows use this class; the main window uses FLUTTER_RUNNER_WIN32_WINDOW.
const String kSubWindowClass = 'FLUTTER_MULTI_WINDOW_WIN32_WINDOW';

final File _result = File('${Directory.current.path}/spike_result.txt');

void _say(String line) {
  _result.writeAsStringSync('$line\n', mode: FileMode.append, flush: true);
}

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  final controller = await WindowController.fromCurrentEngine();
  if (controller.arguments == kHudArgument) {
    runApp(const _Hud());
    return;
  }
  if (_result.existsSync()) _result.deleteSync();
  _say('== espinho multi-window ==');
  runApp(const _Main());
}

/// Describes a window by HWND: owning process, class and title.
String _describe(int hwnd) {
  if (hwnd == 0) return 'nenhuma';
  final buffer = wsalloc(256);
  final pid = calloc<Uint32>();
  try {
    GetWindowThreadProcessId(hwnd, pid);
    GetClassName(hwnd, buffer, 256);
    final cls = buffer.toDartString();
    GetWindowText(hwnd, buffer, 256);
    final title = buffer.toDartString();
    final mine = pid.value == GetCurrentProcessId() ? 'ESTE processo' : 'pid ${pid.value}';
    return '$hwnd [$mine] classe="$cls" titulo="$title"';
  } finally {
    free(buffer);
    free(pid);
  }
}

/// Finds the visible top-level window of a specific PID.
int _findWindowOfPid(int pid) {
  var found = 0;
  final owner = calloc<Uint32>();
  final cb = NativeCallable<WNDENUMPROC>.isolateLocal((int hwnd, int lp) {
    GetWindowThreadProcessId(hwnd, owner);
    if (owner.value != pid || IsWindowVisible(hwnd) == 0) return TRUE;
    found = hwnd;
    return FALSE;
  }, exceptionalReturn: 0);
  try {
    EnumWindows(cb.nativeFunction, 0);
  } finally {
    cb.close();
    free(owner);
  }
  return found;
}

/// Finds this process's sub-window by class; the real app gets the HWND from the plugin.
int _findSubWindow() {
  final me = GetCurrentProcessId();
  var found = 0;
  final buffer = wsalloc(256);
  final cb = NativeCallable<WNDENUMPROC>.isolateLocal((int hwnd, int lp) {
    final owner = calloc<Uint32>();
    try {
      GetWindowThreadProcessId(hwnd, owner);
      if (owner.value != me) return TRUE;
      GetClassName(hwnd, buffer, 256);
      if (buffer.toDartString() != kSubWindowClass) return TRUE;
      found = hwnd;
      return FALSE;
    } finally {
      free(owner);
    }
  }, exceptionalReturn: 0);
  try {
    EnumWindows(cb.nativeFunction, 0);
  } finally {
    cb.close();
    free(buffer);
  }
  return found;
}

/// Reads back what the fork applied at creation time.
void _applyHudStyles() {
  final hwnd = _findSubWindow();
  if (hwnd == 0) {
    _say('FALHOU: HWND da sub-janela nao encontrado');
    return;
  }
  // Nothing to apply: the fork already created the window styled; we only read it back.
  final now = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
  final noactivate = (now & WS_EX_NOACTIVATE) != 0;
  final toolwindow = (now & WS_EX_TOOLWINDOW) != 0;
  final topmost = (now & WS_EX_TOPMOST) != 0;
  _say('hwnd da sub-janela .......... $hwnd');
  _say('exstyle ..................... 0x${now.toRadixString(16)}');
  _say('WS_EX_NOACTIVATE ............ ${noactivate ? "OK" : "FALHOU"}');
  _say('WS_EX_TOOLWINDOW ............ ${toolwindow ? "OK" : "FALHOU"}');
  _say('WS_EX_TOPMOST ............... ${topmost ? "OK" : "FALHOU"}');
}

class _Main extends StatefulWidget {
  const _Main();
  @override
  State<_Main> createState() => _MainState();
}

class _MainState extends State<_Main> {
  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    await Future<void>.delayed(const Duration(seconds: 1));

    // The real dictation setting: another program holds focus, and that is where you type.
    final notepad = await Process.start('notepad.exe', <String>[]);
    var target = 0;
    for (var i = 0; i < 20 && target == 0; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 250));
      target = _findWindowOfPid(notepad.pid); // by PID: FindWindow would match an older notepad
    }
    SetForegroundWindow(target);
    await Future<void>.delayed(const Duration(milliseconds: 500));

    final foregroundBefore = GetForegroundWindow();
    _say('foreground antes ............ ${_describe(foregroundBefore)}');
    _say('alvo e o notepad? ........... '
        '${foregroundBefore == target && target != 0 ? "sim" : "NAO — teste invalido"}');

    try {
      final hud = await WindowController.create(
        const WindowConfiguration(arguments: kHudArgument, focusable: false),
      );
      _say('sub-janela criada ........... id=${hud.windowId}');
      await hud.show();
    } catch (e) {
      _say('FALHOU ao criar sub-janela: $e');
      exit(1);
    }

    await Future<void>.delayed(const Duration(seconds: 2));
    final foregroundAfter = GetForegroundWindow();
    final hudHwnd = _findSubWindow();
    _say('foreground depois ........... ${_describe(foregroundAfter)}');

    // The right assertion is not "foreground unchanged": it is that the HUD never IS it.
    final visible = IsWindowVisible(hudHwnd) != 0;
    final stoleFocus = foregroundAfter == hudHwnd;
    final kept = foregroundAfter == foregroundBefore;
    _say('HUD visivel ................. ${visible ? "OK" : "FALHOU (nao apareceu)"}');
    _say('HUD fora do foreground ...... ${stoleFocus ? "FALHOU (roubou o foco)" : "OK"}');
    _say('foco continua no notepad .... ${kept ? "OK" : "FALHOU"}');
    final pass = visible && !stoleFocus && kept;
    _say('VEREDITO .................... ${pass ? "PASSA" : "FALHA"}');
    _say('== fim ==');
    notepad.kill();
    exit(pass ? 0 : 1);
  }

  @override
  Widget build(BuildContext context) => const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Scaffold(body: Center(child: Text('espinho rodando…'))),
      );
}

class _Hud extends StatefulWidget {
  const _Hud();
  @override
  State<_Hud> createState() => _HudState();
}

class _HudState extends State<_Hud> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _applyHudStyles());
  }

  @override
  Widget build(BuildContext context) => const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Scaffold(
          backgroundColor: Color(0xFF17171C),
          body: Center(
            child: Text('HUD', style: TextStyle(color: Colors.white)),
          ),
        ),
      );
}
