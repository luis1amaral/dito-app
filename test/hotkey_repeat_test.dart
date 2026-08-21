import 'package:dito_app/state/app_snapshot.dart';
import 'package:flutter_test/flutter_test.dart';

/// The hotkey must keep working recording after recording. What broke in the field: stopping
/// left the app in `transcribing`, and every press until it finished was refused, so F9/F10
/// looked dead after the first use. Transcription runs on its own isolate now, so the phase
/// it leaves behind must not gate the next recording.
void main() {
  group('canStart', () {
    test('a press right after stopping is accepted while the transcript is still running', () {
      const justStopped = AppSnapshot(phase: AppPhase.transcribing);
      expect(justStopped.canStart, isTrue,
          reason: 'this is the refusal that made F9/F10 work only once');
    });

    test('idle and paused keep accepting, as they always did', () {
      expect(const AppSnapshot(phase: AppPhase.idle).canStart, isTrue);
      expect(const AppSnapshot(phase: AppPhase.paused).canStart, isTrue);
    });

    test('an active recording still refuses a second start', () {
      expect(const AppSnapshot(phase: AppPhase.recording).canStart, isFalse,
          reason: 'starting on top of a live recording would drop the audio being captured');
      expect(const AppSnapshot(phase: AppPhase.meeting).canStart, isFalse);
    });

    test('every phase either accepts or refuses on purpose, none left undecided', () {
      for (final phase in AppPhase.values) {
        final snapshot = AppSnapshot(phase: phase);
        final expected = phase != AppPhase.recording && phase != AppPhase.meeting;
        expect(snapshot.canStart, expected, reason: 'phase ${phase.name} decided the wrong way');
      }
    });
  });
}
