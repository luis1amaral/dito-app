@Tags(<String>['live'])
library;

import 'dart:async';
import 'dart:io';

import 'package:dito_app/core/logbook.dart';
import 'package:dito_app/engine/engine_client.dart';
import 'package:dito_app/engine/engine_health.dart';
import 'package:dito_app/engine/engine_protocol.dart';
import 'package:dito_app/engine/engine_supervisor.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late EngineClient client;
  late EngineSupervisor supervisor;
  late List<EngineEvent> seen;
  late StreamSubscription<EngineEvent> sub;

  var consumed = 0;

  Future<T> waitFor<T extends EngineEvent>(
      {Duration timeout = const Duration(seconds: 90)}) {
    for (var i = consumed; i < seen.length; i++) {
      final event = seen[i];
      if (event is T) {
        consumed = i + 1;
        return Future<T>.value(event);
      }
    }
    consumed = seen.length;

    final completer = Completer<T>();
    late StreamSubscription<EngineEvent> local;
    local = client.events.listen((event) {
      if (event is T && !completer.isCompleted) {
        consumed = seen.length;
        completer.complete(event);
        local.cancel();
      }
    });
    return completer.future.timeout(timeout, onTimeout: () {
      local.cancel();
      throw TimeoutException('nenhum ${T.toString()} em ${timeout.inSeconds}s; '
          'vistos: ${seen.map((e) => e.runtimeType).toList()}');
    });
  }

  setUp(() {
    client = EngineClient(
      log: Logbook('test-engine', directory: Directory.systemTemp.path),
    );
    supervisor = EngineSupervisor(
      client: client,
      log: Logbook('test-supervisor', directory: Directory.systemTemp.path),
    );
    seen = <EngineEvent>[];
    consumed = 0;
    sub = client.events.listen(seen.add);
  });

  tearDown(() async {
    await sub.cancel();
    await supervisor.stop();
    supervisor.dispose();
  });

  test('handshake: the engine announces itself and reports idle', () async {
    final boot = Stopwatch()..start();
    await supervisor.start();

    await waitFor<EngineReadyEvent>();
    final readyMs = boot.elapsedMilliseconds;

    final status = await waitFor<StatusEvent>();
    expect(status.isRecording, isFalse,
        reason: 'o motor nao pode nascer gravando');
    expect(status.model, isNotEmpty);

    expect(supervisor.health.state, EngineState.ready);
    expect(seen.whereType<StartedEvent>(), isEmpty);

    // ignore: avoid_print
    print(
        'handshake pronto em ${readyMs}ms  modelo=${status.model} backend=${status.backend}');
  }, timeout: const Timeout(Duration(minutes: 2)));

  test('list_devices returns devices list from native whisper', () async {
    await supervisor.start();
    await waitFor<EngineReadyEvent>();

    expect(client.send(const ListDevicesCommand()), isTrue);
    final devices = await waitFor<DevicesEvent>();
    expect(devices, isNotNull);

    // ignore: avoid_print
    print('dispositivos: ${devices.devices.map((d) => d.name).join(" | ")}');
  }, timeout: const Timeout(Duration(minutes: 2)));
}
