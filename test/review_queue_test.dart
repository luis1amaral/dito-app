import 'dart:convert';

import 'package:dito_app/config/config_service.dart';
import 'package:dito_app/core/logbook.dart';
import 'package:dito_app/engine/engine_client.dart';
import 'package:dito_app/engine/engine_protocol.dart';
import 'package:dito_app/engine/engine_supervisor.dart';
import 'package:dito_app/output/paste_service.dart';
import 'package:dito_app/state/dito_controller.dart';
import 'package:flutter_test/flutter_test.dart';

/// Falar 1, falar 2, falar 3 sem confirmar nenhuma tem de deixar TRES cartoes esperando, e cada
/// confirmacao resolve so o seu. Antes, cada gravacao nova sobrescrevia a revisao pendente e o
/// texto anterior sumia sem aviso.

class _Client extends EngineClient {
  _Client({super.log});
  @override
  bool send(EngineCommand command) => true;
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
  late _Client client;
  late EngineSupervisor supervisor;
  late DitoController controller;
  late List<FinishedEvent> mostrados;

  void finished(String id, String text) {
    final event = EngineEvent.parse(Map<String, dynamic>.from(jsonDecode(jsonEncode(
        <String, Object?>{
          'event': 'finished',
          'session_id': id,
          'mode': 'dictation',
          'text': text,
          'seconds': 2.0,
          'folder': '.dart_tool',
        })) as Map));
    // ignore: invalid_use_of_visible_for_testing_member
    client.debugInject(event);
  }

  Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 5));

  setUp(() async {
    final log = Logbook('fila', directory: '.dart_tool');
    client = _Client(log: log);
    supervisor = EngineSupervisor(client: client, log: log);
    mostrados = <FinishedEvent>[];
    final config = ConfigService(path: '.dart_tool/review_queue_test.toml');
    await config.load();
    config.update(config.config.copyWith(
      output: config.config.output.copyWith(confirm: true, paste: false),
    ));
    controller = DitoController(
      client: client,
      supervisor: supervisor,
      config: config,
      paste: PasteService(
        backend: _NullPaste(),
        settle: Duration.zero,
        beforeEnter: Duration.zero,
        restoreAfter: Duration.zero,
      ),
      hud: (_) {},
      review: mostrados.add,
      log: log,
    );
  });

  tearDown(() async {
    await controller.dispose();
    supervisor.dispose();
  });

  test('tres falas seguidas deixam tres cartoes esperando', () async {
    finished('s1', 'falo 1');
    await settle();
    finished('s2', 'falo 2');
    await settle();
    finished('s3', 'falo 3');
    await settle();

    expect(controller.pendingReviews.map((e) => e.text), <String>['falo 1', 'falo 2', 'falo 3'],
        reason: 'antes, a gravacao nova apagava a revisao anterior');
    expect(mostrados, hasLength(3), reason: 'a janela precisa receber os tres para empilhar');
  });

  test('confirmar um cartao resolve so ele', () async {
    finished('s1', 'falo 1');
    await settle();
    finished('s2', 'falo 2');
    await settle();

    await controller.onReviewSend('falo 1', toVault: false, sessionId: 's1');

    expect(controller.pendingReviews.map((e) => e.sessionId), <String>['s2']);
  });

  test('descartar um cartao nao leva os outros junto', () async {
    finished('s1', 'falo 1');
    await settle();
    finished('s2', 'falo 2');
    await settle();
    finished('s3', 'falo 3');
    await settle();

    controller.onReviewDiscard(sessionId: 's2');

    expect(controller.pendingReviews.map((e) => e.sessionId), <String>['s1', 's3']);
  });

  test('sem id, o envio limpa a fila inteira (compatibilidade)', () async {
    finished('s1', 'falo 1');
    await settle();
    finished('s2', 'falo 2');
    await settle();

    await controller.onReviewSend('falo 2', toVault: false);

    expect(controller.pendingReviews, isEmpty);
  });
}
