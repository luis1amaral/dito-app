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

/// Guards the three ways F9/F10 used to die until the app was closed and opened again:
/// a recording nobody could stop, a late transcript idling a newer session, and the pill
/// staying hidden while the engine was still capturing. See CHANGELOG 2026-08-21.

class _RecordingClient extends EngineClient {
  _RecordingClient({super.log});

  final List<EngineCommand> sent = <EngineCommand>[];

  @override
  bool send(EngineCommand command) {
    sent.add(command);
    return true;
  }

  bool get sentStop => sent.any((c) => c is StopCommand);
  void clear() => sent.clear();
}

class _NullPaste extends PasteBackend {
  @override
  Future<String?> readClipboard() async => null;
  @override
  Future<bool> writeClipboard(String text) async => true;
  @override
  Future<bool> pressCtrlV({String? text}) async => true;
  @override
  Future<bool> pressEnter() async => true;
  @override
  Future<bool> restoreFocus() async => true;
}

void main() {
  late _RecordingClient client;
  late EngineSupervisor supervisor;
  late DitoController controller;
  late List<HudMessage> hudLog;

  void emit(Map<String, Object?> json) {
    final event = EngineEvent.parse(
        Map<String, dynamic>.from(jsonDecode(jsonEncode(json)) as Map));
    // ignore: invalid_use_of_visible_for_testing_member
    client.debugInject(event);
  }

  void started(String id, {String mode = 'dictation'}) => emit(<String, Object?>{
        'event': 'started',
        'session_id': id,
        'mode': mode,
        'device_name': 'mic',
      });

  void finished(String id, {String text = 'oi', String mode = 'dictation'}) =>
      emit(<String, Object?>{
        'event': 'finished',
        'session_id': id,
        'mode': mode,
        'text': text,
        'seconds': 1.0,
        'folder': '.dart_tool',
      });

  /// Real timers, but tiny: fake_async cannot be used here because the Logbook writes to disk.
  const startTimeout = Duration(milliseconds: 60);
  const aliveTimeout = Duration(milliseconds: 40);
  Future<void> settle([int ms = 5]) => Future<void>.delayed(Duration(milliseconds: ms));

  setUp(() {
    final log = Logbook('stuck', directory: '.dart_tool');
    client = _RecordingClient(log: log);
    supervisor = EngineSupervisor(client: client, log: log);
    supervisor.markHealthy();
    hudLog = <HudMessage>[];
    controller = DitoController(
      client: client,
      supervisor: supervisor,
      config: ConfigService(path: '.dart_tool/stuck_phase_test.toml'),
      paste: PasteService(
        backend: _NullPaste(),
        settle: Duration.zero,
        beforeEnter: Duration.zero,
        restoreAfter: Duration.zero,
      ),
      hud: hudLog.add,
      review: (_) {},
      startTimeout: startTimeout,
      aliveTimeout: aliveTimeout,
      transcribeTimeout: const Duration(milliseconds: 200),
      log: log,
    );
    // engine_ready is the handshake that makes the supervisor accept commands.
    emit(<String, Object?>{
      'event': 'started',
      'session_id': 'engine_ready',
      'mode': 'engine',
    });
  });

  tearDown(() async {
    await controller.dispose();
    supervisor.dispose();
  });

  group('gravacao fantasma', () {
    test('a tecla solta durante um start lento manda parar quando ele chega', () async {
      expect(controller.onHotkeyStart('dictation'), isTrue);
      // Motor frio: nao responde a tempo e o timeout desiste.
      await settle(startTimeout.inMilliseconds + 20);
      expect(controller.state.phase, AppPhase.idle);
      expect(client.sentStop, isTrue,
          reason: 'desistir so do nosso lado deixa o motor gravando sem dono');

      client.clear();
      // A tecla ja foi solta antes de o motor confirmar.
      controller.onHotkeyStop('dictation');
      started('s1');
      await settle();

      expect(client.sentStop, isTrue,
          reason: 'a gravacao que chegou atrasada tem de ser encerrada, nao adotada');
    });

    test('depois do start abandonado a proxima tecla volta a ser aceita', () async {
      controller.onHotkeyStart('meeting');
      await settle(startTimeout.inMilliseconds + 20);
      controller.onHotkeyStop('meeting');
      client.clear();
      started('s1', mode: 'meeting');
      await settle();
      expect(client.sentStop, isTrue,
          reason: 'sem esse stop a gravacao segue viva e nenhuma tecla e aceita de novo');
      finished('s1', text: '', mode: 'meeting');
      await settle();

      expect(controller.state.phase, AppPhase.idle);
      expect(controller.onHotkeyStart('meeting'), isTrue,
          reason: 'era aqui que F10 ficava morto ate fechar e abrir o app');
    });

    test('gravando sem sinal do motor, o app confere com o motor', () async {
      started('s1');
      await settle();
      expect(controller.state.isRecording, isTrue);

      client.clear();
      await settle(aliveTimeout.inMilliseconds + 20);
      expect(client.sent.any((c) => c is StatusCommand), isTrue,
          reason: 'fase gravando sem level do motor e uma fase mentindo');

      emit(<String, Object?>{'event': 'status', 'state': 'idle', 'model': 'small'});
      await settle();
      expect(controller.state.phase, AppPhase.idle);
    });

    test('o level do motor segura a fase: gravacao viva nao dispara resync', () async {
      started('s1');
      await settle();
      for (var i = 0; i < 4; i++) {
        emit(<String, Object?>{'event': 'level', 'rms': 0.2, 'peak': 0.3, 'seconds': 1.0});
        await settle(aliveTimeout.inMilliseconds ~/ 2);
      }
      expect(controller.state.isRecording, isTrue,
          reason: 'uma reuniao de verdade nao pode ser interrompida pelo watchdog');
    });

    test('a recusa numa gravacao ativa pergunta o estado real ao motor', () async {
      started('s1');
      await settle();
      client.clear();

      expect(controller.onHotkeyStart('dictation'), isFalse);
      expect(client.sent.any((c) => c is StatusCommand), isTrue,
          reason: 'sem esse resync a fase presa em recording nunca se cura sozinha');
    });
  });

  group('sessoes sobrepostas', () {
    test('o finished de uma sessao velha nao encerra a fase da nova, nem gravando', () async {
      started('velha');
      await settle();
      controller.onHotkeyStop('dictation');
      emit(<String, Object?>{'event': 'phase', 'phase': 'transcribing'});
      await settle();

      started('nova');
      await settle();
      expect(controller.state.phase, AppPhase.recording);

      finished('velha');
      await settle();

      expect(controller.state.phase, AppPhase.recording,
          reason: 'a transcricao atrasada da anterior nao pode idlar a gravacao no ar');
      expect(hudLog.last.kind, isNot(HudKind.dismiss),
          reason: 'nem apagar a pilula de quem esta gravando');
    });

    test('nem transcrevendo: e o caso real do log, duas transcricoes sobrepostas', () async {
      // 19:40:09 para a sessao A (134s de audio), 19:40:11 para a B (0,3s): as duas transcrevem.
      started('A');
      await settle();
      controller.onHotkeyStop('dictation');
      started('B');
      await settle();
      controller.onHotkeyStop('dictation');
      emit(<String, Object?>{'event': 'phase', 'phase': 'transcribing'});
      await settle();
      expect(controller.state.phase, AppPhase.transcribing);
      hudLog.clear();

      // A e mais lenta e termina depois de B ja estar transcrevendo.
      finished('A', text: 'texto da A');
      await settle();

      expect(controller.state.phase, AppPhase.transcribing,
          reason: 'a sessao B ainda esta transcrevendo: quem manda na fase e ela');
      expect(hudLog.any((m) => m.kind == HudKind.dismiss), isFalse,
          reason: 'e a pilula de "transcrevendo" da B nao pode ser apagada pela A');
    });

    test('o finished da propria sessao encerra normalmente', () async {
      started('s1');
      await settle();
      finished('s1', text: '');
      await settle();

      expect(controller.state.phase, AppPhase.idle);
      expect(hudLog.last.kind, HudKind.dismiss);
    });
  });
}
