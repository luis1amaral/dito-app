import 'package:dito_app/keys/hotkey_machine.dart';
import 'package:dito_app/keys/key_source.dart';
import 'package:flutter_test/flutter_test.dart';

/// Mirrors tests/test_hotkeys_core.py, with virtual time instead of real sleeps.
void main() {
  late FakeKeySource source;
  late HotkeyMachine machine;
  late List<String> events;

  const dictation = HotkeyBinding(
      action: 'dictation', key: 'f9', mode: HotkeyMode.hold);
  const meeting = HotkeyBinding(
      action: 'meeting', key: 'f10', mode: HotkeyMode.toggle);

  setUp(() {
    source = FakeKeySource();
    events = <String>[];
    machine = HotkeyMachine(
      source: source,
      onStart: (action) {
        events.add('start:$action');
        return true;
      },
      onStop: (action) => events.add('stop:$action'),
      onRefused: (action, blockedBy) => events.add('refused:$action'),
    )
      ..bind(<HotkeyBinding>[dictation, meeting])
      ..start();
  });

  tearDown(() async {
    await machine.dispose();
    await source.dispose();
  });

  /// Lets the stream deliver before assertions; the machine listens asynchronously.
  Future<void> settle() => Future<void>.delayed(Duration.zero);

  group('hold', () {
    test('start fires immediately on the key going down', () async {
      source.press('dictation');
      await settle();
      expect(events, <String>['start:dictation']);
    });

    test('holding lasts as long as the finger, not the grace window', () async {
      source.press('dictation');
      await settle();
      source.elapse(const Duration(seconds: 3));
      await settle();
      expect(events, <String>['start:dictation'], reason: 'ainda segurando');

      source.release('dictation');
      source.elapse(const Duration(milliseconds: 350));
      await settle();
      expect(events, <String>['start:dictation', 'stop:dictation']);
    });

    test('stop waits the full grace, not a millisecond less', () async {
      source.press('dictation');
      await settle();
      source.release('dictation');

      source.elapse(const Duration(milliseconds: 250));
      await settle();
      expect(events, <String>['start:dictation'], reason: 'cedo demais para parar');

      source.elapse(const Duration(milliseconds: 100));
      await settle();
      expect(events, <String>['start:dictation', 'stop:dictation']);
    });

    test('auto-repeat does not restart the recording', () async {
      source.press('dictation');
      await settle();
      source.repeat('dictation', 30);
      await settle();
      expect(events.where((e) => e == 'start:dictation'), hasLength(1));
    });

    test('a ghost release does not cut the recording in two', () async {
      source.press('dictation');
      await settle();
      source.elapse(const Duration(milliseconds: 500));

      // Wireless keyboards emit a spurious release; the finger never left.
      source.ghostRelease('dictation');
      source.elapse(const Duration(milliseconds: 500));
      await settle();
      expect(events, <String>['start:dictation'], reason: 'a mesma gravacao continua');

      source.release('dictation');
      source.elapse(const Duration(milliseconds: 350));
      await settle();
      expect(events, <String>['start:dictation', 'stop:dictation']);
    });

    test('a short tap still yields exactly one start and one stop', () async {
      source.press('dictation');
      await settle();
      source.elapse(const Duration(milliseconds: 100));
      source.release('dictation');
      source.elapse(const Duration(milliseconds: 350));
      await settle();
      expect(events, <String>['start:dictation', 'stop:dictation']);
    });
  });

  group('toggle', () {
    test('one press starts, a second press stops', () async {
      source.press('meeting');
      await settle();
      expect(events, <String>['start:meeting']);

      source.release('meeting');
      source.elapse(const Duration(milliseconds: 350));
      source.press('meeting');
      await settle();
      expect(events, <String>['start:meeting', 'stop:meeting']);
    });

    test('holding the toggle for 1.5 s yields ONE start, not seventeen pairs', () async {
      source.press('meeting');
      await settle();
      // Measured on the Python side before the fix: 35 events, 17 start/stop pairs.
      source.repeat('meeting', 34);
      source.elapse(const Duration(milliseconds: 1500));
      await settle();
      expect(events, <String>['start:meeting']);
    });

    test('a toggle cannot fire again until the keymap says the key came up', () async {
      source.press('meeting');
      await settle();
      source.repeat('meeting', 5);
      await settle();
      expect(events, <String>['start:meeting']);

      source.release('meeting');
      source.elapse(const Duration(milliseconds: 100));
      source.press('meeting');
      await settle();
      expect(events, <String>['start:meeting', 'stop:meeting']);
    });
  });

  group('arbitration', () {
    test('a second action is refused OUT LOUD while another one is running', () async {
      source.press('dictation');
      await settle();
      source.press('meeting');
      await settle();
      expect(events, <String>['start:dictation', 'refused:meeting']);
    });

    test('a hold pressed during a toggle is refused, not silently eaten', () async {
      source.press('meeting');
      await settle();
      source.press('dictation');
      await settle();
      expect(events, <String>['start:meeting', 'refused:dictation']);
    });

    test('a start the controller refuses leaves the machine free', () async {
      final localSource = FakeKeySource();
      final localEvents = <String>[];
      var accept = false;
      final localMachine = HotkeyMachine(
        source: localSource,
        onStart: (a) {
          localEvents.add('start:$a');
          return accept;
        },
        onStop: (a) => localEvents.add('stop:$a'),
      )
        ..bind(<HotkeyBinding>[dictation, meeting])
        ..start();

      localSource.press('meeting');
      await settle();
      expect(localMachine.active, isNull, reason: 'recusa não pode marcar ativo');

      accept = true;
      localSource.release('meeting');
      localSource.elapse(const Duration(milliseconds: 350));
      localSource.press('meeting');
      await settle();
      expect(localEvents, <String>['start:meeting', 'start:meeting']);
      expect(localMachine.active, 'meeting', reason: 'aceite no primeiro toque seguinte');

      await localMachine.dispose();
      await localSource.dispose();
    });

    test('dispatch is by action name, not by key code', () async {
      source.press('meeting');
      await settle();
      expect(events, <String>['start:meeting']);
      expect(machine.active, 'meeting');
    });
  });

  group('pause', () {
    test('pause discards and resume brings it back', () async {
      machine.pause();
      source.press('dictation');
      await settle();
      expect(events, isEmpty);

      machine.resume();
      source.press('dictation');
      await settle();
      expect(events, <String>['start:dictation']);
    });
  });

  group('shutdown', () {
    test('leaving with the key held FINISHES the recording', () async {
      source.press('dictation');
      await settle();
      machine.shutdown();
      expect(events, <String>['start:dictation', 'stop:dictation']);
    });

    test('shutting down with nothing running emits nothing', () async {
      machine.shutdown();
      expect(events, isEmpty);
    });
  });

  group('hold ceiling', () {
    test('a stuck key stops on its own instead of recording forever', () async {
      final ceilingHits = <String>[];
      final localSource = FakeKeySource();
      final localEvents = <String>[];
      final localMachine = HotkeyMachine(
        source: localSource,
        onStart: (a) {
          localEvents.add('start:$a');
          return true;
        },
        onStop: (a) => localEvents.add('stop:$a'),
        holdCeiling: const Duration(seconds: 2),
        onCeilingReached: ceilingHits.add,
      )
        ..bind(<HotkeyBinding>[dictation])
        ..start();

      localSource.press('dictation');
      await settle();
      // The key is never released: UAC or a locked session ate the key-up.
      localSource.elapse(const Duration(seconds: 3));
      await settle();

      expect(localEvents, <String>['start:dictation', 'stop:dictation']);
      expect(ceilingHits, <String>['dictation']);

      await localMachine.dispose();
      await localSource.dispose();
    });
  });

  group('conflicts', () {
    test('names the action a key already answers to', () {
      expect(machine.conflictFor('f9'), 'dictation');
      expect(machine.conflictFor('f10'), 'meeting');
      expect(machine.conflictFor('f7'), isNull);
      expect(machine.conflictFor('f9', ignoreAction: 'dictation'), isNull);
    });
  });
}
