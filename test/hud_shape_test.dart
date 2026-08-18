import 'package:dito_app/l10n/app_strings.dart';
import 'package:dito_app/state/hud_commands.dart';
import 'package:dito_app/ui/hud/hud_pill.dart';
import 'package:dito_app/ui/hud/hud_state.dart';
import 'package:dito_app/ui/tokens.dart';
import 'package:dito_app/ui/widgets/floating_surface.dart';
import 'package:dito_app/ui/widgets/waveform.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Geometry of the pill: the shadow margin on all four sides is what keeps the base from
/// being clipped, which the user saw as "a line underneath".
void main() {
  late HudState state;

  setUp(() => state = HudState(now: () => 0, animate: false));
  tearDown(() => state.dispose());

  Future<void> show(WidgetTester tester, {Locale locale = const Locale('pt')}) async {
    tester.view
      ..physicalSize = const Size(1920, 1080)
      ..devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        debugShowCheckedModeBanner: false,
        localizationsDelegates: AppStrings.localizationsDelegates,
        supportedLocales: AppStrings.supportedLocales,
        locale: locale,
        home: Scaffold(
          backgroundColor: Colors.transparent,
          // The pill is stateless and repaints off the frame counter, which is frozen here;
          // the real window rebuilds it from the state listener, so the test does the same.
          body: Center(
            child: ListenableBuilder(
              listenable: state,
              builder: (_, _) => HudPill(state: state, onAction: () {}),
            ),
          ),
        ),
      ),
    );
    await tester.pump(AppMotion.fade);
  }

  group('shadow margin', () {
    testWidgets('the surface reserves the margin on all four sides', (tester) async {
      state.apply(HudMessage.recording(meeting: false));
      await show(tester);

      final outer = tester.getRect(find.byType(FloatingSurface));
      // The surface pads its child by exactly the shadow margin on every side.
      final surface = tester.widget<FloatingSurface>(find.byType(FloatingSurface));
      final inner = tester.getRect(find.byWidget(surface.child));

      expect(inner.left - outer.left, closeTo(AppShadow.margin, 0.5));
      expect(outer.right - inner.right, closeTo(AppShadow.margin, 0.5));
      expect(inner.top - outer.top, closeTo(AppShadow.margin, 0.5));
      // A clipped base shows up right here: the body would touch the outer bottom edge.
      expect(outer.bottom - inner.bottom, closeTo(AppShadow.margin, 0.5),
          reason: 'a margem de baixo e a que o usuario viu cortada');
    });

    testWidgets('there is body left beyond the two margins', (tester) async {
      state.apply(HudMessage.recording(meeting: false));
      await show(tester);

      final outer = tester.getRect(find.byType(FloatingSurface));
      expect(outer.height, greaterThan(AppShadow.margin * 2));
      expect(outer.width, greaterThan(AppShadow.margin * 2));
    });
  });

  group('the alarm reads without colour', () {
    testWidgets('no audio flattens the wave, recording keeps the bars', (tester) async {
      state.apply(HudMessage.recording(meeting: false));
      await show(tester);
      expect(state.wave.flat, isFalse);
      expect(find.byType(Waveform), findsOneWidget);

      state.apply(HudMessage.dead('microfone mudo', canFix: true));
      await tester.pump();

      // Shape alone separates them: someone who cannot see red still gets the signal.
      expect(state.wave.flat, isTrue, reason: 'sem audio a onda vira uma linha reta');
      expect(find.byType(Waveform), findsOneWidget);
    });

    testWidgets('the fix button only exists when the diagnosis knows the fix',
        (tester) async {
      state.apply(HudMessage.dead('sem sinal', canFix: false));
      await show(tester);
      expect(find.text('Corrigir'), findsNothing);

      state.apply(HudMessage.dead('mudo', canFix: true));
      await tester.pump();
      expect(find.text('Corrigir'), findsOneWidget);
    });

    testWidgets('prolonged silence goes red like no-audio, but keeps its live wave',
        (tester) async {
      state.apply(HudMessage.quiet('fale mais perto'));
      await show(tester);
      final quietFill =
          tester.widget<FloatingSurface>(find.byType(FloatingSurface)).fill;
      // Audio still arrives, only low: the wave stays alive, unlike dead's flat line.
      expect(state.wave.flat, isFalse);

      state.apply(HudMessage.dead('mudo', canFix: false));
      await tester.pump();
      final deadFill =
          tester.widget<FloatingSurface>(find.byType(FloatingSurface)).fill;

      expect(quietFill, deadFill,
          reason: 'silencio prolongado grita em vermelho igual sem audio');
    });
  });

  group('transcribing', () {
    testWidgets('the bar has real size, not just a widget in the tree', (tester) async {
      state.apply(HudMessage.working(HudWork.transcribing));
      await show(tester);

      // The defect was a childless CustomPaint with no size: present, laid out at zero.
      final size = tester.getSize(find.byKey(workingBarKey));
      expect(size.width, greaterThan(0));
      expect(size.height, AppSize.workingBarHeight);
    });

    testWidgets('the wave gives way to the bar', (tester) async {
      state.apply(HudMessage.working(HudWork.transcribing));
      await show(tester);
      expect(find.byType(Waveform), findsNothing);
      expect(find.byKey(workingBarKey), findsOneWidget);
    });
  });

  group('no state inherits the previous button', () {
    testWidgets('quiet during dictation has no stop button', (tester) async {
      state.apply(HudMessage.recording(meeting: true));
      await show(tester);
      expect(find.text('Parar'), findsOneWidget);

      state.apply(HudMessage.recording(meeting: false));
      state.apply(HudMessage.quiet('fale mais perto'));
      await tester.pump();
      expect(find.text('Parar'), findsNothing);
    });

    testWidgets('quiet during a meeting keeps it', (tester) async {
      state.apply(HudMessage.recording(meeting: true));
      state.apply(HudMessage.quiet('fale mais perto'));
      await show(tester);
      expect(find.text('Parar'), findsOneWidget);
    });
  });

  group('language', () {
    testWidgets('the pill speaks the locale it was given', (tester) async {
      state.apply(HudMessage.recording(meeting: true));
      await show(tester, locale: const Locale('en'));
      expect(find.text('Recording'), findsOneWidget);
      expect(find.text('Stop'), findsOneWidget);
      expect(find.text('Gravando'), findsNothing);
    });

    testWidgets('every toast has wording in both catalogues', (tester) async {
      for (final aviso in HudToast.values) {
        state.apply(HudMessage.toast(aviso));
        await show(tester, locale: const Locale('en'));
        final textos = tester.widgetList<Text>(find.byType(Text)).map((t) => t.data);
        expect(textos.any((t) => t != null && t.isNotEmpty), isTrue,
            reason: 'o aviso ${aviso.name} nao tem texto em ingles');
        // The toast schedules its own exit; leaving it pending fails the whole test.
        await tester.pump(const Duration(seconds: 2));
        await tester.pump(AppMotion.fade);
      }
    });
  });

  group('text', () {
    testWidgets('both modes say the same thing: there is no "meeting"', (tester) async {
      state.apply(HudMessage.recording(meeting: false));
      await show(tester);
      expect(find.text('Gravando'), findsOneWidget);

      state.apply(HudMessage.recording(meeting: true));
      await tester.pump();
      expect(find.text('Gravando'), findsOneWidget);
      expect(find.textContaining('euni'), findsNothing);
    });

    testWidgets('nothing on screen uses a glyph a system font may lack', (tester) async {
      state.apply(HudMessage.dead('microfone mudo', canFix: true));
      await show(tester);

      for (final text in tester.widgetList<Text>(find.byType(Text))) {
        final value = text.data ?? '';
        for (final rune in value.runes) {
          // Accented letters are fine; typographic and box glyphs drew as squares.
          expect(rune, lessThan(0x2000),
              reason: 'U+${rune.toRadixString(16)} em "$value" pode nao ter glifo');
        }
      }
    });
  });
}
