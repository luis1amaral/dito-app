import 'dart:convert';

import 'package:dito_app/config/config_service.dart';
import 'package:dito_app/core/logbook.dart';
import 'package:dito_app/engine/engine_client.dart';
import 'package:dito_app/engine/engine_protocol.dart';
import 'package:dito_app/engine/engine_supervisor.dart';
import 'package:dito_app/output/paste_service.dart';
import 'package:dito_app/state/app_snapshot.dart';
import 'package:dito_app/state/dito_controller.dart';
import 'package:dito_app/state/hud_commands.dart';
import 'package:flutter_test/flutter_test.dart';

class FakePasteBackend implements PasteBackend {
  final List<String> pasted = <String>[];
  final List<String> copied = <String>[];

  @override
  Future<String?> readClipboard() async => null;

  @override
  Future<bool> writeClipboard(String text) async {
    copied.add(text);
    return true;
  }

  @override
  Future<bool> pressCtrlV() async {
    pasted.add(copied.last);
    return true;
  }

  @override
  Future<bool> pressEnter() async => true;

  @override
  Future<bool> restoreFocus() async => true;
}

void main() {
  late EngineClient client;
  late EngineSupervisor supervisor;
  late ConfigService config;
  late FakePasteBackend backend;
  late DitoController controller;
  late List<HudMessage> hudLog;
  late List<FinishedEvent> reviewed;
  late List<String> notified;
  late List<int> sounds;
  late int clock;

  /// The client is never started, so nothing spawns; we feed events by hand.
  void emit(Map<String, Object?> json) {
    final line = jsonEncode(json);
    final event = EngineEvent.parse(
        Map<String, dynamic>.from(jsonDecode(line) as Map));
    // ignore: invalid_use_of_visible_for_testing_member
    client.debugInject(event);
  }

  Future<void> settle() => Future<void>.delayed(Duration.zero);

  setUp(() {
    clock = 0;
    client = EngineClient(
        candidates: <String>[], log: Logbook('t', directory: '.dart_tool'));
    supervisor = EngineSupervisor(
        client: client, log: Logbook('t2', directory: '.dart_tool'));
    config = ConfigService(path: '.dart_tool/controller_test.toml');
    backend = FakePasteBackend();
    hudLog = <HudMessage>[];
    reviewed = <FinishedEvent>[];
    notified = <String>[];
    sounds = <int>[];

    controller = DitoController(
      client: client,
      supervisor: supervisor,
      config: config,
      paste: PasteService(
        backend: backend,
        settle: Duration.zero,
        beforeEnter: Duration.zero,
        restoreAfter: const Duration(milliseconds: 10),
      ),
      hud: hudLog.add,
      review: reviewed.add,
      notify: ({required title, required body}) => notified.add(title),
      playSound: () => sounds.add(clock),
      now: () => clock,
      log: Logbook('t3', directory: '.dart_tool'),
    );
  });

  tearDown(() async {
    await controller.dispose();
    supervisor.dispose();
  });

  group('handshake', () {
    test('engine_ready never starts a recording', () async {
      emit(<String, Object?>{
        'event': 'started',
        'session_id': 'engine_ready',
        'mode': 'engine',
        'device_name': 'init',
      });
      await settle();

      expect(controller.state.phase, AppPhase.idle);
      expect(hudLog, isEmpty);
    });

    test('a real start does move to recording', () async {
      emit(<String, Object?>{
        'event': 'started',
        'session_id': 's1',
        'mode': 'dictation',
        'device_name': 'mic',
      });
      await settle();

      expect(controller.state.phase, AppPhase.recording);
      expect(hudLog.last.kind, HudKind.recording);
    });
  });

  group('resynchronise', () {
    test('a status saying idle pulls us out of a stuck recording', () async {
      emit(<String, Object?>{'event': 'started', 'session_id': 's1', 'mode': 'dictation'});
      await settle();
      expect(controller.state.isRecording, isTrue);

      emit(<String, Object?>{'event': 'status', 'state': 'idle', 'model': 'small'});
      await settle();

      expect(controller.state.phase, AppPhase.idle);
      expect(hudLog.last.kind, HudKind.dismiss);
    });
  });

  group('alarms', () {
    test('quiet reaches the HUD as its own state', () async {
      emit(<String, Object?>{'event': 'alarm', 'state': 'quiet', 'reason': 'baixo'});
      await settle();
      expect(hudLog.last.kind, HudKind.quiet);
    });

    test('dead notifies once, then stays quiet for ten seconds', () async {
      emit(<String, Object?>{'event': 'alarm', 'state': 'dead', 'reason': 'mudo'});
      await settle();
      expect(notified, hasLength(1));

      emit(<String, Object?>{'event': 'alarm', 'state': 'dead', 'reason': 'mudo'});
      await settle();
      expect(notified, hasLength(1), reason: 'repetir treina o usuario a ignorar');

      clock += 11 * 1000000;
      emit(<String, Object?>{'event': 'alarm', 'state': 'dead', 'reason': 'mudo'});
      await settle();
      // The sound rings again after the throttle, but only the first alarm notifies.
      expect(notified, hasLength(1));
      expect(sounds, hasLength(2));
    });
  });

  group('finished', () {
    test('a mis-tap leaves nothing behind and raises no alarm', () async {
      emit(<String, Object?>{'event': 'started', 'session_id': 's1', 'mode': 'dictation'});
      await settle();
      emit(<String, Object?>{
        'event': 'finished',
        'session_id': 's1',
        'mode': 'dictation',
        'text': '',
        'seconds': 0.4,
        'folder': 'C:/x',
        'ever_heard_audio': false,
      });
      await settle();

      expect(controller.state.phase, AppPhase.idle);
      expect(hudLog.last.kind, HudKind.dismiss);
      expect(reviewed, isEmpty);
      expect(backend.pasted, isEmpty);
    });

    test('with confirm on, the card gets the text and nothing is pasted yet', () async {
      await config.update(config.config
          .copyWith(output: config.config.output.copyWith(confirm: true)));

      emit(<String, Object?>{
        'event': 'finished',
        'session_id': 's1',
        'mode': 'dictation',
        'text': 'ola mundo',
        'seconds': 3.0,
        'folder': 'C:/x',
        'ever_heard_audio': true,
      });
      await settle();

      expect(reviewed, hasLength(1));
      expect(backend.pasted, isEmpty);
      expect(controller.pendingReview, isNotNull);
    });

    test('with confirm off, a dictation pastes straight away', () async {
      await config.update(config.config
          .copyWith(output: config.config.output.copyWith(confirm: false)));

      emit(<String, Object?>{
        'event': 'finished',
        'session_id': 's1',
        'mode': 'dictation',
        'text': 'ola mundo',
        'seconds': 3.0,
        'folder': 'C:/x',
        'ever_heard_audio': true,
      });
      await Future<void>.delayed(const Duration(milliseconds: 30));

      expect(backend.pasted, <String>['ola mundo']);
    });

    test('a meeting is NEVER pasted without review', () async {
      await config.update(config.config
          .copyWith(output: config.config.output.copyWith(confirm: false)));

      emit(<String, Object?>{
        'event': 'finished',
        'session_id': 's1',
        'mode': 'meeting',
        'text': 'ata da reuniao',
        'seconds': 300.0,
        'folder': 'C:/x',
        'ever_heard_audio': true,
      });
      await Future<void>.delayed(const Duration(milliseconds: 30));

      expect(backend.pasted, isEmpty);
      expect(reviewed, isEmpty);
    });
  });

  group('tray actions', () {
    test('copy copies and never pastes', () async {
      emit(<String, Object?>{
        'event': 'finished',
        'session_id': 's1',
        'mode': 'dictation',
        'text': 'guardado',
        'seconds': 2.0,
        'folder': 'C:/x',
        'ever_heard_audio': true,
      });
      await Future<void>.delayed(const Duration(milliseconds: 30));
      backend.pasted.clear();

      await controller.copyLastText();

      expect(backend.copied.last, 'guardado');
      expect(backend.pasted, isEmpty, reason: 'copiar nao pode injetar Ctrl+V');
    });
  });

  group('guards', () {
    test('a start while already recording is refused, and SAYS so', () async {
      emit(<String, Object?>{'event': 'started', 'session_id': 's1', 'mode': 'dictation'});
      await settle();
      final before = hudLog.length;
      final phase = controller.state.phase;

      controller.onHotkeyStart('dictation');
      await settle();

      // A refusal nobody can see reads exactly like a dead shortcut, which is what happened.
      expect(hudLog.length, greaterThan(before), reason: 'a recusa tem que aparecer');
      expect(controller.state.phase, phase, reason: 'e nao pode mexer na gravacao em curso');
    });
  });
}
