import 'dart:async';

import 'key_source.dart';

/// The key must be physically up for this long, continuously, before a hold ends.
///
/// There is no time debounce: any window wide enough to swallow auto-repeat also swallows a
/// legitimate double tap. The keymap has no such dilemma, it knows whether the finger left.
const Duration kGrace = Duration(milliseconds: 300);

/// A push-to-talk of ten minutes is a defect; the unlimited mode is the toggle.
const Duration kHoldCeiling = Duration(minutes: 10);

enum HotkeyMode { hold, toggle }

class HotkeyBinding {
  const HotkeyBinding({required this.action, required this.key, required this.mode});

  final String action;
  final String key;
  final HotkeyMode mode;
}

/// Port of src/dito/platform/hotkeys_core.py, driven by physical state, never by release events.
class HotkeyMachine {
  HotkeyMachine({
    required this.source,
    required this.onStart,
    required this.onStop,
    this.grace = kGrace,
    this.holdCeiling = kHoldCeiling,
    this.onCeilingReached,
    this.onRefused,
  });

  final KeySource source;

  /// Returns whether the start was accepted; a refusal must roll `_active` back.
  final bool Function(String action) onStart;
  final void Function(String action) onStop;
  final void Function(String action)? onCeilingReached;

  /// A press swallowed because another action holds the machine; silence here reads as a dead key.
  final void Function(String action, String blockedBy)? onRefused;
  final Duration grace;
  final Duration holdCeiling;

  final List<HotkeyBinding> _bindings = <HotkeyBinding>[];
  final Map<String, StreamSubscription<void>> _subs = <String, StreamSubscription<void>>{};

  StreamSubscription<KeyDownSignal>? _downSub;
  StreamSubscription<KeyTickSignal>? _tickSub;

  String? _active;
  int? _activeSince;
  int? _upSince;
  bool _paused = false;
  bool _shuttingDown = false;

  /// Toggles held from the previous press, so auto-repeat cannot flip them.
  final Set<String> _awaitingRelease = <String>{};

  String? get active => _active;
  bool get isPaused => _paused;

  void bind(List<HotkeyBinding> bindings) {
    _bindings
      ..clear()
      ..addAll(bindings);
  }

  void start() {
    _downSub = source.downs.listen(_onDown);
    _tickSub = source.ticks.listen(_onTick);
  }

  HotkeyBinding? _bindingFor(String action) {
    for (final binding in _bindings) {
      if (binding.action == action) return binding;
    }
    return null;
  }

  void _onDown(KeyDownSignal signal) {
    if (_paused || _shuttingDown) return;
    final binding = _bindingFor(signal.action);
    if (binding == null) return;

    switch (binding.mode) {
      case HotkeyMode.hold:
        // Same action already running means auto-repeat, not a new press.
        if (_active == binding.action) return;
        if (_active != null) {
          onRefused?.call(binding.action, _active!);
          return;
        }
        _begin(binding.action, signal.micros);

      case HotkeyMode.toggle:
        // Still held from last time: 1.5 s on the key used to produce 17 start/stop pairs.
        if (_awaitingRelease.contains(binding.action)) return;
        _awaitingRelease.add(binding.action);
        if (_active == binding.action) {
          _active = null;
          _activeSince = null;
          _upSince = null;
          onStop(binding.action);
        } else if (_active == null) {
          _begin(binding.action, signal.micros);
        } else {
          onRefused?.call(binding.action, _active!);
        }
    }
  }

  /// A start the controller refuses must not leave the machine marked active.
  void _begin(String action, int micros) {
    _active = action;
    _activeSince = micros;
    _upSince = null;
    if (!onStart(action)) {
      _active = null;
      _activeSince = null;
      _upSince = null;
    }
  }

  void _onTick(KeyTickSignal signal) {
    if (_shuttingDown) return;

    // A toggle is free to fire again only once the keymap says the key really came up.
    _awaitingRelease.removeWhere((action) => !signal.down.contains(action));

    final active = _active;
    if (active == null) return;
    final binding = _bindingFor(active);
    if (binding == null || binding.mode != HotkeyMode.hold) return;

    final since = _activeSince;
    if (since != null && signal.micros - since >= holdCeiling.inMicroseconds) {
      _active = null;
      _activeSince = null;
      _upSince = null;
      onCeilingReached?.call(active);
      onStop(active);
      return;
    }

    if (signal.down.contains(active)) {
      // A ghost release is swallowed: the same recording carries on.
      _upSince = null;
      return;
    }

    _upSince ??= signal.micros;
    if (signal.micros - _upSince! < grace.inMicroseconds) return;

    _active = null;
    _activeSince = null;
    _upSince = null;
    onStop(active);
  }

  /// Pause discards without tearing anything down; the hook stays installed.
  void pause() => _paused = true;

  void resume() => _paused = false;

  /// Leaving with the key held must FINISH the recording, never abandon it.
  void shutdown() {
    _shuttingDown = true;
    final active = _active;
    _active = null;
    _activeSince = null;
    _upSince = null;
    if (active != null) onStop(active);
  }

  /// Names the action a key already answers to, so the settings screen can say it.
  String? conflictFor(String key, {String? ignoreAction}) {
    for (final binding in _bindings) {
      if (binding.key == key && binding.action != ignoreAction) return binding.action;
    }
    return null;
  }

  Future<void> dispose() async {
    await _downSub?.cancel();
    await _tickSub?.cancel();
    for (final sub in _subs.values) {
      await sub.cancel();
    }
  }
}
