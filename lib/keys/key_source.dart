import 'dart:async';

/// What the machine needs from the keyboard: an edge and the physical truth.
///
/// This is the seam that lets the whole state machine be tested without a keyboard.
abstract class KeySource {
  /// Key went down, auto-repeat included.
  Stream<KeyDownSignal> get downs;

  /// Physical state of every bound key, every poll interval.
  Stream<KeyTickSignal> get ticks;

  /// Fires when the hook is lost or reinstalled.
  Stream<bool> get hookAlive;
}

class KeyDownSignal {
  const KeyDownSignal(this.action, this.micros);
  final String action;
  final int micros;
}

class KeyTickSignal {
  const KeyTickSignal(this.down, this.micros);
  final Set<String> down;
  final int micros;
}

/// Test double driving the machine with no keyboard and no real time.
class FakeKeySource implements KeySource {
  final _downs = StreamController<KeyDownSignal>.broadcast();
  final _ticks = StreamController<KeyTickSignal>.broadcast();
  final _hook = StreamController<bool>.broadcast();

  final Set<String> _held = <String>{};
  int _micros = 0;

  @override
  Stream<KeyDownSignal> get downs => _downs.stream;

  @override
  Stream<KeyTickSignal> get ticks => _ticks.stream;

  @override
  Stream<bool> get hookAlive => _hook.stream;

  int get micros => _micros;

  void press(String action) {
    _held.add(action);
    _downs.add(KeyDownSignal(action, _micros));
  }

  /// Auto-repeat: the key never came up, the hardware just says down again.
  void repeat(String action, int times) {
    for (var i = 0; i < times; i++) {
      _downs.add(KeyDownSignal(action, _micros));
    }
  }

  void release(String action) => _held.remove(action);

  /// A wireless keyboard sends a spurious release; the key is still physically down.
  void ghostRelease(String action) {
    _held.remove(action);
    tick();
    _held.add(action);
  }

  void tick() => _ticks.add(KeyTickSignal(Set<String>.from(_held), _micros));

  /// Advances virtual time, emitting one tick per poll interval.
  void elapse(Duration duration, {Duration step = const Duration(milliseconds: 50)}) {
    var remaining = duration.inMicroseconds;
    while (remaining > 0) {
      final chunk = remaining < step.inMicroseconds ? remaining : step.inMicroseconds;
      _micros += chunk;
      remaining -= chunk;
      tick();
    }
  }

  void hookLost() => _hook.add(false);
  void hookInstalled() => _hook.add(true);

  Future<void> dispose() async {
    await _downs.close();
    await _ticks.close();
    await _hook.close();
  }
}
