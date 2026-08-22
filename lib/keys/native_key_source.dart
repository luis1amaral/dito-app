import 'dart:async';

import 'package:dito_win32/dito_win32.dart' as win32;

import 'key_source.dart';

/// KeySource backed by the low-level hook; reinstalls itself if Windows drops the hook.
class NativeKeySource implements KeySource {
  NativeKeySource() {
    _sub = win32.DitoWin32.keys.listen(_onSignal, onError: (Object _) {}, cancelOnError: false);
  }

  final _downs = StreamController<KeyDownSignal>.broadcast();
  final _ticks = StreamController<KeyTickSignal>.broadcast();
  final _hook = StreamController<bool>.broadcast();
  final _grabs = StreamController<KeyGrabSignal>.broadcast();
  StreamSubscription<win32.KeySignal>? _sub;

  @override
  Stream<KeyDownSignal> get downs => _downs.stream;

  @override
  Stream<KeyTickSignal> get ticks => _ticks.stream;

  @override
  Stream<bool> get hookAlive => _hook.stream;

  @override
  Stream<KeyGrabSignal> get grabs => _grabs.stream;

  void _onSignal(win32.KeySignal signal) {
    switch (signal) {
      case win32.KeyDown(:final action, :final micros):
        _downs.add(KeyDownSignal(action, micros));
      case win32.KeyTick(:final down, :final micros):
        _ticks.add(KeyTickSignal(down, micros));
      case win32.HookStatus(:final installed):
        _hook.add(installed);
      case win32.GrabStatus(:final action, :final key, :final ok):
        _grabs.add(KeyGrabSignal(action, key, ok));
      case win32.KeyUp():
        // Informative only: the tick is the authority on whether a key is up.
        break;
      case win32.UnknownSignal():
        break;
    }
  }

  Future<void> dispose() async {
    await _sub?.cancel();
    await _downs.close();
    await _ticks.close();
    await _hook.close();
    await _grabs.close();
  }
}
