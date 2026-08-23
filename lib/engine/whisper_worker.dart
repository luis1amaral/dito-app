import 'dart:async';
import 'dart:ffi';
import 'dart:isolate';

import 'package:dito_whisper/dito_whisper.dart';

class _LoadModel {
  const _LoadModel(this.path, this.useGpu, this.gpuDir);
  final String path;
  final bool useGpu;
  final String? gpuDir;
}

class _Transcribe {
  const _Transcribe(this.samples, this.language);
  final List<double> samples;
  final String language;
}

class _FreeModel {
  const _FreeModel();
}

class _WorkerError {
  const _WorkerError(this.message);
  final String message;
}

/// Owns whisper.cpp's model handle and every blocking FFI call on its own isolate; CUDA's context is thread-bound, so load and transcribe always run here.
class WhisperWorker {
  WhisperWorker._(this._commands, this._isolate);

  final SendPort _commands;
  final Isolate _isolate;
  final Set<ReceivePort> _pending = {};
  ReceivePort? _exits;
  ReceivePort? _errors;
  bool _dead = false;

  /// A native crash used to hang every future transcription; now it fails loud and once.
  void Function(String reason)? onDied;

  bool get isDead => _dead;

  static Future<WhisperWorker> spawn() async {
    final ready = ReceivePort();
    final exits = ReceivePort();
    final errors = ReceivePort();
    final isolate = await Isolate.spawn(
      _main,
      ready.sendPort,
      debugName: 'whisper_worker',
      onExit: exits.sendPort,
      onError: errors.sendPort,
    );
    final commands = await ready.first as SendPort;
    ready.close();
    final worker = WhisperWorker._(commands, isolate);
    worker._exits = exits;
    worker._errors = errors;
    exits.listen((_) => worker._onDeath('o isolate do whisper morreu'));
    errors.listen((e) => worker._onDeath('erro no isolate do whisper: $e'));
    return worker;
  }

  /// Frees every caller waiting on a reply that will never come.
  void _onDeath(String reason) {
    if (_dead) return;
    _dead = true;
    for (final port in _pending) {
      port.close();
    }
    _pending.clear();
    onDied?.call(reason);
  }

  Future<Object?> _call(Object? request) async {
    if (_dead) throw StateError('whisper worker morto');
    final reply = ReceivePort();
    _pending.add(reply);
    try {
      _commands.send([reply.sendPort, request]);
      // dispose() closing this port while it awaits makes `first` throw, not hang forever.
      final result = await reply.first;
      if (result is _WorkerError) throw StateError(result.message);
      return result;
    } finally {
      _pending.remove(reply);
      reply.close();
    }
  }

  Future<bool> loadModel(String path, {required bool useGpu, String? gpuDir}) async =>
      await _call(_LoadModel(path, useGpu, gpuDir)) == true;

  Future<String> transcribe(List<double> samples, {required String language}) async {
    final result = await _call(_Transcribe(samples, language));
    return result is String ? result : '';
  }

  Future<void> freeModel() => _call(const _FreeModel());

  void dispose() {
    // Closing each port fails any in-flight _call with a StateError instead of hanging forever.
    _dead = true;
    for (final port in _pending) {
      port.close();
    }
    _pending.clear();
    _exits?.close();
    _errors?.close();
    _isolate.kill(priority: Isolate.immediate);
  }

  static void _main(SendPort readyPort) {
    final commands = ReceivePort();
    readyPort.send(commands.sendPort);

    var handle = nullptr.cast<Void>();
    commands.listen((message) {
      final parts = message as List<Object?>;
      final reply = parts[0] as SendPort;
      final request = parts[1];
      try {
        if (request is _LoadModel) {
          if (handle != nullptr) {
            DitoWhisper.freeModel(handle);
            handle = nullptr;
          }
          if (request.gpuDir != null) DitoWhisper.setBackendDir(request.gpuDir!);
          handle = DitoWhisper.loadModel(request.path, useGpu: request.useGpu);
          reply.send(handle != nullptr);
        } else if (request is _Transcribe) {
          reply.send(handle == nullptr
              ? ''
              : DitoWhisper.transcribe(handle, request.samples, language: request.language));
        } else if (request is _FreeModel) {
          if (handle != nullptr) {
            DitoWhisper.freeModel(handle);
            handle = nullptr;
          }
          reply.send(true);
        } else {
          reply.send(null);
        }
      } catch (e) {
        reply.send(_WorkerError(e.toString()));
      }
    });
  }
}
