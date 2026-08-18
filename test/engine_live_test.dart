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

/// Talks to the real dito-engine.exe; run with `flutter test --tags live`.
///
/// This is the seam docs/porte-windows.md records as never verified.
void main() {
  final enginePath = Platform.environment['DITO_ENGINE'] ??
      r'C:\Users\Luis\Desktop\Projetos\dito\dito-app\build\windows\dist\dito-engine\dito-engine.exe';

  late EngineClient client;
  late EngineSupervisor supervisor;
  late List<EngineEvent> seen;
  late StreamSubscription<EngineEvent> sub;

  var consumed = 0;

  /// Checks what already arrived before waiting: on a broadcast stream the event we want
  /// can land between two awaits, and listening only to the future misses it.
  Future<T> waitFor<T extends EngineEvent>({Duration timeout = const Duration(seconds: 90)}) {
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

  setUpAll(() {
    if (!File(enginePath).existsSync()) {
      fail('motor nao encontrado em $enginePath — defina DITO_ENGINE');
    }
  });

  setUp(() {
    client = EngineClient(
      candidates: <String>[enginePath],
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
    expect(status.isRecording, isFalse, reason: 'o motor nao pode nascer gravando');
    expect(status.model, isNotEmpty);

    expect(supervisor.health.state, EngineState.ready);
    // The bug that killed the old port: engine_ready must never look like a recording.
    expect(seen.whereType<StartedEvent>(), isEmpty);

    // ignore: avoid_print
    print('handshake pronto em ${readyMs}ms  modelo=${status.model} backend=${status.backend}');
  }, timeout: const Timeout(Duration(minutes: 2)));

  test('list_devices returns at least one input', () async {
    await supervisor.start();
    await waitFor<EngineReadyEvent>();

    expect(client.send(const ListDevicesCommand()), isTrue);
    final devices = await waitFor<DevicesEvent>();
    expect(devices.devices, isNotEmpty);

    // ignore: avoid_print
    print('dispositivos: ${devices.devices.map((d) => d.name).join(" | ")}');
  }, timeout: const Timeout(Duration(minutes: 2)));

  test('record and transcribe: start -> started -> stop -> finished', () async {
    await supervisor.start();
    await waitFor<EngineReadyEvent>();

    final startLatency = Stopwatch()..start();
    expect(
      client.send(const StartCommand(
        mode: 'dictation',
        model: 'small',
        language: 'pt',
        device: '',
        devicePref: 'auto',
      )),
      isTrue,
    );

    final started = await waitFor<StartedEvent>();
    final startMs = startLatency.elapsedMilliseconds;
    expect(started.sessionId, isNot(EngineEvent.readySessionId));

    await Future<void>.delayed(const Duration(seconds: 3));
    expect(seen.whereType<LevelEvent>(), isNotEmpty,
        reason: 'o motor deve emitir nivel enquanto grava');

    final stopLatency = Stopwatch()..start();
    expect(client.send(const StopCommand()), isTrue);

    final finished = await waitFor<FinishedEvent>(timeout: const Duration(minutes: 3));
    final stopMs = stopLatency.elapsedMilliseconds;

    expect(finished.seconds, greaterThan(2.0));
    expect(finished.folder, isNotEmpty);
    expect(Directory(finished.folder).existsSync(), isTrue,
        reason: 'a pasta da sessao tem que existir no disco');

    // ignore: avoid_print
    print('start->started: ${startMs}ms  stop->finished: ${stopMs}ms  '
        'audio=${finished.seconds}s ouviu=${finished.everHeardAudio}  '
        'texto=${finished.text.length} chars');
  }, timeout: const Timeout(Duration(minutes: 5)));

  test('the supervisor notices death and brings the engine back', () async {
    await supervisor.start();
    await waitFor<EngineReadyEvent>();
    expect(supervisor.health.state, EngineState.ready);

    final died = Completer<void>();
    late void Function() listener;
    listener = () {
      if (supervisor.health.state == EngineState.dead && !died.isCompleted) {
        died.complete();
      }
    };
    supervisor.addListener(listener);

    Process.runSync('taskkill', <String>['/F', '/IM', 'dito-engine.exe']);
    await died.future.timeout(const Duration(seconds: 20));
    expect(supervisor.health.restarts, greaterThan(0));

    await waitFor<EngineReadyEvent>();
    expect(supervisor.health.state, EngineState.ready,
        reason: 'o supervisor tem que religar o motor sozinho');
    supervisor.removeListener(listener);
  }, timeout: const Timeout(Duration(minutes: 3)));
}
