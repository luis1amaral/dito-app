import 'dart:async';

import 'package:flutter/foundation.dart';

import '../core/logbook.dart';
import '../l10n/app_strings.dart';
import 'engine_client.dart';
import 'engine_health.dart';
import 'engine_protocol.dart';

/// Keeps the engine alive and reports what happened to it.
class EngineSupervisor extends ChangeNotifier {
  EngineSupervisor({required this.client, Logbook? log, this.localeCode})
      : _log = log ?? Logbook('supervisor') {
    _events = client.events.listen(_onEvent);
    _exits = client.onExit.listen((_) => _onDeath());
  }

  final EngineClient client;
  final Logbook _log;

  /// The user's chosen UI language, read live so a later change in Settings applies at once.
  final String Function()? localeCode;

  static const List<Duration> _backoff = <Duration>[
    Duration(milliseconds: 500),
    Duration(seconds: 1),
    Duration(seconds: 2),
    Duration(seconds: 5),
  ];

  StreamSubscription<EngineEvent>? _events;
  StreamSubscription<void>? _exits;
  Timer? _retry;
  int _attempt = 0;
  bool _stopping = false;

  EngineHealth _health = const EngineHealth(state: EngineState.starting);
  EngineHealth get health => _health;

  /// True while a recording runs, so the supervisor knows how bad a death is.
  bool wasRecording = false;

  /// Called when the engine dies mid-recording: the audio is safe, the text is not.
  void Function(String reason)? onDiedRecording;

  Future<void> start() async {
    _stopping = false;
    _set(_health.copyWith(state: EngineState.starting, clearReason: true));
    final error = await client.start();
    if (error != null) {
      _set(_health.copyWith(state: EngineState.dead, reason: error));
      _scheduleRetry();
    }
  }

  void _onEvent(EngineEvent event) {
    switch (event) {
      case EngineReadyEvent():
        _attempt = 0;
        _set(_health.copyWith(state: EngineState.ready, clearReason: true));
      case StatusEvent(:final model, :final backend):
        _set(_health.copyWith(
          state: _health.state == EngineState.starting ? EngineState.ready : _health.state,
          model: model,
          backend: backend,
        ));
      default:
        break;
    }
  }

  void _onDeath() {
    if (_stopping) return;
    final wasMidRecording = wasRecording;
    wasRecording = false;
    final s = stringsFor(localeCode?.call());
    final reason = wasMidRecording ? s.errEngineDiedRecording : s.errEngineDiedIdle;
    _log('morte do motor (gravando=$wasMidRecording)');
    _set(_health.copyWith(
      state: EngineState.dead,
      reason: reason,
      restarts: _health.restarts + 1,
    ));
    if (wasMidRecording) onDiedRecording?.call(reason);
    _scheduleRetry();
  }

  void _scheduleRetry() {
    if (_stopping) return;
    _retry?.cancel();
    final wait = _backoff[_attempt.clamp(0, _backoff.length - 1)];
    _attempt++;
    _log('religando em ${wait.inMilliseconds}ms (tentativa $_attempt)');
    _retry = Timer(wait, () async {
      if (_stopping) return;
      final error = await client.start();
      if (error != null) {
        _set(_health.copyWith(state: EngineState.dead, reason: error));
        _scheduleRetry();
      }
    });
  }

  void markDegraded(String reason) {
    if (_health.state == EngineState.dead) return;
    _set(_health.copyWith(state: EngineState.degraded, reason: reason));
  }

  void markHealthy() {
    if (_health.state != EngineState.degraded) return;
    _set(_health.copyWith(state: EngineState.ready, clearReason: true));
  }

  void _set(EngineHealth next) {
    if (next == _health) return;
    _health = next;
    notifyListeners();
  }

  Future<void> stop() async {
    _stopping = true;
    _retry?.cancel();
    await client.shutdown();
  }

  @override
  void dispose() {
    _stopping = true;
    _retry?.cancel();
    _events?.cancel();
    _exits?.cancel();
    _log.close();
    super.dispose();
  }
}
