import 'dart:async';

import 'package:dito_app/keys/hotkey_machine.dart';
import 'package:dito_app/keys/key_source.dart';
import 'package:flutter_test/flutter_test.dart';

/// The two ways the machine itself could go deaf until the app restarted: a release the keymap
/// never reported (F10 swallowed forever) and a start that threw (F9 stuck active).
/// See CHANGELOG 2026-08-21.
void main() {
  late FakeKeySource source;
  late List<String> events;

  const dictation = HotkeyBinding(action: 'dictation', key: 'f9', mode: HotkeyMode.hold);
  const meeting = HotkeyBinding(action: 'meeting', key: 'f10', mode: HotkeyMode.toggle);

  Future<void> settle() => Future<void>.delayed(Duration.zero);

  HotkeyMachine build({bool Function(String action)? onStart}) => HotkeyMachine(
        source: source,
        onStart: onStart ??
            (action) {
              events.add('start:$action');
              return true;
            },
        onStop: (action) => events.add('stop:$action'),
        onRefused: (action, blockedBy) => events.add('refused:$action'),
      )
        ..bind(<HotkeyBinding>[dictation, meeting])
        ..start();

  setUp(() {
    source = FakeKeySource();
    events = <String>[];
  });

  tearDown(() async {
    await source.dispose();
  });

  test('um release que o teclado nunca reporta nao pode calar o F10 para sempre', () async {
    final machine = build();
    // A tecla e apertada e o keymap continua jurando que ela esta pressionada.
    source.press('meeting');
    await settle();
    expect(events, <String>['start:meeting']);

    source.elapse(kToggleReleaseCeiling + const Duration(milliseconds: 100));
    await settle();

    // Sem o teto, este segundo aperto some sem log e sem acao — o sintoma relatado.
    source.press('meeting');
    await settle();
    expect(events, <String>['start:meeting', 'stop:meeting'],
        reason: 'F10 tem de voltar a responder mesmo sem o release chegar');

    await machine.dispose();
  });

  test('o release normal continua liberando o toggle na hora', () async {
    final machine = build();
    source.press('meeting');
    await settle();
    source.release('meeting');
    source.tick();
    await settle();

    source.press('meeting');
    await settle();
    expect(events, <String>['start:meeting', 'stop:meeting']);

    await machine.dispose();
  });

  test('auto-repeat dentro do teto continua sendo engolido', () async {
    final machine = build();
    source.press('meeting');
    await settle();
    source.repeat('meeting', 8);
    await settle();

    expect(events, <String>['start:meeting'],
        reason: 'segurar a tecla nao pode virar uma rajada de start/stop');

    await machine.dispose();
  });

  test('um onStart que estoura nao deixa a tecla presa como ativa', () async {
    var attempts = 0;
    final errors = <Object>[];
    late HotkeyMachine machine;

    // O erro sobe para a zona (vira log de crash no app); aqui ele so nao pode matar o teste.
    await runZonedGuarded(() async {
      machine = build(onStart: (action) {
        attempts++;
        if (attempts == 1) throw StateError('motor explodiu');
        events.add('start:$action');
        return true;
      });

      source.press('dictation');
      await settle();
    }, (e, _) => errors.add(e));

    expect(errors, hasLength(1), reason: 'a falha nao pode ser engolida em silencio');
    expect(machine.active, isNull,
        reason: 'com _active preso, todo F9 seguinte e engolido sem nem logar');

    source.release('dictation');
    source.tick();
    await settle();

    source.press('dictation');
    await settle();
    expect(events, contains('start:dictation'));

    await machine.dispose();
  });
}
