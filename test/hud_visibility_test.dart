import 'package:dito_app/state/hud_commands.dart';
import 'package:dito_app/ui/hud/hud_state.dart';
import 'package:dito_app/ui/tokens.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

/// The pill is the only thing on screen saying "we are recording". It used to vanish for the
/// rest of the session when a new recording started inside the exit fade of the previous one,
/// and nothing ever brought it back. See CHANGELOG 2026-08-21.
void main() {
  late int clock;

  HudState build({bool animate = false}) => HudState(now: () => clock, animate: animate);

  setUp(() => clock = 0);

  test('uma gravacao nova durante o fade de saida nao e apagada pelo timer velho', () {
    fakeAsync((async) {
      final state = build();
      state.apply(HudMessage.recording(meeting: true));
      expect(state.isOnScreen, isTrue);

      state.apply(HudMessage.dismiss);
      // Dentro dos 180 ms do fade, o F10 seguinte sobe outra gravacao.
      async.elapse(const Duration(milliseconds: 40));
      state.apply(HudMessage.recording(meeting: true));
      expect(state.isOnScreen, isTrue);

      // O timer de saida da sessao anterior venceria aqui.
      async.elapse(AppMotion.fade + const Duration(milliseconds: 40));
      expect(state.isOnScreen, isTrue,
          reason: 'era assim que a pilula sumia e so voltava reiniciando o app');
      expect(state.visual, HudVisual.recording);
      state.dispose();
    });
  });

  test('o nivel de audio religa a pilula que ficou escondida gravando', () {
    fakeAsync((async) {
      final state = build();
      state.apply(HudMessage.recording(meeting: false));
      state.apply(HudMessage.dismiss);
      async.elapse(AppMotion.fade + const Duration(milliseconds: 40));
      expect(state.isOnScreen, isFalse);

      // Level so existe enquanto o motor captura: se ele chega, ha gravacao no ar.
      state.apply(HudMessage.level(0.4));

      expect(state.isOnScreen, isTrue,
          reason: 'nada mais reacende a pilula depois de uma transicao perdida');
      expect(state.visual, HudVisual.recording);
      state.dispose();
    });
  });

  test('o dismiss normal continua escondendo', () {
    fakeAsync((async) {
      final state = build();
      state.apply(HudMessage.recording(meeting: false));
      state.apply(HudMessage.dismiss);
      async.elapse(AppMotion.fade + const Duration(milliseconds: 40));

      expect(state.isOnScreen, isFalse);
      expect(state.visual, HudVisual.hidden);
      state.dispose();
    });
  });

  test('voltar durante o fade reinicia o relogio da sessao nova', () {
    fakeAsync((async) {
      final state = build(animate: true);
      state.apply(HudMessage.recording(meeting: true));
      clock = 95 * 1000000;
      async.elapse(const Duration(seconds: 1));
      expect(state.clock.value, isNot('00:00'));

      state.apply(HudMessage.dismiss);
      async.elapse(const Duration(milliseconds: 40));
      state.apply(HudMessage.recording(meeting: true));
      async.elapse(const Duration(milliseconds: 100));

      expect(state.clock.value, '00:00',
          reason: 'a reuniao nova nao pode nascer com o tempo da anterior');
      state.dispose();
    });
  });
}
