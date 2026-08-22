import 'package:dito_app/engine/engine_protocol.dart';
import 'package:dito_app/engine/silence_alarm.dart';
import 'package:flutter_test/flutter_test.dart';

/// Red used to fire after 700ms of silence, so pausing to breathe looked like a dead mic --
/// and the cleaner the microphone, the faster the false alarm. Red now means one thing only:
/// this take never heard audio at all.
void main() {
  late SilenceAlarm alarm;

  setUp(() => alarm = SilenceAlarm());

  /// Feeds `ms` worth of ticks at one level and returns every state change seen.
  List<AudioState> feed(double rms, int ms, {double seconds = 1}) {
    final changes = <AudioState>[];
    for (var elapsed = 0; elapsed < ms; elapsed += alarm.tickMs) {
      final next = alarm.update(rms: rms, bufferedSeconds: seconds);
      if (next != null) changes.add(next);
    }
    return changes;
  }

  test('a mic that never captures anything goes red', () {
    // Depois do aquecimento (warmUpMs), que existe porque o device sobe a amplitude aos poucos.
    expect(feed(0.0, 3000), contains(AudioState.dead));
  });

  test('pausing after speaking never goes red, however long the pause', () {
    feed(0.05, 500);
    expect(alarm.heardAudio, isTrue);
    expect(feed(0.0, 30000), isNot(contains(AudioState.dead)),
        reason: 'a pause is a pause: red is reserved for a take that heard nothing');
  });

  test('a clean mic pausing does not go red either, even below the dead floor', () {
    feed(0.05, 300);
    // A good headset drops under deadRms between words; that used to fire dead in 700ms.
    expect(feed(0.0005, 5000), isNot(contains(AudioState.dead)));
  });

  test('speaking again clears the warning', () {
    feed(0.05, 200);
    // Silencio suficiente para passar do aquecimento E do quietMs, senao nem chega a avisar.
    feed(0.0, 6000);
    expect(feed(0.05, 200), contains(AudioState.ok));
  });

  test('a device still waking up is not silence', () {
    expect(feed(0.0, 5000, seconds: 0), isEmpty,
        reason: 'no audio buffered yet means no data, not a dead mic');
  });

  test('each state is announced once, not on every tick', () {
    final changes = feed(0.0, 10000);
    expect(changes.where((s) => s == AudioState.dead).length, 1);
  });

  test('reset forgets the previous take', () {
    feed(0.05, 200);
    expect(alarm.heardAudio, isTrue);
    alarm.reset();
    expect(alarm.heardAudio, isFalse);
    expect(alarm.state, AudioState.ok);
    expect(feed(0.0, 3000), contains(AudioState.dead));
  });

  test('o aquecimento nao acusa mic morto enquanto o device sobe a amplitude', () {
    expect(feed(0.0, SilenceAlarm.warmUpMs - 100), isEmpty,
        reason: 'o triangulo vermelho aparecia com o dono ja falando');
  });

  test('nivel oscilando em torno do piso nao gera pisca-pisca dead/quiet', () {
    // Caso real do log: 5 trocas de estado em menos de 1s com o RMS dancando sobre deadRms.
    feed(0.0, 4000);
    final changes = <AudioState>[];
    for (var i = 0; i < 40; i++) {
      final next = alarm.update(rms: i.isEven ? 0.0009 : 0.0011, bufferedSeconds: 1);
      if (next != null) changes.add(next);
    }
    expect(changes, isEmpty,
        reason: 'sem histerese isso alternava dead/quiet a cada tick de 50ms');
  });

  test('fala dentro do aquecimento conta: a pausa seguinte nao vira vermelho', () {
    feed(0.05, 300);
    expect(alarm.heardAudio, isTrue);
    expect(feed(0.0, 10000), isNot(contains(AudioState.dead)));
  });
}
