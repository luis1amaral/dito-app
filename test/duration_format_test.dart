import 'package:dito_app/core/duration_format.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('formatClock', () {
    test('mm:ss below one hour', () {
      expect(formatClock(0), '00:00');
      expect(formatClock(9), '00:09');
      expect(formatClock(59), '00:59');
      expect(formatClock(60), '01:00');
      expect(formatClock(599), '09:59');
      expect(formatClock(3599), '59:59');
    });

    test('grows to h:mm:ss instead of wrapping, because a meeting has no limit', () {
      expect(formatClock(3600), '1:00:00');
      expect(formatClock(3661), '1:01:01');
      expect(formatClock(36000), '10:00:00');
    });

    test('truncates rather than rounds, so the clock never shows a second early', () {
      expect(formatClock(9.99), '00:09');
    });

    test('never blows up on nonsense input', () {
      expect(formatClock(-5), '00:00');
      expect(formatClock(double.nan), '00:00');
    });
  });
}
