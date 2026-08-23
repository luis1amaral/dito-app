import 'dart:async';

import 'package:dito_app/keys/hotkey_machine.dart';
import 'package:dito_app/keys/key_source.dart';
import 'package:flutter_test/flutter_test.dart';

/// The two ways the machine itself could go deaf until restart: a release the keymap never reported, and a start that threw (CHANGELOG 2026-08-21).
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
    // The key is pressed and the keymap keeps swearing it is still down.
    source.press('meeting');
    await settle();
    expect(events, <String>['start:meeting']);

    source.elapse(kToggleReleaseCeiling + const Duration(milliseconds: 100));
    await settle();

    // Without the ceiling, this second press vanishes with no log and no action — the reported symptom.
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

    // The error bubbles up to the zone (becomes a crash log in the app); here it just must not kill the test.
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
