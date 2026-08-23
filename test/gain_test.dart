import 'dart:math' as math;

import 'package:dito_app/engine/native_engine.dart';
import 'package:dito_app/engine/silence_alarm.dart';
import 'package:flutter_test/flutter_test.dart';

/// Headset gain varies wildly between takes; see docs/armadilhas.md 1.7 for the measured numbers.
void main() {
  List<double> tom({required double amplitude, int amostras = 16000}) => <double>[
        for (var i = 0; i < amostras; i++)
          amplitude * math.sin(2 * math.pi * 220 * i / 16000),
      ];

  test('fala fraca e amplificada ate o alvo', () {
    final ganho = NativeEngine.gainFor(tom(amplitude: 0.05));
    expect(ganho, greaterThan(1));
    expect(0.05 * ganho, closeTo(0.35, 0.01),
        reason: 'o alvo e uma fala audivel para o Whisper');
  });

  test('o pior caso medido no headset ainda cabe no teto', () {
    // 23:18 on 08/21: peak 0.010 with the same voice that normally gives 0.068.
    final ganho = NativeEngine.gainFor(tom(amplitude: 0.010));
    expect(0.010 * ganho, greaterThan(SilenceAlarm.audibleRms * 10),
        reason: 'sem isto o Whisper continua sem ouvir a fala do dono');
  });

  test('fala com nivel bom nao e tocada', () {
    expect(NativeEngine.gainFor(tom(amplitude: 0.5)), 1);
    expect(NativeEngine.gainFor(tom(amplitude: 0.35)), 1);
  });

  test('ruido de fundo NAO vira voz por multiplicacao', () {
    // Below the app's own voice threshold: amplifying this only causes Whisper hallucinations.
    expect(NativeEngine.gainFor(tom(amplitude: SilenceAlarm.audibleRms / 2)), 1);
    expect(NativeEngine.gainFor(tom(amplitude: 0.0)), 1);
  });

  test('o ganho tem teto: sinal quase nulo nao e esticado sem limite', () {
    final ganho = NativeEngine.gainFor(tom(amplitude: 0.009), maxGain: 12);
    expect(ganho, lessThanOrEqualTo(12));
  });

  test('lista vazia nao quebra', () {
    expect(NativeEngine.gainFor(<double>[]), 1);
  });
}
