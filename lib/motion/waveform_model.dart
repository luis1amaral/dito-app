import 'dart:math' as math;

import '../ui/tokens.dart';

/// The 13 bars of the HUD wave, as data: no widgets, so it can be tested and painted cheaply.
class WaveformModel {
  WaveformModel({int bars = AppSize.waveBars})
      : _values = List<double>.filled(bars, 0),
        _targets = List<double>.filled(bars, 0);

  final List<double> _values;
  final List<double> _targets;

  List<double> get values => List<double>.unmodifiable(_values);

  /// Flat means dead: a straight line reads as "nothing is coming in" without needing colour.
  bool flat = false;

  /// Compressed scale, because speech RMS sits between 0.02 and 0.10 and linear would leave
  /// the bars invisible exactly when everything works.
  static double levelFor(double rms) =>
      math.min(1.0, math.sqrt(math.max(0.0, rms) * AppMotion.waveGain));

  /// Newest level enters on the right; the rest shifts left.
  void push(double rms) {
    final level = levelFor(rms);
    for (var i = 0; i < _targets.length - 1; i++) {
      _targets[i] = _targets[i + 1];
    }
    _targets[_targets.length - 1] = level;
  }

  /// Eases towards the targets; one call per frame.
  void tick() {
    for (var i = 0; i < _values.length; i++) {
      _values[i] += (_targets[i] - _values[i]) * AppMotion.waveEasing;
    }
  }

  void reset() {
    for (var i = 0; i < _values.length; i++) {
      _values[i] = 0;
      _targets[i] = 0;
    }
  }

  /// Bar height in logical pixels, floor included.
  double heightAt(int index) =>
      math.max(AppSize.waveMinHeight, _values[index] * (AppSize.waveHeight - 4));
}
