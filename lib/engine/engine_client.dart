import 'dart:async';

import 'package:flutter/foundation.dart';

import '../core/logbook.dart';
import '../l10n/app_strings.dart';
import 'engine_protocol.dart';
import 'native_engine.dart';

/// Runs whisper.cpp/miniaudio fully in-process, covering every EngineProtocol event and command.
class EngineClient {
  EngineClient({Logbook? log, String Function()? localeCode})
      : _log = log ?? Logbook('engine'),
        _engine = NativeEngine(log: log, localeCode: localeCode),
        _localeCode = localeCode;

  final Logbook _log;
  final NativeEngine _engine;

  /// The user's chosen UI language, read live so a later change in Settings applies at once.
  final String Function()? _localeCode;

  StreamSubscription<EngineEvent>? _sub;
  final StreamController<EngineEvent> _events =
      StreamController<EngineEvent>.broadcast();
  final StreamController<void> _exits = StreamController<void>.broadcast();

  Stream<EngineEvent> get events => _events.stream;
  Stream<void> get onExit => _exits.stream;

  bool _isAlive = false;
  bool get isAlive => _isAlive;

  Future<String?> start() async {
    // In-process engine never really left; a supervisor retry has to be able to see it is ready.
    if (_isAlive) {
      _events.add(const EngineReadyEvent());
      return null;
    }

    try {
      _engine.onWorkerDied = (reason) {
        _log('motor degradado: $reason');
        _exits.add(null);
      };
      _sub = _engine.events.listen(
        (event) => _events.add(event),
        onError: (Object e) => _log('erro nos eventos do motor nativo: $e'),
      );
      await _engine.init();
      _isAlive = true;
      _log('motor nativo pronto');
      return null;
    } catch (e) {
      _log('falha ao iniciar motor nativo: $e');
      _isAlive = false;
      return stringsFor(_localeCode?.call()).errEngineStartFailed('$e');
    }
  }

  @visibleForTesting
  void debugInject(EngineEvent event) => _events.add(event);

  bool send(EngineCommand command) {
    if (!_isAlive) {
      _log('comando ${command.name} descartado: motor nativo nao inicializado');
      return false;
    }
    unawaited(_engine.handleCommand(command));
    return true;
  }

  Future<void> shutdown({Duration grace = const Duration(seconds: 5)}) async {
    if (!_isAlive) return;
    _isAlive = false;
    await _engine.shutdown();
    await _sub?.cancel();
    _sub = null;
  }

  Future<void> dispose() async {
    await shutdown();
    await _events.close();
    await _exits.close();
    await _log.close();
  }
}
