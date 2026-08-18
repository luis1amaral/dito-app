import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../core/logbook.dart';
import 'engine_protocol.dart';

/// Where to look for dito-engine.exe, in order; never a developer machine path.
List<String> defaultEngineCandidates() {
  final exeDir = File(Platform.resolvedExecutable).parent.path;
  return <String>[
    '$exeDir\\dito-engine\\dito-engine.exe',
    '$exeDir\\engine\\dito-engine.exe',
    if (Platform.environment['DITO_ENGINE'] case final String p when p.isNotEmpty) p,
  ];
}

/// Speaks JSON-lines to the engine process; it decides nothing, it only carries.
class EngineClient {
  EngineClient({List<String>? candidates, Logbook? log})
      : _candidates = candidates ?? defaultEngineCandidates(),
        _log = log ?? Logbook('engine');

  final List<String> _candidates;
  final Logbook _log;

  Process? _process;
  StreamSubscription<String>? _stdout;
  StreamSubscription<String>? _stderr;

  final StreamController<EngineEvent> _events = StreamController<EngineEvent>.broadcast();
  final StreamController<void> _exits = StreamController<void>.broadcast();

  Stream<EngineEvent> get events => _events.stream;

  /// Fires whenever the process dies, for any reason.
  Stream<void> get onExit => _exits.stream;

  bool get isAlive => _process != null;

  String? get executablePath => _executable;
  String? _executable;

  /// Starts the process, returning the error as text instead of throwing.
  Future<String?> start() async {
    if (_process != null) return null;

    final path = _candidates.firstWhere(
      (c) => File(c).existsSync(),
      orElse: () => '',
    );
    if (path.isEmpty) {
      final tried = _candidates.join(', ');
      _log('motor nao encontrado; procurei em: $tried');
      return 'nao encontrei o dito-engine.exe';
    }

    try {
      _executable = path;
      final process = await Process.start(
        path,
        <String>['engine'],
        workingDirectory: File(path).parent.path,
      );
      _process = process;
      _log('motor iniciado: $path (pid ${process.pid})');

      // allowMalformed, or one Windows device name in the OEM code page kills the whole stream.
      const decoder = Utf8Decoder(allowMalformed: true);

      _stdout = process.stdout
          .transform(decoder)
          .transform(const LineSplitter())
          .listen(_onLine,
              onError: (Object e) => _log('erro no stdout: $e'), cancelOnError: false);

      _stderr = process.stderr
          .transform(decoder)
          .transform(const LineSplitter())
          .listen((line) => _log('[motor] $line'),
              onError: (Object e) => _log('erro no stderr: $e'), cancelOnError: false);

      unawaited(process.exitCode.then(_onExit));
      return null;
    } catch (e) {
      _log('falha ao iniciar o motor: $e');
      _process = null;
      return 'falha ao iniciar o motor: $e';
    }
  }

  /// Feeds an event as if the engine had sent it; tests drive the controller through this.
  @visibleForTesting
  void debugInject(EngineEvent event) => _events.add(event);

  void _onLine(String line) {
    final trimmed = line.trim();
    if (trimmed.isEmpty) return;
    try {
      final decoded = jsonDecode(trimmed);
      if (decoded is! Map) {
        _log('linha ignorada (nao e objeto): $trimmed');
        return;
      }
      _events.add(EngineEvent.parse(Map<String, dynamic>.from(decoded)));
    } catch (e) {
      _log('JSON invalido do motor: $trimmed');
    }
  }

  void _onExit(int code) {
    _log('motor encerrou com codigo $code');
    _process = null;
    _stdout?.cancel();
    _stderr?.cancel();
    _stdout = null;
    _stderr = null;
    if (!_exits.isClosed) _exits.add(null);
  }

  /// Returns false when no process was there to receive it: the caller must know.
  bool send(EngineCommand command) {
    final process = _process;
    if (process == null) {
      _log('comando ${command.name} descartado: motor nao esta rodando');
      return false;
    }
    try {
      process.stdin.writeln(jsonEncode(command.toJson()));
      // Without the flush the line can sit in the sink buffer and the engine never reads it.
      unawaited(process.stdin.flush().catchError((Object e) {
        _log('falha ao esvaziar o stdin apos ${command.name}: $e');
      }));
      return true;
    } catch (e) {
      _log('falha ao enviar ${command.name}: $e');
      return false;
    }
  }

  /// Asks to quit and waits: the engine finishes the recording on a daemon thread.
  Future<void> shutdown({Duration grace = const Duration(seconds: 30)}) async {
    final process = _process;
    if (process == null) return;
    send(const QuitCommand());
    try {
      await process.exitCode.timeout(grace);
    } on TimeoutException {
      _log('motor nao saiu em ${grace.inSeconds}s; encerrando a forca');
      process.kill();
    }
    _process = null;
  }

  Future<void> dispose() async {
    await shutdown(grace: const Duration(seconds: 5));
    await _events.close();
    await _exits.close();
    await _log.close();
  }
}
