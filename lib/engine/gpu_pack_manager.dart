import 'dart:async';
import 'dart:io';

import '../config/paths.dart';
import '../core/logbook.dart';

/// Downloads the optional CUDA backend module on demand, mirroring ModelManager's pattern:
/// only for a machine that actually has a compatible NVIDIA GPU, a no-op everywhere else.
class GpuPackManager {
  GpuPackManager({Logbook? log}) : _log = log ?? Logbook('gpu');

  final Logbook _log;
  Future<String?>? _activeDownload;

  static const String _packUrl =
      'https://apt.defaltm.com/extras/dito-gpu-cuda-linux-x64.tar.gz';

  static String get _sep => Platform.pathSeparator;
  static String get gpuDir => '${DitoPaths.dataDir}${_sep}gpu';
  static String get _moduleFile => '$gpuDir${_sep}libggml-cuda.so';

  /// True only when the machine has an NVIDIA GPU driver loaded; no driver, no point downloading.
  static bool hasCompatibleGpu() {
    if (!Platform.isLinux) return false;
    return File('/proc/driver/nvidia/version').existsSync();
  }

  static bool isDownloaded() => File(_moduleFile).existsSync();

  /// Returns the directory to hand to the native side, or null if there's nothing to use
  /// (no compatible GPU, or the download hasn't happened/failed): the caller just skips it then.
  Future<String?> ensureGpuPack() async {
    if (!hasCompatibleGpu()) return null;
    if (isDownloaded()) return gpuDir;

    if (_activeDownload != null) return _activeDownload;
    final future = _download();
    _activeDownload = future;
    try {
      return await future;
    } finally {
      _activeDownload = null;
    }
  }

  Future<String?> _download() async {
    final dir = Directory(gpuDir)..createSync(recursive: true);
    final tmpTar = File('${dir.path}$_sep.download.tar.gz');
    _log('GPU NVIDIA detectada, baixando pacote de aceleracao de $_packUrl');

    final client = HttpClient();
    try {
      final request = await client.getUrl(Uri.parse(_packUrl));
      final response = await request.close();
      if (response.statusCode != 200) {
        _log('pacote de GPU indisponivel: HTTP ${response.statusCode}');
        return null;
      }

      final sink = tmpTar.openWrite();
      await response.pipe(sink);

      final extract = await Process.run('tar', ['-xzf', tmpTar.path, '-C', dir.path]);
      if (extract.exitCode != 0) {
        _log('falha ao extrair pacote de GPU: ${extract.stderr}');
        return null;
      }

      if (!isDownloaded()) {
        _log('pacote de GPU extraido mas libggml-cuda.so nao apareceu');
        return null;
      }

      _log('pacote de GPU pronto em ${dir.path}');
      return gpuDir;
    } catch (e) {
      _log('erro no download do pacote de GPU: $e');
      return null;
    } finally {
      client.close();
      if (tmpTar.existsSync()) {
        try {
          tmpTar.deleteSync();
        } catch (_) {}
      }
    }
  }
}
