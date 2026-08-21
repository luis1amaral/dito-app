import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dito_whisper/dito_whisper.dart';

import '../config/paths.dart';
import '../core/logbook.dart';
import 'engine_protocol.dart';
import 'gpu_pack_manager.dart';
import 'model_manager.dart';
import 'whisper_worker.dart';

/// In-process native engine powered by whisper.cpp and native audio capture.
/// Completely eliminates the Python backend.
class NativeEngine {
  NativeEngine({Logbook? log})
      : _log = log ?? Logbook('native_engine'),
        _models = ModelManager(),
        _gpuPack = GpuPackManager();

  final Logbook _log;
  final ModelManager _models;
  final GpuPackManager _gpuPack;

  final StreamController<EngineEvent> _events =
      StreamController<EngineEvent>.broadcast();

  Stream<EngineEvent> get events => _events.stream;

  WhisperWorker? _worker;
  bool _modelLoaded = false;
  String _loadedModelName = '';
  Future<void>? _loadFuture;
  Future<void>? _stopInFlight;
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
  int _silenceMs = 0;
  AudioState _alarmState = AudioState.ok;

  // Same rms floor as _everHeardAudio, so "audible" means one thing everywhere.
  static const double _audibleRms = 0.008;
  static const double _deadRms = 0.001;
  // Mirrors AlertConfig.deadMs/quietMs defaults (lib/config/config_model.dart); wire live config
  // here if a settings screen ever exposes them.
  static const int _deadMs = 700;
  static const int _quietMs = 2500;

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
        // Tracked so shutdown() can wait for it: EngineClient dispatches commands
        // unawaited, so a quit right after stop could otherwise race the transcription.
        final stopping = _handleStop();
        _stopInFlight = stopping;
        try {
          await stopping;
        } finally {
          _stopInFlight = null;
        }
      case StatusCommand():
        _handleStatus();
      case ListDevicesCommand():
        _handleListDevices();
      case QuitCommand():
        await shutdown();
    }
  }

  Future<void> _ensureModelLoaded(String model) async {
    if (_modelLoaded && _loadedModelName == model) {
      return;
    }

    if (_loadFuture != null) {
      await _loadFuture;
      if (_modelLoaded && _loadedModelName == model) {
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
    _modelLoaded = false;
    _loadedModelName = '';

    _log('carregando modelo $model...');
    final path = await _models.ensureModel(model);
    // Never await the GPU pack here: a ~130MB download must not delay the user hitting record.
    // The postinst script already fetches it during `apt install`; this is only the fallback
    // for a GPU plugged in after install, and it happens quietly in the background.
    final gpuDir = GpuPackManager.isDownloaded() ? GpuPackManager.gpuDir : null;
    if (gpuDir == null) unawaited(_gpuPack.ensureGpuPack());
    // Load and transcribe always run on this same worker isolate: CUDA's context is thread-bound.
    final worker = _worker ??= await WhisperWorker.spawn();
    _modelLoaded = await worker.loadModel(path, useGpu: true, gpuDir: gpuDir);
    if (!_modelLoaded) {
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

    final sep = Platform.pathSeparator;
    _currentFolder = '${DitoPaths.defaultLibrary}$sep$y$sep$m$sep$d';
    _currentStem = '$hh-$mm-$ss';
    _currentSessionId = '$y-$m-${d}_$_currentStem';
    _currentWavPath = '$_currentFolder$sep$_currentStem${DitoPaths.audioSuffix}';

    Directory(_currentFolder).createSync(recursive: true);

    _emit(StartedEvent(
      sessionId: _currentSessionId,
      mode: _currentMode,
      deviceName: device.isNotEmpty ? device : 'Microfone Padrão',
    ));

    // Start 20Hz level polling
    _silenceMs = 0;
    _alarmState = AudioState.ok;
    _levelTimer?.cancel();
    _levelTimer = Timer.periodic(const Duration(milliseconds: 50), (_) {
      if (!_isRecording) return;
      final lvl = DitoWhisper.getLevel();
      if (lvl.rms > _audibleRms) {
        _everHeardAudio = true;
      }
      _emit(LevelEvent(
        peak: lvl.peak,
        rms: lvl.rms,
        seconds: lvl.seconds,
      ));
      _checkAlarm(lvl.rms, lvl.seconds);
    });
  }

  /// Turns raw rms into the dead/quiet/ok alarm the HUD and the sound/notify guarantee react to.
  /// Emits only on the edge (state actually changing), never every 50ms tick while it holds.
  void _checkAlarm(double rms, double bufferedSeconds) {
    // No real audio buffered yet (device still waking up, e.g. WirePlumber suspend) -> not silence.
    if (bufferedSeconds <= 0.05) return;

    if (rms > _audibleRms) {
      _silenceMs = 0;
      _setAlarmState(AudioState.ok, null);
      return;
    }

    _silenceMs += 50;
    // No reason text here: dito_controller/hud_pill already fall back to the localized
    // AppStrings label (hudNoAudio/notifyNoAudio) when reason is null; a hardcoded string
    // here would override that fallback and break translation for every other language.
    if (rms <= _deadRms && _silenceMs >= _deadMs) {
      _setAlarmState(AudioState.dead, null);
    } else if (_silenceMs >= _quietMs) {
      _setAlarmState(AudioState.quiet, null);
    }
  }

  void _setAlarmState(AudioState next, String? reason) {
    if (next == _alarmState) return;
    _alarmState = next;
    _emit(AlarmEvent(state: next, reason: reason));
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
    if (samples.isNotEmpty && _modelLoaded && _worker != null) {
      try {
        text = await _worker!.transcribe(samples, language: _currentLanguage);
      } catch (e) {
        _log('erro na transcricao whisper: $e');
      }
    }

    text = text.trim();
    _log('transcricao concluida: "$text"');

    // Write session JSON metadata
    final sep = Platform.pathSeparator;
    final metaPath =
        '$_currentFolder$sep$_currentStem${DitoPaths.sessionSuffix}';
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
      backend: 'whisper.cpp (${DitoWhisper.backendName})',
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
    // Let a stop already writing the transcript/session finish before freeing the model.
    await _stopInFlight;
    if (_isRecording) {
      DitoWhisper.stopCapture();
      _isRecording = false;
    }
    if (_modelLoaded) {
      await _worker?.freeModel();
      _modelLoaded = false;
      _loadedModelName = '';
    }
  }

  Future<void> dispose() async {
    await shutdown();
    _worker?.dispose();
    await _events.close();
  }
}
