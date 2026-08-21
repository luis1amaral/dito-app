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

/// Owns whisper.cpp's model handle and every blocking FFI call (load, CUDA inference) on
/// its own isolate/thread, so the UI isolate never freezes during transcription. CUDA
/// context is thread-bound: load and transcribe must always run on this same isolate.
class WhisperWorker {
  WhisperWorker._(this._commands, this._isolate);

  final SendPort _commands;
  final Isolate _isolate;
  final Set<ReceivePort> _pending = {};

  static Future<WhisperWorker> spawn() async {
    final ready = ReceivePort();
    final isolate = await Isolate.spawn(_main, ready.sendPort, debugName: 'whisper_worker');
    final commands = await ready.first as SendPort;
    return WhisperWorker._(commands, isolate);
  }

  Future<Object?> _call(Object? request) async {
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
    for (final port in _pending) {
      port.close();
    }
    _pending.clear();
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
