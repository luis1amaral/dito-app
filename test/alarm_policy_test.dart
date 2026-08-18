import 'package:dito_app/config/config_model.dart';
import 'package:dito_app/engine/engine_protocol.dart';
import 'package:dito_app/state/alarm_policy.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late int clock;
  late AlarmPolicy policy;
  const alerts = AlertConfig();

  AlarmEvent dead() => const AlarmEvent(state: AudioState.dead, reason: 'mudo');
  AlarmEvent ok() => const AlarmEvent(state: AudioState.ok);

  setUp(() {
    clock = 0;
    policy = AlarmPolicy(now: () => clock);
  });

  test('the first alarm both rings and notifies', () {
    final action = policy.evaluate(dead(), alerts);
    expect(action.sound, isTrue);
    expect(action.notify, isTrue);
  });

  test('a repeat inside the throttle is completely silent', () {
    policy.evaluate(dead(), alerts);
    final again = policy.evaluate(dead(), alerts);
    expect(again.isSilent, isTrue);
  });

  test('after ten seconds it rings again but never notifies again', () {
    policy.evaluate(dead(), alerts);
    clock += 11 * 1000000;
    final again = policy.evaluate(dead(), alerts);

    expect(again.sound, isTrue);
    // Notifying on every tick is what trains people to ignore the alarm.
    expect(again.notify, isFalse);
  });

  test('recovering and failing again counts as a new episode', () {
    policy.evaluate(dead(), alerts);
    policy.evaluate(ok(), alerts);
    clock += 1000000;

    final fresh = policy.evaluate(dead(), alerts);
    expect(fresh.notify, isTrue);
  });

  test('the config can silence each channel on its own', () {
    const muted = AlertConfig(sound: false);
    expect(policy.evaluate(dead(), muted).sound, isFalse);
    expect(policy.evaluate(dead(), muted).notify, isFalse);

    final other = AlarmPolicy(now: () => clock);
    const noPopup = AlertConfig(notify: false);
    final action = other.evaluate(dead(), noPopup);
    expect(action.sound, isTrue);
    expect(action.notify, isFalse);
  });

  test('a quiet alarm is never loud', () {
    final action =
        policy.evaluate(const AlarmEvent(state: AudioState.quiet), alerts);
    expect(action.isSilent, isTrue);
  });
}
