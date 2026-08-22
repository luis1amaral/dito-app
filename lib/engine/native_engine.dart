import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dito_whisper/dito_whisper.dart';

import '../config/paths.dart';
import '../core/logbook.dart';
import '../l10n/app_strings.dart';
import 'engine_protocol.dart';
import 'gpu_pack_manager.dart';
import 'model_manager.dart';
import 'silence_alarm.dart';
import 'whisper_worker.dart';

/// In-process native engine powered by whisper.cpp and native audio capture.
/// Completely eliminates the Python backend.
class NativeEngine {
  NativeEngine({Logbook? log, this.localeCode})
      : _log = log ?? Logbook('native_engine'),
        _models = ModelManager(),
        _gpuPack = GpuPackManager();

  final Logbook _log;
  final ModelManager _models;
  final GpuPackManager _gpuPack;

  /// The user's chosen UI language, read live so a later change in Settings applies at once.
  final String Function()? localeCode;

  final StreamController<EngineEvent> _events =
      StreamController<EngineEvent>.broadcast();

  Stream<EngineEvent> get events => _events.stream;

  /// The transcription isolate died; the supervisor decides what to tell the user.
  void Function(String reason)? onWorkerDied;

  WhisperWorker? _worker;
  bool _modelLoaded = false;
  String _loadedModelName = '';
  Future<void>? _loadFuture;
  /// Every stop still writing its session: two overlapping recordings must both be waited on.
  final Set<Future<void>> _stopsInFlight = <Future<void>>{};
  bool _isRecording = false;
  String _currentMode = 'dictation';
  String _currentSessionId = '';
  String _currentFolder = '';
  String _currentStem = '';
  /// Empty means no WAV is written; only DITO_SALVAR_WAV=1 fills it (CHANGELOG 1.6.4).
  String _currentWavPath = '';
  String _currentLanguage = 'pt';
  String _currentModel = 'small';
  String _currentDevice = 'default';
  DateTime? _recordingStarted;
  Timer? _levelTimer;
  double _peakSeen = 0;
  double _rmsSum = 0;
  int _rmsTicks = 0;
  final SilenceAlarm _alarm = SilenceAlarm();

  bool get isRecording => _isRecording;
  String get loadedModel => _loadedModelName;

  /// Debug valve: the WAV is off by default because it was 99,9% of the library on disk.
  static bool get savesWav =>
      (Platform.environment['DITO_SALVAR_WAV'] ?? '').trim() == '1';

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
          :final devicePref,
          :final folder
        ):
        await _handleStart(
          mode: mode,
          model: model,
          language: language,
          device: device,
          devicePref: devicePref,
          folder: folder,
        );
      case StopCommand():
        // Tracked so shutdown() can wait for it: EngineClient dispatches commands
        // unawaited, so a quit right after stop could otherwise race the transcription.
        final stopping = _handleStop();
        _stopsInFlight.add(stopping);
        try {
          await stopping;
        } finally {
          _stopsInFlight.remove(stopping);
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
    if (_worker?.isDead ?? false) {
      _log('worker anterior morreu: subindo outro');
      _worker = null;
      _modelLoaded = false;
    }
    final worker = _worker ??= (await WhisperWorker.spawn())..onDied = _onWorkerDied;
    _modelLoaded = await worker.loadModel(path, useGpu: true, gpuDir: gpuDir);
    if (!_modelLoaded) {
      throw StateError('Falha ao inicializar o modelo GGML em $path');
    }
    _loadedModelName = model;
    _log('modelo $model pronto para uso');
  }

  /// The model handle died with the isolate; the next start has to load it again.
  void _onWorkerDied(String reason) {
    _log('worker do whisper caiu: $reason');
    _modelLoaded = false;
    _loadedModelName = '';
    onWorkerDied?.call(reason);
  }

  Future<void> _handleStart({
    required String mode,
    required String model,
    required String language,
    required String device,
    required String devicePref,
    String folder = '',
  }) async {
    if (_isRecording) {
      _log('start ignorado: gravacao ja em andamento');
      return;
    }

    _currentMode = mode;
    _currentLanguage = language.isNotEmpty ? language : 'pt';
    _currentModel = model.isNotEmpty ? model : 'small';
    _currentDevice = device;
    _alarm.reset();

    try {
      // Ensure model is ready (downloads on-demand if not already present)
      await _ensureModelLoaded(_currentModel);
    } catch (e) {
      _log('falha ao preparar modelo: $e');
      _emit(FailedEvent(
        sessionId: '',
        reason: stringsFor(localeCode?.call()).errModelLoadFailed('$e'),
      ));
      return;
    }

    // The folder must exist before capture starts: the session JSON lands there when it stops.
    final now = DateTime.now();
    final y = now.year.toString();
    final m = now.month.toString().padLeft(2, '0');
    final d = now.day.toString().padLeft(2, '0');
    final hh = now.hour.toString().padLeft(2, '0');
    final mm = now.minute.toString().padLeft(2, '0');
    final ss = now.second.toString().padLeft(2, '0');

    final sep = Platform.pathSeparator;
    final root = folder.isEmpty ? DitoPaths.defaultLibrary : folder;
    _currentFolder = '$root$sep$y$sep$m$sep$d';
    _currentStem = '$hh-$mm-$ss';
    _currentSessionId = '$y-$m-${d}_$_currentStem';
    _currentWavPath =
        savesWav ? '$_currentFolder$sep$_currentStem${DitoPaths.audioSuffix}' : '';

    Directory(_currentFolder).createSync(recursive: true);

    final res = DitoWhisper.startCapture(
      deviceName: (device.isNotEmpty && device != 'default') ? device : null,
      wavPath: _currentWavPath,
    );
    if (res < 0) {
      _log('falha ao iniciar captura de audio: codigo $res');
      _emit(FailedEvent(
        sessionId: '',
        reason: stringsFor(localeCode?.call()).errMicUnavailable,
      ));
      return;
    }

    _recordingStarted = now;
    _isRecording = true;

    _emit(StartedEvent(
      sessionId: _currentSessionId,
      mode: _currentMode,
      deviceName: device.isNotEmpty ? device : 'Microfone Padrão',
    ));

    // Start 20Hz level polling
    _alarm.reset();
    _peakSeen = 0;
    _rmsSum = 0;
    _rmsTicks = 0;
    _levelTimer?.cancel();
    _levelTimer = Timer.periodic(const Duration(milliseconds: 50), (_) {
      if (!_isRecording) return;
      final lvl = DitoWhisper.getLevel();
      // O nivel medido e a unica prova de que o microfone entregou voz; ver CHANGELOG 2026-08-21.
      if (lvl.peak > _peakSeen) _peakSeen = lvl.peak;
      _rmsSum += lvl.rms;
      _rmsTicks++;
      _emit(LevelEvent(
        peak: lvl.peak,
        rms: lvl.rms,
        seconds: lvl.seconds,
      ));
      final next = _alarm.update(rms: lvl.rms, bufferedSeconds: lvl.seconds);
      // Reason stays null so the localized AppStrings label is used (hud_pill._detailFor).
      if (next != null) _emit(AlarmEvent(state: next, reason: null));
    });
  }

  /// Quanto amplificar para o Whisper ouvir: 1 quando o sinal ja esta bom ou quando so ha ruido.
  static double gainFor(List<double> samples, {double target = 0.35, double maxGain = 20}) {
    var peak = 0.0;
    for (final s in samples) {
      final a = s.abs();
      if (a > peak) peak = a;
    }
    // Piso de ruido nao vira voz por multiplicacao: amplificar isso so gera alucinacao no Whisper.
    if (peak <= SilenceAlarm.audibleRms || peak >= target) return 1;
    final ganho = target / peak;
    return ganho > maxGain ? maxGain : ganho;
  }

  /// Whisper answers silence with invented sound tags like "[Musica]"; that is not speech.
  static String dropSoundTags(String text) {
    final speech = text
        .replaceAll(RegExp(r'\[[^\]]*\]'), ' ')
        .replaceAll(RegExp(r'\([^)]*\)'), ' ')
        .replaceAll(RegExp(r'\*[^*]*\*'), ' ')
        .replaceAll(RegExp('[\u266A\u266B]'), ' ')
        .trim();
    return speech.isEmpty ? '' : text.trim();
  }

  Future<void> _handleStop() async {
    if (!_isRecording) return;
    _isRecording = false;
    _levelTimer?.cancel();
    _levelTimer = null;

    // Snapshot before the first await: a new recording may start while this one transcribes,
    // and it overwrites every _current* field with its own session.
    final sessionId = _currentSessionId;
    final mode = _currentMode;
    final folder = _currentFolder;
    final stem = _currentStem;
    final wavPath = _currentWavPath;
    final language = _currentLanguage;
    final device = _currentDevice;
    final model = _currentModel;
    final startedAt = _recordingStarted;
    final heardAudio = _alarm.heardAudio;

    _emit(const PhaseEvent(phase: EnginePhase.transcribing));

    final samples = DitoWhisper.stopCapture();
    final seconds = samples.length / 16000.0;

    final rmsMedio = _rmsTicks > 0 ? _rmsSum / _rmsTicks : 0.0;
    final ouviuVoz = _peakSeen > SilenceAlarm.audibleRms;
    _log('captura finalizada: ${samples.length} amostras (${seconds.toStringAsFixed(2)}s), '
        'rms medio=${rmsMedio.toStringAsFixed(4)} pico=${_peakSeen.toStringAsFixed(4)} '
        'ouviu voz=$ouviuVoz');
    if (!ouviuVoz && seconds > 1) {
      _log('ATENCAO: o microfone entregou so ruido de fundo nesta gravacao inteira');
    }

    // No fallback save here: with the WAV off, it would write the whole file on every stop.
    if (wavPath.isNotEmpty) _log('WAV de depuracao em $wavPath');

    String text = '';
    if (samples.isNotEmpty && _modelLoaded && _worker != null) {
      // O headset entrega fala ate 30x mais fraca em alguns momentos (medido: rms 0.0003 contra
      // 0.0091 na mesma voz). O WAV em disco fica intacto; so o que vai ao Whisper e normalizado.
      final ganho = gainFor(samples);
      if (ganho > 1) {
        _log('sinal fraco: aplicando ganho de ${ganho.toStringAsFixed(1)}x para transcrever');
        for (var i = 0; i < samples.length; i++) {
          samples[i] = (samples[i] * ganho).clamp(-1.0, 1.0);
        }
      }
      try {
        text = await _worker!.transcribe(samples, language: language);
      } catch (e) {
        _log('erro na transcricao whisper: $e');
      }
    }

    text = dropSoundTags(text);
    _log('transcricao concluida: "$text"');

    // Write session JSON metadata
    final sep = Platform.pathSeparator;
    final metaPath =
        '$folder$sep$stem${DitoPaths.sessionSuffix}';
    try {
      final meta = {
        'id': sessionId,
        'mode': mode,
        'state': 'done',
        'started': startedAt?.toIso8601String() ??
            DateTime.now().toIso8601String(),
        'seconds': double.parse(seconds.toStringAsFixed(2)),
        'device': device,
        'model': model,
        'text': text,
        'error': null,
      };
      File(metaPath).writeAsStringSync(const JsonEncoder.withIndent('  ').convert(meta));
    } catch (e) {
      _log('erro ao salvar meta JSON: $e');
    }

    _emit(FinishedEvent(
      sessionId: sessionId,
      mode: mode,
      text: text,
      seconds: seconds,
      folder: folder,
      everHeardAudio: heardAudio,
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
    // Let every stop already writing its transcript/session finish before freeing the model.
    await Future.wait(_stopsInFlight.toList());
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
