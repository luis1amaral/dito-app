@Tags(<String>['golden'])
library;

import 'package:dito_app/l10n/app_strings.dart';
import 'package:dito_app/ui/review/review_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Baseline pixels for the review card: short, three lines, long text and meeting mode.
void main() {
  setUp(() {
    final view = TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(1920, 1080);
    view.devicePixelRatio = 1.0;
  });

  tearDown(() {
    TestWidgetsFlutterBinding.instance.platformDispatcher.views.first
      ..resetPhysicalSize()
      ..resetDevicePixelRatio();
  });

  Future<void> show(WidgetTester tester, String text, {bool meeting = false}) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppStrings.localizationsDelegates,
      supportedLocales: AppStrings.supportedLocales,
      locale: const Locale('pt'),
      home: Scaffold(
        body: Center(
          child: ReviewCard(
            text: text,
            meeting: meeting,
            onSend: (t, {required toVault}) {},
            onDiscard: () {},
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('short text', (tester) async {
    await show(tester, 'texto curto');
    await expectLater(find.byType(ReviewCard), matchesGoldenFile('review_card_short.png'));
  });

  testWidgets('three lines', (tester) async {
    await show(tester,
        'primeira linha de um texto ditado que segue por mais um pouco de conteudo\n'
        'segunda linha continuando a mesma ideia sem parar de todo\n'
        'terceira linha fechando o pensamento por aqui');
    await expectLater(
        find.byType(ReviewCard), matchesGoldenFile('review_card_three_lines.png'));
  });

  testWidgets('long text', (tester) async {
    await show(tester, List<String>.filled(60, 'palavra').join(' '));
    await expectLater(find.byType(ReviewCard), matchesGoldenFile('review_card_long.png'));
  });

  testWidgets('meeting', (tester) async {
    await show(tester, 'ata da reuniao de hoje', meeting: true);
    await expectLater(find.byType(ReviewCard), matchesGoldenFile('review_card_meeting.png'));
  });
}
