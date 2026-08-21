import 'dart:async';

import 'package:dito_win32/dito_win32.dart';
import 'package:flutter/foundation.dart';

import '../config/config_model.dart';
import '../core/logbook.dart';
import 'hotkey_machine.dart';
import 'key_source.dart';
import 'native_key_source.dart';

/// The global-hotkey seam behind an interface: Windows uses a low-level hook, Linux is a stub.
abstract class HotkeyService extends ChangeNotifier {
  bool Function(String action)? onStart;
  void Function(String action)? onStop;
  void Function(String action)? onHoldCeiling;
  void Function(String action, String blockedBy)? onRefused;

  /// False means the app cannot hear the keyboard: it has to say so, not fail silently.
  bool get hookInstalled;
  bool get isPaused;
  String? get activeAction;

  Future<void> start(HotkeyConfig config);
  Future<void> apply(HotkeyConfig config);
  Future<void> pause();
  Future<void> resume();
  String? conflictFor(String key, {String? ignoreAction});

  /// Ends any recording in progress before the hook goes away.
  void shutdown();

  /// Declared here so callers holding the interface can await teardown, not ChangeNotifier's void.
  @override
  Future<void> dispose();
}

/// Picks the platform implementation; both Windows and Linux use NativeKeySource.
HotkeyService createHotkeyService({KeySource? source, Logbook? log}) =>
    WindowsHotkeyService(source: source, log: log);

/// Wires the machine to the config and to the native Win32 hook.
class WindowsHotkeyService extends HotkeyService {
  WindowsHotkeyService({KeySource? source, Logbook? log})
      : _log = log ?? Logbook('hotkeys'),
        _source = source ?? NativeKeySource();

  final Logbook _log;
  final KeySource _source;

  HotkeyMachine? _machine;
  StreamSubscription<bool>? _hookSub;
  StreamSubscription<KeyDownSignal>? _downSpy;
  List<HotkeyBinding> _bindings = <HotkeyBinding>[];

  bool _hookInstalled = false;
  bool _paused = false;

  @override
  bool get hookInstalled => _hookInstalled;
  @override
  bool get isPaused => _paused;
  @override
  String? get activeAction => _machine?.active;

  @override
  Future<void> start(HotkeyConfig config) async {
    _machine ??= HotkeyMachine(
      source: _source,
      onStart: (action) {
        final accepted = onStart?.call(action) ?? false;
        _log('start: $action (aceito=$accepted)');
        return accepted;
      },
      onStop: (action) {
        _log('stop: $action');
        onStop?.call(action);
      },
      onCeilingReached: (action) => onHoldCeiling?.call(action),
      onRefused: (action, blockedBy) {
        _log('recusado: $action (ativo=$blockedBy)');
        onRefused?.call(action, blockedBy);
      },
    )..start();

    _downSpy ??= _source.downs.listen((d) => _log('tecla desceu: ${d.action}'));

    _hookSub ??= _source.hookAlive.listen((alive) {
      _hookInstalled = alive;
      _log(alive ? 'hook instalado' : 'hook perdido');
      notifyListeners();
    });

    await apply(config);
  }

  /// Rebinding is live: the gap between changing a shortcut and it working has to be zero.
  @override
  Future<void> apply(HotkeyConfig config) async {
    _bindings = <HotkeyBinding>[
      HotkeyBinding(
          action: 'dictation', key: config.pushToTalk, mode: HotkeyMode.hold),
      HotkeyBinding(
          action: 'meeting', key: config.meetingToggle, mode: HotkeyMode.toggle),
    ];
    _machine?.bind(_bindings);

    try {
      await DitoWin32.unbindAll();
      for (final binding in _bindings) {
        if (binding.key.trim().isEmpty) continue;
        await DitoWin32.bindKey(
          name: binding.action,
          key: binding.key,
          suppress: config.grab,
        );
        _log('tecla ligada: ${binding.action} -> ${binding.key} '
            '(consumir=${config.grab})');
      }
      // Ask the hook itself instead of assuming: it reports whether it is installed.
      final snapshot = await DitoWin32.keySnapshot();
      _hookInstalled = snapshot['_installed'] == true;
      _log('estado do hook: $snapshot');
      _startWatchdog();
    } catch (e) {
      _hookInstalled = false;
      _log('falha ao registrar as teclas: $e');
    }
    notifyListeners();
  }

  Timer? _watchdog;
  int _lastSeen = -1;

  /// Reports the hook counters whenever they move, so a silent hook is visible in the log.
  void _startWatchdog() {
    _watchdog?.cancel();
    _watchdog = Timer.periodic(const Duration(seconds: 3), (_) async {
      try {
        final snapshot = await DitoWin32.keySnapshot();
        final seen = (snapshot['_seen'] as num?)?.toInt() ?? 0;
        if (seen == _lastSeen) return;
        _lastSeen = seen;
        _log('hook viu $seen eventos: $snapshot');
      } catch (e) {
        _log('falha ao consultar o hook: $e');
      }
    });
  }

  @override
  Future<void> pause() async {
    _paused = true;
    _machine?.pause();
    try {
      await DitoWin32.pauseKeys();
    } catch (e) {
      _log('falha ao pausar as teclas: $e');
    }
    notifyListeners();
  }

  @override
  Future<void> resume() async {
    _paused = false;
    _machine?.resume();
    try {
      await DitoWin32.resumeKeys();
    } catch (e) {
      _log('falha ao retomar as teclas: $e');
    }
    notifyListeners();
  }

  @override
  String? conflictFor(String key, {String? ignoreAction}) =>
      _machine?.conflictFor(key, ignoreAction: ignoreAction);

  @override
  void shutdown() => _machine?.shutdown();

  @override
  Future<void> dispose() async {
    shutdown();
    _watchdog?.cancel();
    await _hookSub?.cancel();
    await _downSpy?.cancel();
    await _machine?.dispose();
    await _log.close();
    super.dispose();
  }
}

/// Linux stub: no global hotkey yet (needs X11/evdev or the XDG portal; see docs/LINUX.md).
class LinuxHotkeyService extends HotkeyService {
  LinuxHotkeyService({Logbook? log}) : _log = log ?? Logbook('hotkeys');

  final Logbook _log;
  bool _paused = false;

  @override
  bool get hookInstalled => false;
  @override
  bool get isPaused => _paused;
  @override
  String? get activeAction => null;

  @override
  Future<void> start(HotkeyConfig config) async {
    _log('atalho global ainda nao implementado no Linux (stub)');
  }

  @override
  Future<void> apply(HotkeyConfig config) async {}

  @override
  Future<void> pause() async {
    _paused = true;
  }

  @override
  Future<void> resume() async {
    _paused = false;
  }

  @override
  String? conflictFor(String key, {String? ignoreAction}) => null;

  @override
  void shutdown() {}

  @override
  Future<void> dispose() async {
    await _log.close();
    super.dispose();
  }
}
