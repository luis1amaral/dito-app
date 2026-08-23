import 'dart:convert';
import 'dart:io';

import 'package:dito_app/config/config_model.dart';
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

class FakePasteBackend extends PasteBackend {
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
  Future<bool> pressCtrlV({String? text}) async {
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
    client = EngineClient(log: Logbook('t', directory: '.dart_tool'));
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
      // Both channels ship off; this case is about the throttle, so turn them on explicitly.
      await config.update(config.config.copyWith(
          audio: config.config.audio
              .copyWith(alerts: const AlertConfig(sound: true, notify: true))));

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

  group('paste confirmation', () {
    test('a successful paste confirms with a toast, not silence', () async {
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
      final toasts =
          hudLog.where((m) => m.kind == HudKind.toast).map((m) => m.toastKind);
      expect(toasts, contains(HudToast.pasted),
          reason: 'sucesso sem sinal e indistinguivel de falha');
    });

    test('onReviewSend with toVault and paste emits exactly one toast', () async {
      // Redirects away from the real ~/notas vault so the test never touches the dono's disk.
      await config.update(config.config.copyWith(
          obsidian: config.config.obsidian
              .copyWith(vault: '.dart_tool/controller_test_vault')));

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
      hudLog.clear();

      await controller.onReviewSend('ola mundo', toVault: true, sessionId: 's1');

      final pastedToasts = hudLog.where(
          (m) => m.kind == HudKind.toast && m.toastKind == HudToast.pasted);
      expect(pastedToasts, hasLength(1),
          reason: 'toVault + paste nao pode duplicar a confirmacao');
    });

    test('onReviewSend with paste and without toVault pastes and confirms once', () async {
      // The most common path in practice: no vault, just paste. Left uncovered before this round.
      await config.update(config.config
          .copyWith(output: config.config.output.copyWith(paste: true)));

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
      hudLog.clear();

      await controller.onReviewSend('ola mundo', toVault: false, sessionId: 's1');

      expect(backend.pasted, <String>['ola mundo']);
      final finalSignals = hudLog.where((m) =>
          m.kind == HudKind.dismiss ||
          (m.kind == HudKind.toast && m.toastKind == HudToast.pasted));
      expect(finalSignals, hasLength(1),
          reason: 'paste direto pela review card tem que confirmar exatamente uma vez');
    });

    test('a failed vault save reports failure, never the success toast', () async {
      // Parent is a FILE, not a directory: mkdir -p fails with ENOTDIR, never touching ~/notas.
      final blocker = File('.dart_tool/controller_test_vault_blocker');
      blocker.createSync(recursive: true);
      addTearDown(() {
        if (blocker.existsSync()) blocker.deleteSync();
      });
      await config.update(config.config.copyWith(
          obsidian: config.config.obsidian.copyWith(vault: blocker.path),
          output: config.config.output.copyWith(paste: false)));

      await controller.onReviewSend('ola mundo', toVault: true, sessionId: null);

      final last = hudLog.last;
      expect(last.kind, HudKind.toast);
      expect(last.toastKind, HudToast.failed,
          reason: 'falha ao gravar a nota nao pode parecer "colado"');
    });
  });

  group('session ordering', () {
    test('an old session finishing while a newer one is on air pastes silently', () async {
      await config.update(config.config.copyWith(
          output: config.config.output.copyWith(confirm: false, paste: true)));

      emit(<String, Object?>{'event': 'started', 'session_id': 's1', 'mode': 'dictation'});
      await settle();
      // s2 takes over as the session on air before s1's late transcript arrives.
      emit(<String, Object?>{'event': 'started', 'session_id': 's2', 'mode': 'dictation'});
      await settle();
      hudLog.clear();

      emit(<String, Object?>{
        'event': 'finished',
        'session_id': 's1',
        'mode': 'dictation',
        'text': 'texto da sessao antiga',
        'seconds': 3.0,
        'folder': 'C:/x',
        'ever_heard_audio': true,
      });
      await Future<void>.delayed(const Duration(milliseconds: 30));

      expect(controller.state.phase, AppPhase.recording,
          reason: 'a pilula da sessao nova nao pode ser mexida pelo evento antigo');
      expect(
          hudLog.where((m) => m.kind == HudKind.toast && m.toastKind == HudToast.pasted),
          isEmpty,
          reason: 'colar da sessao antiga nao pode atropelar a pilula "Gravando" da sessao nova');
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
