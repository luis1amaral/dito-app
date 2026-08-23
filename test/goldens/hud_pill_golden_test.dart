@Tags(<String>['golden'])
library;

import 'package:dito_app/l10n/app_strings.dart';
import 'package:dito_app/state/hud_commands.dart';
import 'package:dito_app/ui/hud/hud_pill.dart';
import 'package:dito_app/ui/hud/hud_state.dart';
import 'package:dito_app/ui/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Baseline pixels for every HudVisual, captured before any UI refactor moves a single line.
void main() {
  late HudState state;

  setUp(() => state = HudState(now: () => 0, animate: false));
  tearDown(() => state.dispose());

  Future<void> show(WidgetTester tester) async {
    tester.view
      ..physicalSize = const Size(1920, 1080)
      ..devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        debugShowCheckedModeBanner: false,
        localizationsDelegates: AppStrings.localizationsDelegates,
        supportedLocales: AppStrings.supportedLocales,
        locale: const Locale('pt'),
        home: Scaffold(
          backgroundColor: Colors.transparent,
          body: Center(
            child: ListenableBuilder(
              listenable: state,
              builder: (context, child) => HudPill(state: state, onAction: () {}),
            ),
          ),
        ),
      ),
    );
    await tester.pump(AppMotion.fade);
  }

  testWidgets('recording', (tester) async {
    state.apply(HudMessage.recording(meeting: false));
    await show(tester);
    await expectLater(find.byType(HudPill), matchesGoldenFile('hud_pill_recording.png'));
  });

  testWidgets('quiet', (tester) async {
    state.apply(HudMessage.quiet('fale mais perto'));
    await show(tester);
    await expectLater(find.byType(HudPill), matchesGoldenFile('hud_pill_quiet.png'));
  });

  testWidgets('dead without fix button', (tester) async {
    state.apply(HudMessage.dead('sem sinal', canFix: false));
    await show(tester);
    await expectLater(find.byType(HudPill), matchesGoldenFile('hud_pill_dead_no_fix.png'));
  });

  testWidgets('dead with fix button', (tester) async {
    state.apply(HudMessage.dead('microfone mudo', canFix: true));
    await show(tester);
    await expectLater(find.byType(HudPill), matchesGoldenFile('hud_pill_dead_with_fix.png'));
  });

  testWidgets('working', (tester) async {
    state.apply(HudMessage.working(HudWork.transcribing));
    await show(tester);
    await expectLater(find.byType(HudPill), matchesGoldenFile('hud_pill_working.png'));
  });

  testWidgets('toast', (tester) async {
    state.apply(HudMessage.toast(HudToast.pasted));
    await show(tester);
    await expectLater(find.byType(HudPill), matchesGoldenFile('hud_pill_toast.png'));
    // The toast schedules its own exit; leaving it pending fails the whole test.
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(AppMotion.fade);
  });
}
