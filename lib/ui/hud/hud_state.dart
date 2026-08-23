import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../../core/duration_format.dart';
import '../../motion/waveform_model.dart';
import '../../state/hud_commands.dart';
import '../tokens.dart';

enum HudVisual { hidden, recording, quiet, dead, working, toast }

/// Everything the HUD window owns; the main window sends signals, this decides nothing else.
class HudState extends ChangeNotifier {
  HudState({this.now = _defaultNow, this.animate = true});

  /// False freezes the clock and the wave: a repeating timer never lets a widget test settle.
  final bool animate;

  static int _defaultNow() => DateTime.now().microsecondsSinceEpoch;

  /// Injectable so tests do not wait on wall time.
  final int Function() now;

  final WaveformModel wave = WaveformModel();

  HudVisual visual = HudVisual.hidden;
  String? detail;
  bool meeting = false;

  /// Role, not wording: the pill resolves every one of these against the ARB catalogue.
  HudAction action = HudAction.none;
  HudToast toast = HudToast.pasted;
  HudWork work = HudWork.transcribing;
  int minutes = 0;

  /// Repaint signal for the painters; ticks at 50 ms while visible.
  final ValueNotifier<int> frame = ValueNotifier<int>(0);

  /// The clock text, which only notifies when the string actually changes.
  final ValueNotifier<String> clock = ValueNotifier<String>('');

  Timer? _ticker;
  Timer? _exitTimer;
  bool _disposed = false;
  bool _leaving = false;
  int _startedAt = 0;
  int _shakeUntil = 0;
  double _shakePhase = 0;
  double _shakeOffset = 0;
  Timer? _toastTimer;

  /// The pill fades rather than slides, because translating inside a window sized to the content clips its base.
  bool get isOnScreen => visual != HudVisual.hidden && !_leaving;
  double get shake => _shakeOffset;
  bool get isVisible => visual != HudVisual.hidden;

  double dotPhase() {
    final elapsed = (now() - _startedAt) / 1000000.0;
    return (elapsed / AppMotion.dotPeriodSeconds) % 1.0;
  }

  void apply(HudMessage message) {
    switch (message.kind) {
      case HudKind.recording:
        meeting = message.meeting;
        _enter(HudVisual.recording);
        detail = null;
        action = meeting ? HudAction.stop : HudAction.none;
        wave.flat = false;
      case HudKind.quiet:
        _enter(HudVisual.quiet);
        detail = message.reason;
        // Stated, never inherited: a leftover action from the previous state is a stray button.
        action = meeting ? HudAction.stop : HudAction.none;
        wave.flat = false;
      case HudKind.dead:
        _enter(HudVisual.dead);
        detail = message.reason;
        action = message.canFix ? HudAction.fix : HudAction.none;
        // A flat line reads as "nothing is arriving" even with no colour at all.
        wave.flat = true;
        _shake();
      case HudKind.working:
        _enter(HudVisual.working);
        work = message.work;
        minutes = message.minutes;
        detail = null;
        action = HudAction.none;
        wave.flat = false;
      case HudKind.toast:
        _enter(HudVisual.toast);
        toast = message.toastKind;
        detail = message.detail;
        action = HudAction.none;
        clock.value = '';
        _toastTimer?.cancel();
        _toastTimer = Timer(Duration(milliseconds: message.ms), () {
          if (visual == HudVisual.toast) dismiss();
        });
      case HudKind.level:
        wave.push(message.rms);
        // Level only exists while the engine captures: a hidden pill here is out of sync and nothing else brings it back (CHANGELOG 2026-08-21).
        if (!isOnScreen) {
          _enter(HudVisual.recording);
          detail = null;
          action = meeting ? HudAction.stop : HudAction.none;
          wave.flat = false;
          break;
        }
        return;
      case HudKind.dismiss:
        dismiss();
        return;
    }
    notifyListeners();
  }

  void _enter(HudVisual next) {
    // Coming back mid-fade is a new session: the clock and the wave restart with it.
    final wasHidden = visual == HudVisual.hidden || _leaving;
    // A pending exit from the previous session would hide this one 180 ms after it appeared.
    _exitTimer?.cancel();
    _exitTimer = null;
    visual = next;
    _leaving = false;
    if (wasHidden) {
      _startedAt = now();
      wave.reset();
      _startTicker();
    }
  }

  void _shake() {
    _shakeUntil = now() + AppMotion.shake.inMicroseconds;
    _shakePhase = 0;
  }

  void _startTicker() {
    if (!animate) return;
    _ticker?.cancel();
    _ticker = Timer.periodic(AppMotion.tick, (_) => _onTick());
  }

  void _onTick() {
    wave.tick();

    if (visual == HudVisual.recording ||
        visual == HudVisual.quiet ||
        visual == HudVisual.dead) {
      // Monotonic, not the engine's seconds: a meeting has no limit and must not wrap.
      clock.value = formatClock((now() - _startedAt) / 1000000.0);
    }

    final remaining = _shakeUntil - now();
    if (remaining > 0) {
      final fraction = remaining / AppMotion.shake.inMicroseconds;
      _shakeOffset = AppMotion.shakePixels * fraction * _sin(_shakePhase);
      _shakePhase += 0.9;
    } else if (_shakeOffset != 0) {
      _shakeOffset = 0;
    }

    frame.value++;
  }

  static double _sin(double radians) => math.sin(radians);

  void dismiss() {
    if (_disposed) return;
    _toastTimer?.cancel();
    _exitTimer?.cancel();
    _leaving = true;
    notifyListeners();
    // Held so dispose can cancel it: a timer that fires after dispose notifies a dead object.
    _exitTimer = Timer(AppMotion.fade, () {
      if (_disposed) return;
      _ticker?.cancel();
      _ticker = null;
      visual = HudVisual.hidden;
      wave.reset();
      wave.flat = false;
      clock.value = '';
      notifyListeners();
    });
  }

  @override
  void dispose() {
    // Idempotent: the window and its owner can both reach for it on the way down.
    if (_disposed) return;
    _disposed = true;
    _ticker?.cancel();
    _toastTimer?.cancel();
    _exitTimer?.cancel();
    frame.dispose();
    clock.dispose();
    super.dispose();
  }
}
