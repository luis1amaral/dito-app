import 'dart:convert';

import 'package:dito_app/config/config_service.dart';
import 'package:dito_app/core/logbook.dart';
import 'package:dito_app/engine/engine_client.dart';
import 'package:dito_app/engine/engine_protocol.dart';
import 'package:dito_app/engine/engine_supervisor.dart';
import 'package:dito_app/output/paste_service.dart';
import 'package:dito_app/state/dito_controller.dart';
import 'package:dito_app/state/hud_commands.dart';
import 'package:flutter_test/flutter_test.dart';

/// Guards the regression from CHANGELOG 2026-08-23 where deleting hud_window.dart silently killed focus restore; see docs/armadilhas.md 6.11.

class _RecordingClient extends EngineClient {
  _RecordingClient({super.log, required this.trace});

  final List<String> trace;

  @override
  bool send(EngineCommand command) {
    if (command is StartCommand) trace.add('start');
    return true;
  }
}

class _DeafClient extends EngineClient {
  _DeafClient({super.log});

  @override
  bool send(EngineCommand command) => false;
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
  late List<String> trace;
  late EngineSupervisor supervisor;
  late DitoController controller;
  late List<HudMessage> hudLog;
  late EngineClient client;

  /// The handshake, not markHealthy(), is what makes the supervisor accept commands.
  void handshake(EngineClient c) {
    final event = EngineEvent.parse(Map<String, dynamic>.from(jsonDecode(jsonEncode(
        <String, Object?>{
          'event': 'started',
          'session_id': 'engine_ready',
          'mode': 'engine',
        })) as Map));
    // ignore: invalid_use_of_visible_for_testing_member
    c.debugInject(event);
  }

  DitoController build(EngineClient c) {
    supervisor = EngineSupervisor(
        client: c, log: Logbook('focus2', directory: '.dart_tool'));
    return DitoController(
      client: c,
      supervisor: supervisor,
      config: ConfigService(path: '.dart_tool/focus_target_test.toml'),
      paste: PasteService(
        backend: _NullPaste(),
        settle: Duration.zero,
        beforeEnter: Duration.zero,
        restoreAfter: Duration.zero,
      ),
      hud: hudLog.add,
      review: (_) {},
      takeFocus: () => trace.add('takeFocus'),
      log: Logbook('focus', directory: '.dart_tool'),
    );
  }

  setUp(() {
    trace = <String>[];
    hudLog = <HudMessage>[];
    client = _RecordingClient(
        log: Logbook('focus1', directory: '.dart_tool'), trace: trace);
    controller = build(client);
    handshake(client);
  });

  tearDown(() async {
    await controller.dispose();
    supervisor.dispose();
  });

  test('an accepted start captures the focus target before the engine is told', () {
    expect(controller.onHotkeyStart('dictation'), isTrue);
    expect(trace, <String>['takeFocus', 'start'],
        reason: 'captured after the start, the pill may already own the foreground');
  });

  test('the toggle key captures the target too, not just push-to-talk', () {
    expect(controller.onHotkeyStart('meeting'), isTrue);
    expect(trace.first, 'takeFocus');
  });

  test('a start the engine refuses does not capture anything', () async {
    await controller.dispose();
    supervisor.dispose();
    trace = <String>[];
    final deaf = _DeafClient(log: Logbook('focus3', directory: '.dart_tool'));
    controller = build(deaf);
    handshake(deaf);

    expect(controller.onHotkeyStart('dictation'), isFalse);
    expect(trace, isEmpty,
        reason: 'a refused start must not overwrite the target of a live session');
  });

  test('a start refused because the engine is not ready does not capture', () async {
    await controller.dispose();
    supervisor.dispose();
    trace = <String>[];
    // Never marked healthy: the supervisor refuses commands until the handshake lands.
    controller = build(_RecordingClient(
        log: Logbook('focus4', directory: '.dart_tool'), trace: trace));

    expect(controller.onHotkeyStart('dictation'), isFalse);
    expect(trace, isEmpty);
  });

  test('every recording refreshes the target, so a new session never reuses the old one', () {
    expect(controller.onHotkeyStart('dictation'), isTrue);
    controller.onHotkeyStop('dictation');
    final event = EngineEvent.parse(Map<String, dynamic>.from(jsonDecode(jsonEncode(
        <String, Object?>{
          'event': 'finished',
          'session_id': 's1',
          'mode': 'dictation',
          'text': 'oi',
          'seconds': 1.0,
          'folder': '.dart_tool',
        })) as Map));
    // ignore: invalid_use_of_visible_for_testing_member
    client.debugInject(event);

    expect(controller.onHotkeyStart('dictation'), isTrue);
    expect(trace.where((e) => e == 'takeFocus').length, 2);
  });
}
