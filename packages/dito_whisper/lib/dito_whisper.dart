import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'package:ffi/ffi.dart';

typedef _InitNative = Pointer<Void> Function(Pointer<Utf8> modelPath, Int32 useGpu);
typedef _InitDart = Pointer<Void> Function(Pointer<Utf8> modelPath, int useGpu);

typedef _TranscribeNative = Int32 Function(
    Pointer<Void> handle,
    Pointer<Float> pcmData,
    Int32 nSamples,
    Pointer<Utf8> lang,
    Pointer<Utf8> outText,
    Int32 maxLen);
typedef _TranscribeDart = int Function(
    Pointer<Void> handle,
    Pointer<Float> pcmData,
    int nSamples,
    Pointer<Utf8> lang,
    Pointer<Utf8> outText,
    int maxLen);

typedef _FreeNative = Void Function(Pointer<Void> handle);
typedef _FreeDart = void Function(Pointer<Void> handle);

typedef _VersionNative = Pointer<Utf8> Function();
typedef _VersionDart = Pointer<Utf8> Function();

typedef _BackendNameNative = Pointer<Utf8> Function();
typedef _BackendNameDart = Pointer<Utf8> Function();

typedef _SetBackendDirNative = Void Function(Pointer<Utf8> dir);
typedef _SetBackendDirDart = void Function(Pointer<Utf8> dir);

typedef _ListDevicesNative = Int32 Function(Pointer<Utf8> outJson, Int32 maxLen);
typedef _ListDevicesDart = int Function(Pointer<Utf8> outJson, int maxLen);

typedef _StartCaptureNative = Int32 Function(Pointer<Utf8> deviceName);
typedef _StartCaptureDart = int Function(Pointer<Utf8> deviceName);

typedef _GetLevelNative = Int32 Function(
    Pointer<Float> outRms, Pointer<Float> outPeak, Pointer<Float> outSeconds);
typedef _GetLevelDart = int Function(
    Pointer<Float> outRms, Pointer<Float> outPeak, Pointer<Float> outSeconds);

typedef _StopCaptureNative = Int32 Function(
    Pointer<Pointer<Float>> outPcm, Pointer<Int32> outNSamples);
typedef _StopCaptureDart = int Function(
    Pointer<Pointer<Float>> outPcm, Pointer<Int32> outNSamples);

typedef _FreeSamplesNative = Void Function(Pointer<Float> pcm);
typedef _FreeSamplesDart = void Function(Pointer<Float> pcm);

typedef _SaveWavNative = Int32 Function(
    Pointer<Utf8> filePath, Pointer<Float> pcm, Int32 nSamples);
typedef _SaveWavDart = int Function(
    Pointer<Utf8> filePath, Pointer<Float> pcm, int nSamples);

class AudioDevice {
  const AudioDevice({required this.id, required this.name, required this.isDefault});
  final String id;
  final String name;
  final bool isDefault;

  factory AudioDevice.fromJson(Map<String, dynamic> j) => AudioDevice(
        id: j['id']?.toString() ?? '',
        name: j['name']?.toString() ?? '',
        isDefault: j['is_default'] == true,
      );
}

class DitoWhisper {
  DitoWhisper._();

  static DynamicLibrary? _lib;
  static _InitDart? _initFn;
  static _TranscribeDart? _transcribeFn;
  static _FreeDart? _freeFn;
  static _VersionDart? _versionFn;
  static _BackendNameDart? _backendNameFn;
  static _SetBackendDirDart? _setBackendDirFn;
  static _ListDevicesDart? _listDevicesFn;
  static _StartCaptureDart? _startCaptureFn;
  static _GetLevelDart? _getLevelFn;
  static _StopCaptureDart? _stopCaptureFn;
  static _FreeSamplesDart? _freeSamplesFn;
  static _SaveWavDart? _saveWavFn;

  static void _ensureLoaded() {
    if (_lib != null) return;
    if (Platform.isWindows) {
      _lib = DynamicLibrary.open('dito_whisper_plugin.dll');
    } else if (Platform.isLinux) {
      try {
        _lib = DynamicLibrary.open('libdito_whisper_plugin.so');
      } catch (_) {
        final candidates = [
          '${Directory.current.path}/build/linux/x64/release/bundle/lib/libdito_whisper_plugin.so',
          '/opt/dito/lib/libdito_whisper_plugin.so',
        ];
        for (final p in candidates) {
          if (File(p).existsSync()) {
            try {
              _lib = DynamicLibrary.open(p);
              break;
            } catch (_) {}
          }
        }
        _lib ??= DynamicLibrary.process();
      }
    } else {
      _lib = DynamicLibrary.process();
    }

    try {
      _initFn = _lib!.lookupFunction<_InitNative, _InitDart>('dito_whisper_init');
      _transcribeFn =
          _lib!.lookupFunction<_TranscribeNative, _TranscribeDart>('dito_whisper_transcribe');
      _freeFn = _lib!.lookupFunction<_FreeNative, _FreeDart>('dito_whisper_free');
      _versionFn =
          _lib!.lookupFunction<_VersionNative, _VersionDart>('dito_whisper_version');
      _backendNameFn = _lib!
          .lookupFunction<_BackendNameNative, _BackendNameDart>('dito_whisper_backend_name');
      _setBackendDirFn = _lib!.lookupFunction<_SetBackendDirNative, _SetBackendDirDart>(
          'dito_whisper_set_backend_dir');
      _listDevicesFn =
          _lib!.lookupFunction<_ListDevicesNative, _ListDevicesDart>('dito_audio_list_devices');
      _startCaptureFn =
          _lib!.lookupFunction<_StartCaptureNative, _StartCaptureDart>('dito_audio_start_capture');
      _getLevelFn =
          _lib!.lookupFunction<_GetLevelNative, _GetLevelDart>('dito_audio_get_level');
      _stopCaptureFn =
          _lib!.lookupFunction<_StopCaptureNative, _StopCaptureDart>('dito_audio_stop_capture');
      _freeSamplesFn =
          _lib!.lookupFunction<_FreeSamplesNative, _FreeSamplesDart>('dito_audio_free_samples');
      _saveWavFn =
          _lib!.lookupFunction<_SaveWavNative, _SaveWavDart>('dito_audio_save_wav');
    } catch (_) {}
  }

  static String get version {
    try {
      _ensureLoaded();
      final ptr = _versionFn?.call();
      return ptr != null && ptr != nullptr ? ptr.toDartString() : '1.7.4';
    } catch (_) {
      return '1.7.4';
    }
  }

  /// Real ggml backend in use ("CUDA0", "CPU", ...) — only meaningful after [loadModel].
  static String get backendName {
    try {
      _ensureLoaded();
      final ptr = _backendNameFn?.call();
      return ptr != null && ptr != nullptr ? ptr.toDartString() : 'CPU';
    } catch (_) {
      return 'CPU';
    }
  }

  /// Points the optional-backend search (e.g. a downloaded GPU pack) at [dir]; call before [loadModel].
  static void setBackendDir(String dir) {
    _ensureLoaded();
    final dirPtr = dir.toNativeUtf8();
    try {
      _setBackendDirFn?.call(dirPtr);
    } finally {
      malloc.free(dirPtr);
    }
  }

  static Pointer<Void> loadModel(String path, {bool useGpu = false}) {
    _ensureLoaded();
    if (_initFn == null) return nullptr;
    final pathPtr = path.toNativeUtf8();
    try {
      final handle = _initFn!(pathPtr, useGpu ? 1 : 0);
      return handle;
    } finally {
      calloc.free(pathPtr);
    }
  }

  static String transcribe(
    Pointer<Void> handle,
    List<double> samples, {
    String language = 'pt',
  }) {
    _ensureLoaded();
    if (_transcribeFn == null || handle == nullptr || samples.isEmpty) return '';

    final pcmPtr = calloc<Float>(samples.length);
    final langPtr = language.toNativeUtf8();
    final outPtr = calloc<Uint8>(65536);

    try {
      final pcmList = pcmPtr.asTypedList(samples.length);
      for (var i = 0; i < samples.length; i++) {
        pcmList[i] = samples[i];
      }

      final res = _transcribeFn!(
        handle,
        pcmPtr,
        samples.length,
        langPtr,
        outPtr.cast<Utf8>(),
        65536,
      );

      if (res < 0) return '';
      return outPtr.cast<Utf8>().toDartString();
    } finally {
      calloc.free(pcmPtr);
      calloc.free(langPtr);
      calloc.free(outPtr);
    }
  }

  static void freeModel(Pointer<Void> handle) {
    _ensureLoaded();
    if (_freeFn != null && handle != nullptr) {
      _freeFn!(handle);
    }
  }

  // ---------------------------------------------------------------------------
  // Native Audio API
  // ---------------------------------------------------------------------------

  static List<AudioDevice> listDevices() {
    _ensureLoaded();
    if (_listDevicesFn == null) {
      return const <AudioDevice>[
        AudioDevice(id: '0', name: 'Microfone Padrão do Sistema', isDefault: true),
      ];
    }
    final outPtr = calloc<Uint8>(32768);
    try {
      final res = _listDevicesFn!(outPtr.cast<Utf8>(), 32768);
      if (res < 0) return const <AudioDevice>[];
      final jsonStr = outPtr.cast<Utf8>().toDartString();
      if (jsonStr.isEmpty) return const <AudioDevice>[];
      final decoded = jsonDecode(jsonStr);
      if (decoded is! List) return const <AudioDevice>[];
      return decoded
          .map((e) => AudioDevice.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();
    } catch (_) {
      return const <AudioDevice>[
        AudioDevice(id: '0', name: 'Microfone Padrão do Sistema', isDefault: true),
      ];
    } finally {
      calloc.free(outPtr);
    }
  }

  static int startCapture({String? deviceName}) {
    _ensureLoaded();
    if (_startCaptureFn == null) return 0;
    final devPtr = (deviceName ?? '').toNativeUtf8();
    try {
      return _startCaptureFn!(devPtr);
    } finally {
      calloc.free(devPtr);
    }
  }

  static ({double rms, double peak, double seconds}) getLevel() {
    _ensureLoaded();
    if (_getLevelFn == null) return (rms: 0.0, peak: 0.0, seconds: 0.0);
    final rmsPtr = calloc<Float>();
    final peakPtr = calloc<Float>();
    final secPtr = calloc<Float>();
    try {
      _getLevelFn!(rmsPtr, peakPtr, secPtr);
      return (rms: rmsPtr.value.toDouble(), peak: peakPtr.value.toDouble(), seconds: secPtr.value.toDouble());
    } finally {
      calloc.free(rmsPtr);
      calloc.free(peakPtr);
      calloc.free(secPtr);
    }
  }

  static List<double> stopCapture() {
    _ensureLoaded();
    if (_stopCaptureFn == null || _freeSamplesFn == null) return const <double>[];
    final outPcmPtr = calloc<Pointer<Float>>();
    final outCountPtr = calloc<Int32>();
    try {
      final res = _stopCaptureFn!(outPcmPtr, outCountPtr);
      if (res < 0 || outPcmPtr.value == nullptr || outCountPtr.value <= 0) {
        return const <double>[];
      }
      final count = outCountPtr.value;
      final rawList = outPcmPtr.value.asTypedList(count);
      final list = List<double>.from(rawList);
      _freeSamplesFn!(outPcmPtr.value);
      return list;
    } finally {
      calloc.free(outPcmPtr);
      calloc.free(outCountPtr);
    }
  }

  static bool saveWav(String filePath, List<double> samples) {
    _ensureLoaded();
    if (_saveWavFn == null || samples.isEmpty) return false;
    final pathPtr = filePath.toNativeUtf8();
    final pcmPtr = calloc<Float>(samples.length);
    try {
      final pcmList = pcmPtr.asTypedList(samples.length);
      for (var i = 0; i < samples.length; i++) {
        pcmList[i] = samples[i];
      }
      return _saveWavFn!(pathPtr, pcmPtr, samples.length) == 0;
    } finally {
      calloc.free(pathPtr);
      calloc.free(pcmPtr);
    }
  }
}
