import 'engine_protocol.dart';

/// Decides ok/quiet/dead from the raw level, apart from the engine so the rule can be tested
/// without audio hardware. Red (dead) is reserved for a take that never heard audio at all.
class SilenceAlarm {
  SilenceAlarm({this.deadMs = 700, this.quietMs = 2500, this.tickMs = 50});

  /// Mirrors AlertConfig.deadMs/quietMs (lib/config/config_model.dart).
  final int deadMs;
  final int quietMs;
  final int tickMs;

  /// Anything above this counts as speech; below deadRms counts as no signal at all.
  static const double audibleRms = 0.008;
  static const double deadRms = 0.001;

  /// A device waking up ramps its amplitude up; counting that as silence lit the red pill while
  /// the user was already speaking. Measured in TIME, not in samples: one large first block from
  /// the driver used to clear the old sample-based gate on the first tick.
  static const int warmUpMs = 1200;

  /// The state only flips after this many ticks agreeing, so an RMS dancing around deadRms cannot
  /// produce the dead/quiet flapping seen in the logs (5 changes in under a second).
  static const int stableTicks = 3;

  int _silenceMs = 0;
  int _elapsedMs = 0;
  bool _heardAudio = false;
  AudioState _state = AudioState.ok;
  AudioState? _pending;
  int _pendingTicks = 0;

  AudioState get state => _state;
  bool get heardAudio => _heardAudio;

  void reset() {
    _silenceMs = 0;
    _elapsedMs = 0;
    _heardAudio = false;
    _state = AudioState.ok;
    _pending = null;
    _pendingTicks = 0;
  }

  /// Returns the new state only when it changes, so callers emit on the edge.
  AudioState? update({required double rms, required double bufferedSeconds}) {
    if (bufferedSeconds <= 0) return null;
    _elapsedMs += tickMs;
    if (_elapsedMs <= warmUpMs) {
      // Speech during the warm-up still counts: only the alarm side is held back.
      if (rms > audibleRms) _heardAudio = true;
      return null;
    }

    if (rms > audibleRms) {
      _heardAudio = true;
      _silenceMs = 0;
      return _moveTo(AudioState.ok);
    }

    _silenceMs += tickMs;

    // Once this take has heard speech, silence is the user pausing: never the red alarm.
    if (_heardAudio) {
      return _silenceMs >= quietMs ? _moveTo(AudioState.quiet) : _hold();
    }

    if (rms <= deadRms && _silenceMs >= deadMs) return _moveTo(AudioState.dead);
    if (_silenceMs >= quietMs) return _moveTo(AudioState.quiet);
    return _hold();
  }

  /// A tick that asks for nothing breaks the streak: only consecutive agreement flips the state.
  AudioState? _hold() {
    _pending = null;
    _pendingTicks = 0;
    return null;
  }

  AudioState? _moveTo(AudioState next) {
    if (next == _state) return _hold();
    if (_pending != next) {
      _pending = next;
      _pendingTicks = 1;
      return null;
    }
    if (++_pendingTicks < stableTicks) return null;
    _state = next;
    _pending = null;
    _pendingTicks = 0;
    return next;
  }
}
