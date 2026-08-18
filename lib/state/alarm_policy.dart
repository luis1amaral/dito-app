import '../config/config_model.dart';
import '../engine/engine_protocol.dart';

/// Decides how loudly to complain about a dead microphone, and how often.
///
/// Repeating on every tick turns the alarm into noise people learn to ignore, which is the
/// same as having no alarm.
class AlarmPolicy {
  AlarmPolicy({required this.now});

  /// Microseconds, injectable so tests do not wait.
  final int Function() now;

  static const Duration soundThrottle = Duration(seconds: 10);

  bool _ringing = false;
  int _lastSound = 0;

  bool get isRinging => _ringing;

  /// What to do about this alarm right now.
  AlarmAction evaluate(AlarmEvent event, AlertConfig config) {
    if (event.state != AudioState.dead) {
      _ringing = false;
      return const AlarmAction(sound: false, notify: false);
    }

    final first = !_ringing;
    final elapsed = now() - _lastSound;
    final due = first || elapsed >= soundThrottle.inMicroseconds;
    _ringing = true;

    if (!due) return const AlarmAction(sound: false, notify: false);
    _lastSound = now();

    return AlarmAction(
      sound: config.sound,
      // Only the FIRST of each alarm notifies; the rest would train the user to ignore it.
      notify: config.notify && first,
    );
  }

  void reset() => _ringing = false;
}

class AlarmAction {
  const AlarmAction({required this.sound, required this.notify});

  final bool sound;
  final bool notify;

  bool get isSilent => !sound && !notify;
}
