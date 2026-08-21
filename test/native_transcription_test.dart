import 'dart:io';
import 'package:dito_app/config/paths.dart';
import 'package:dito_app/core/logbook.dart';
import 'package:dito_app/engine/engine_protocol.dart';
import 'package:dito_app/engine/native_engine.dart';
import 'package:dito_whisper/dito_whisper.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  setUpAll(() {
    DitoPaths.ensureDirs();
  });

  group('NativeEngine & DitoWhisper tests', () {
    test('DitoWhisper FFI bindings work without errors', () {
      expect(DitoWhisper.version, isNotEmpty);
      final devices = DitoWhisper.listDevices();
      expect(devices, isNotEmpty);
      expect(devices.first.name, isNotEmpty);
    });

    test('Audio capture and level polling return valid numbers', () {
      final level = DitoWhisper.getLevel();
      expect(level.rms, greaterThanOrEqualTo(0.0));
      expect(level.peak, greaterThanOrEqualTo(0.0));
      expect(level.seconds, greaterThanOrEqualTo(0.0));
    });

    test('NativeEngine initializes and handles lifecycle commands', () async {
      final tempDir = Directory.systemTemp.createTempSync('engine_test_');
      addTearDown(() => tempDir.deleteSync(recursive: true));

      final engine = NativeEngine(
        log: Logbook('test_engine', directory: tempDir.path),
      );

      final events = <EngineEvent>[];
      final sub = engine.events.listen(events.add);

      await engine.init();
      await Future<void>.delayed(const Duration(milliseconds: 50));

      expect(events.whereType<EngineReadyEvent>(), isNotEmpty);
      expect(events.whereType<StatusEvent>(), isNotEmpty);

      await engine.handleCommand(const ListDevicesCommand());
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(events.whereType<DevicesEvent>(), isNotEmpty);

      await sub.cancel();
      await engine.dispose();
    });
  });
}
