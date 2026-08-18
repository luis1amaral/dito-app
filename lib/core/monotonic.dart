/// Injectable monotonic clock; every grace window and the HUD clock measure through it.
abstract class Clock {
  /// Microseconds from an arbitrary zero: only differences mean anything.
  int get micros;

  const factory Clock.system() = _SystemClock;
}

class _SystemClock implements Clock {
  const _SystemClock();

  @override
  int get micros => _stopwatch.elapsedMicroseconds;
}

final Stopwatch _stopwatch = Stopwatch()..start();

/// Test clock: only moves when told, so grace windows cost no real seconds.
class FakeClock implements Clock {
  FakeClock([this._micros = 0]);

  int _micros;

  @override
  int get micros => _micros;

  void advance(Duration by) => _micros += by.inMicroseconds;
}
