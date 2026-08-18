import 'dart:async';

import 'package:flutter/foundation.dart';

import '../core/logbook.dart';
import 'engine_protocol.dart';
import 'native_engine.dart';

/// EngineClient providing complete in-process native execution via whisper.cpp & miniaudio.
/// Implements 100% of the EngineProtocol events and commands without external Python processes.
class EngineClient {
  EngineClient({List<String>? candidates, Logbook? log})
      : _log = log ?? Logbook('engine'),
        _engine = NativeEngine(log: log);

  final Logbook _log;
  final NativeEngine _engine;

  StreamSubscription<EngineEvent>? _sub;
  final StreamController<EngineEvent> _events =
      StreamController<EngineEvent>.broadcast();
  final StreamController<void> _exits = StreamController<void>.broadcast();

  Stream<EngineEvent> get events => _events.stream;
  Stream<void> get onExit => _exits.stream;

  bool _isAlive = false;
  bool get isAlive => _isAlive;

  String? get executablePath => 'native (in-process whisper.cpp)';

  Future<String?> start() async {
    if (_isAlive) return null;

    try {
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
      return 'falha ao iniciar motor nativo: $e';
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
