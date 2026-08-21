import 'package:dito_app/state/hud_commands.dart';
import 'package:dito_app/ui/hud/hud_state.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late int clock;
  late HudState state;

  setUp(() {
    clock = 0;
    state = HudState(now: () => clock);
  });

  tearDown(() => state.dispose());

  group('states', () {
    test('recording shows the pill and never flattens the wave', () {
      state.apply(HudMessage.recording(meeting: false));

      expect(state.visual, HudVisual.recording);
      expect(state.isVisible, isTrue);
      expect(state.wave.flat, isFalse);
      expect(state.meeting, isFalse);
    });

    test('a meeting offers a stop action, a dictation does not', () {
      state.apply(HudMessage.recording(meeting: true));
      expect(state.action, HudAction.stop);

      final other = HudState(now: () => clock)
        ..apply(HudMessage.recording(meeting: false));
      expect(other.action, HudAction.none);
      other.dispose();
    });

    test('dead flattens the wave, so the alarm reads without colour', () {
      state.apply(HudMessage.dead('microfone mudo', canFix: true));

      expect(state.visual, HudVisual.dead);
      expect(state.wave.flat, isTrue, reason: 'linha reta = nada chegando');
      expect(state.action, HudAction.fix);
      expect(state.detail, 'microfone mudo');
    });

    test('quiet is its own state, not silence and not dead', () {
      state.apply(HudMessage.quiet('volume baixo'));

      expect(state.visual, HudVisual.quiet);
      expect(state.wave.flat, isFalse);
      expect(state.detail, 'volume baixo');
    });

    test('a fix button only exists when the diagnosis knows the fix', () {
      state.apply(HudMessage.dead('sem sinal', canFix: false));
      expect(state.action, HudAction.none);
    });

    test('working carries the progress as a number, not as a sentence', () {
      state.apply(HudMessage.working(HudWork.minutesDone, minutes: 12));
      expect(state.visual, HudVisual.working);
      // The wording lives in the catalogue; the state must stay language-free.
      expect(state.work, HudWork.minutesDone);
      expect(state.minutes, 12);
    });
  });

  group('entry motion', () {
    test('the pill is on screen as soon as it has a state to show', () {
      state.apply(HudMessage.recording(meeting: false));
      expect(state.isOnScreen, isTrue);
    });

    test('dismissing marks it as leaving before it is hidden', () async {
      state.apply(HudMessage.recording(meeting: false));
      state.dismiss();

      expect(state.isOnScreen, isFalse, reason: 'a saida comeca imediatamente');
      expect(state.visual, isNot(HudVisual.hidden), reason: 'a janela ainda esta la');
    });

    test('showing again after dismissing cancels the exit', () async {
      state.apply(HudMessage.recording(meeting: false));
      state.dismiss();
      state.apply(HudMessage.dead('mudo', canFix: true));

      expect(state.isOnScreen, isTrue);
    });
  });

  group('clock', () {
    test('it is driven by the monotonic clock, not by the engine seconds', () async {
      state.apply(HudMessage.recording(meeting: true));
      clock += 3661 * 1000000;
      await Future<void>.delayed(const Duration(milliseconds: 120));

      // A meeting has no limit, so past an hour it must grow instead of wrapping.
      expect(state.clock.value, '1:01:01');
    });

    test('a toast has no clock at all', () {
      state.apply(HudMessage.toast(HudToast.discarded));
      expect(state.clock.value, '');
    });
  });

  group('level', () {
    test('a level signal never changes the visual state', () {
      state.apply(HudMessage.recording(meeting: false));
      final before = state.visual;
      state.apply(HudMessage.level(0.05));
      expect(state.visual, before);
    });
  });

  group('dismiss', () {
    test('dismiss hides after the exit animation', () async {
      state.apply(HudMessage.recording(meeting: false));
      expect(state.isVisible, isTrue);

      state.apply(HudMessage.dismiss);
      await Future<void>.delayed(const Duration(milliseconds: 300));

      expect(state.visual, HudVisual.hidden);
      expect(state.wave.flat, isFalse, reason: 'o proximo uso comeca limpo');
    });

    test('a toast dismisses itself', () async {
      state.apply(HudMessage.toast(HudToast.copied, ms: 60));
      await Future<void>.delayed(const Duration(milliseconds: 400));
      expect(state.visual, HudVisual.hidden);
    });

    test('a timer that fires after dispose never touches a dead object', () async {
      state.apply(HudMessage.recording(meeting: false));
      state.dismiss();
      state.dispose();
      // The exit timer would fire here; cancelling it in dispose is what keeps this quiet.
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
  });
}
