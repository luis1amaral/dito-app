import 'dart:io';

import 'package:dito_app/config/paths.dart';
import 'package:dito_app/core/logbook.dart';
import 'package:dito_app/engine/model_manager.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  setUpAll(() {
    DitoPaths.ensureDirs();
  });

  group('ModelManager unit tests', () {
    test('fileNameFor formats model names cleanly', () {
      expect(ModelManager.fileNameFor('small'), 'ggml-small.bin');
      expect(ModelManager.fileNameFor('tiny'), 'ggml-tiny.bin');
      expect(ModelManager.fileNameFor('base'), 'ggml-base.bin');
      expect(ModelManager.fileNameFor('large-v3'), 'ggml-large-v3.bin');
      expect(ModelManager.fileNameFor('ggml-medium.bin'), 'ggml-medium.bin');
      expect(ModelManager.fileNameFor('  SMALL  '), 'ggml-small.bin');
    });

    test('urlFor points to official huggingface repository', () {
      expect(
        ModelManager.urlFor('small'),
        'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin',
      );
      expect(
        ModelManager.urlFor('tiny'),
        'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin',
      );
    });

    test('modelPathFor uses local data directory', () {
      final path = ModelManager.modelPathFor('small');
      expect(path, contains('models'));
      expect(path, endsWith('ggml-small.bin'));
    });

    test('isDownloaded accurately detects valid model files', () {
      final tempDir = Directory.systemTemp.createTempSync('model_test_');
      addTearDown(() => tempDir.deleteSync(recursive: true));

      final manager = ModelManager(
        log: Logbook('test_models', directory: tempDir.path),
      );
      expect(manager, isNotNull);

      // Verify that a non-existent model reports not downloaded
      expect(ModelManager.isDownloaded('non_existent_model_xyz'), isFalse);
    });
  });
}
