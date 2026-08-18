import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:dito_whisper/dito_whisper.dart';

import '../config/paths.dart';
import '../core/logbook.dart';
import 'engine_protocol.dart';
import 'model_manager.dart';

/// In-process native engine powered by whisper.cpp and native audio capture.
/// Completely eliminates the Python backend.
class NativeEngine {
  NativeEngine({Logbook? log})
      : _log = log ?? Logbook('native_engine'),
        _models = ModelManager();

  final Logbook _log;
  final ModelManager _models;

  final StreamController<EngineEvent> _events =
      StreamController<EngineEvent>.broadcast();

  Stream<EngineEvent> get events => _events.stream;

  Pointer<Void> _modelHandle = nullptr;
  String _loadedModelName = '';
  Future<void>? _loadFuture;
  bool _isRecording = false;
  String _currentMode = 'dictation';
  String _currentSessionId = '';
  String _currentFolder = '';
  String _currentStem = '';
  String _currentWavPath = '';
  String _currentLanguage = 'pt';
  String _currentModel = 'small';
  String _currentDevice = 'default';
  DateTime? _recordingStarted;
  Timer? _levelTimer;
  bool _everHeardAudio = false;

  bool get isRecording => _isRecording;
  String get loadedModel => _loadedModelName;

  Future<void> init() async {
    _log('iniciando motor nativo C++ (whisper.cpp ${DitoWhisper.version})');
    _emit(const EngineReadyEvent());
    _handleStatus();
  }

  void _emit(EngineEvent event) {
    if (!_events.isClosed) {
      _events.add(event);
    }
  }

  Future<void> handleCommand(EngineCommand cmd) async {
    switch (cmd) {
      case StartCommand(
          :final mode,
          :final model,
          :final language,
          :final device,
          :final devicePref
        ):
        await _handleStart(
          mode: mode,
          model: model,
          language: language,
          device: device,
          devicePref: devicePref,
        );
      case StopCommand():
        await _handleStop();
      case StatusCommand():
        _handleStatus();
      case ListDevicesCommand():
        _handleListDevices();
      case QuitCommand():
        await shutdown();
    }
  }

  Future<void> _ensureModelLoaded(String model) async {
    if (_modelHandle != nullptr && _loadedModelName == model) {
      return;
    }

    if (_loadFuture != null) {
      await _loadFuture;
      if (_modelHandle != nullptr && _loadedModelName == model) {
        return;
      }
    }

    final future = _loadModelInternal(model);
    _loadFuture = future;
    try {
      await future;
    } finally {
      _loadFuture = null;
    }
  }

  Future<void> _loadModelInternal(String model) async {
    if (_modelHandle != nullptr) {
      DitoWhisper.freeModel(_modelHandle);
      _modelHandle = nullptr;
      _loadedModelName = '';
    }

    _log('carregando modelo $model...');
    final path = await _models.ensureModel(model);
    _modelHandle = DitoWhisper.loadModel(path, useGpu: false);
    if (_modelHandle == nullptr) {
      throw StateError('Falha ao inicializar o modelo GGML em $path');
    }
    _loadedModelName = model;
    _log('modelo $model pronto para uso');
  }

  Future<void> _handleStart({
    required String mode,
    required String model,
    required String language,
    required String device,
    required String devicePref,
  }) async {
    if (_isRecording) {
      _log('start ignorado: gravacao ja em andamento');
      return;
    }

    _currentMode = mode;
    _currentLanguage = language.isNotEmpty ? language : 'pt';
    _currentModel = model.isNotEmpty ? model : 'small';
    _currentDevice = device;
    _everHeardAudio = false;

    try {
      // Ensure model is ready (downloads on-demand if not already present)
      await _ensureModelLoaded(_currentModel);
    } catch (e) {
      _log('falha ao preparar modelo: $e');
      _emit(FailedEvent(
        sessionId: '',
        reason: 'Falha ao carregar modelo: $e',
      ));
      return;
    }

    final res = DitoWhisper.startCapture(
      deviceName: (device.isNotEmpty && device != 'default') ? device : null,
    );
    if (res < 0) {
      _log('falha ao iniciar captura de audio: codigo $res');
      _emit(FailedEvent(
        sessionId: '',
        reason: 'Não foi possível acessar o microfone',
      ));
      return;
    }

    final now = DateTime.now();
    _recordingStarted = now;
    _isRecording = true;

    final y = now.year.toString();
    final m = now.month.toString().padLeft(2, '0');
    final d = now.day.toString().padLeft(2, '0');
    final hh = now.hour.toString().padLeft(2, '0');
    final mm = now.minute.toString().padLeft(2, '0');
    final ss = now.second.toString().padLeft(2, '0');

    _currentFolder = '${DitoPaths.defaultLibrary}\\$y\\$m\\$d';
    _currentStem = '$hh-$mm-$ss';
    _currentSessionId = '$y-$m-${d}_$_currentStem';
    _currentWavPath = '$_currentFolder\\$_currentStem${DitoPaths.audioSuffix}';

    Directory(_currentFolder).createSync(recursive: true);

    _emit(StartedEvent(
      sessionId: _currentSessionId,
      mode: _currentMode,
      deviceName: device.isNotEmpty ? device : 'Microfone Padrão',
    ));

    // Start 20Hz level polling
    _levelTimer?.cancel();
    _levelTimer = Timer.periodic(const Duration(milliseconds: 50), (_) {
      if (!_isRecording) return;
      final lvl = DitoWhisper.getLevel();
      if (lvl.rms > 0.008) {
        _everHeardAudio = true;
      }
      _emit(LevelEvent(
        peak: lvl.peak,
        rms: lvl.rms,
        seconds: lvl.seconds,
      ));
    });
  }

  Future<void> _handleStop() async {
    if (!_isRecording) return;
    _isRecording = false;
    _levelTimer?.cancel();
    _levelTimer = null;

    _emit(const PhaseEvent(phase: EnginePhase.transcribing));

    final samples = DitoWhisper.stopCapture();
    final seconds = samples.length / 16000.0;

    _log('captura finalizada: ${samples.length} amostras (${seconds.toStringAsFixed(2)}s)');

    // Save WAV audio file to Library folder
    if (samples.isNotEmpty) {
      try {
        DitoWhisper.saveWav(_currentWavPath, samples);
      } catch (e) {
        _log('erro ao salvar WAV: $e');
      }
    }

    String text = '';
    if (samples.isNotEmpty && _modelHandle != nullptr) {
      try {
        text = DitoWhisper.transcribe(
          _modelHandle,
          samples,
          language: _currentLanguage,
        );
      } catch (e) {
        _log('erro na transcricao whisper: $e');
      }
    }

    text = text.trim();
    _log('transcricao concluida: "$text"');

    // Write session JSON metadata
    final metaPath =
        '$_currentFolder\\$_currentStem${DitoPaths.sessionSuffix}';
    try {
      final meta = {
        'id': _currentSessionId,
        'mode': _currentMode,
        'state': 'done',
        'started': _recordingStarted?.toIso8601String() ??
            DateTime.now().toIso8601String(),
        'seconds': double.parse(seconds.toStringAsFixed(2)),
        'device': _currentDevice,
        'model': _currentModel,
        'text': text,
        'error': null,
      };
      File(metaPath).writeAsStringSync(const JsonEncoder.withIndent('  ').convert(meta));
    } catch (e) {
      _log('erro ao salvar meta JSON: $e');
    }

    _emit(FinishedEvent(
      sessionId: _currentSessionId,
      mode: _currentMode,
      text: text,
      seconds: seconds,
      folder: _currentFolder,
      everHeardAudio: _everHeardAudio,
    ));

    _emit(const PhaseEvent(phase: EnginePhase.idle));
  }

  void _handleStatus() {
    _emit(StatusEvent(
      isRecording: _isRecording,
      model: _loadedModelName.isNotEmpty ? _loadedModelName : _currentModel,
      backend: 'whisper.cpp (C++ nativo AVX2)',
    ));
  }

  void _handleListDevices() {
    final nativeDevs = DitoWhisper.listDevices();
    final items = nativeDevs
        .map((d) => DeviceItem(
              index: int.tryParse(d.id) ?? 0,
              name: d.name,
              isDefault: d.isDefault,
            ))
        .toList();
    _emit(DevicesEvent(items));
  }

  Future<void> shutdown() async {
    _levelTimer?.cancel();
    _levelTimer = null;
    if (_isRecording) {
      DitoWhisper.stopCapture();
      _isRecording = false;
    }
    if (_modelHandle != nullptr) {
      DitoWhisper.freeModel(_modelHandle);
      _modelHandle = nullptr;
      _loadedModelName = '';
    }
    await _events.close();
  }
}
