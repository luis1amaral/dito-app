import 'dart:async';
import 'dart:io';

import '../config/paths.dart';
import '../core/logbook.dart';

class ModelManager {
  ModelManager({Logbook? log}) : _log = log ?? Logbook('models');

  final Logbook _log;
  final Map<String, Future<String>> _activeDownloads = {};

  static const String _hfBaseUrl =
      'https://huggingface.co/ggerganov/whisper.cpp/resolve/main';

  static String get _sep => Platform.pathSeparator;

  static String get modelsDir => '${DitoPaths.dataDir}${_sep}models';

  static String fileNameFor(String model) {
    final clean = model.trim().toLowerCase();
    return clean.endsWith('.bin') ? clean : 'ggml-$clean.bin';
  }

  static String modelPathFor(String model) {
    return '$modelsDir$_sep${fileNameFor(model)}';
  }

  static bool isDownloaded(String model) {
    final file = File(modelPathFor(model));
    return file.existsSync() && file.lengthSync() > 1024 * 1024;
  }

  static String urlFor(String model) {
    final file = fileNameFor(model);
    return '$_hfBaseUrl/$file';
  }

  Future<String> ensureModel(
    String model, {
    void Function(double progress, int received, int total)? onProgress,
  }) async {
    final path = modelPathFor(model);
    final targetFile = File(path);

    if (targetFile.existsSync() && targetFile.lengthSync() > 1024 * 1024) {
      return path;
    }

    if (_activeDownloads.containsKey(model)) {
      return _activeDownloads[model]!;
    }

    final future = _downloadModel(model, path, targetFile, onProgress: onProgress);
    _activeDownloads[model] = future;
    try {
      return await future;
    } finally {
      _activeDownloads.remove(model);
    }
  }

  Future<String> _downloadModel(
    String model,
    String path,
    File targetFile, {
    void Function(double progress, int received, int total)? onProgress,
  }) async {
    targetFile.parent.createSync(recursive: true);
    final url = urlFor(model);
    _log('baixando modelo $model de $url');

    final tmpFile = File('$path.tmp');
    if (tmpFile.existsSync()) {
      try {
        tmpFile.deleteSync();
      } catch (_) {}
    }

    final client = HttpClient()
      ..badCertificateCallback =
          ((X509Certificate cert, String host, int port) => true);
    try {
      final request = await client.getUrl(Uri.parse(url));
      final response = await request.close();

      if (response.statusCode != 200) {
        throw HttpException(
            'Falha ao baixar modelo ($model): HTTP ${response.statusCode}');
      }

      final total = response.contentLength;
      int received = 0;

      final sink = tmpFile.openWrite();
      await for (final chunk in response) {
        sink.add(chunk);
        received += chunk.length;
        if (total > 0 && onProgress != null) {
          onProgress(received / total, received, total);
        }
      }
      await sink.flush();
      await sink.close();

      if (targetFile.existsSync()) {
        try {
          targetFile.deleteSync();
        } catch (_) {}
      }
      tmpFile.renameSync(path);
      _log('download concluido: $path ($received bytes)');
      return path;
    } catch (e) {
      _log('erro no download de $model: $e');
      if (tmpFile.existsSync()) {
        try {
          tmpFile.deleteSync();
        } catch (_) {}
      }
      rethrow;
    } finally {
      client.close();
    }
  }
}
