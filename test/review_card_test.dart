import 'package:dito_app/l10n/app_strings.dart';
import 'package:dito_app/ui/review/review_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late List<({String text, bool toVault})> sent;
  late int discards;

  setUp(() {
    // A real desktop screen: the card is 560 wide and grows with the text.
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
    sent = <({String text, bool toVault})>[];
    discards = 0;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppStrings.localizationsDelegates,
      supportedLocales: AppStrings.supportedLocales,
      locale: const Locale('pt'),
      home: Scaffold(
        body: Center(
            child: ReviewCard(
          text: text,
          meeting: meeting,
          onSend: (t, {required toVault}) => sent.add((text: t, toVault: toVault)),
          onDiscard: () => discards++,
        )),
      ),
    ));
    await tester.pumpAndSettle();
  }

  group('keys', () {
    // On Linux the Enter arrives as a text INSERTION, not only as a key (CHANGELOG 1.6.7).
    testWidgets('Enter que chega como texto envia, e nao pula linha', (tester) async {
      await show(tester, 'texto original');
      await tester.enterText(find.byType(TextField), 'texto original\n');
      await tester.pump();

      expect(sent, hasLength(1));
      expect(sent.single.text, 'texto original');
      expect(discards, 0);
      final campo = tester.widget<TextField>(find.byType(TextField));
      expect(campo.controller!.text, isNot(contains('\n')));
    });

    testWidgets('Enter sends exactly what is on screen', (tester) async {
      await show(tester, 'texto original');
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();

      expect(sent, hasLength(1));
      expect(sent.single.text, 'texto original');
      expect(discards, 0);
    });

    testWidgets('edits go along with the send', (tester) async {
      await show(tester, 'texto original');
      await tester.enterText(find.byType(TextField), 'texto editado');
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();

      expect(sent.single.text, 'texto editado');
    });

    testWidgets('Shift+Enter inserts a line and does NOT send', (tester) async {
      await show(tester, 'primeira');
      await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
      await tester.pump();

      expect(sent, isEmpty, reason: 'Shift+Enter e quebra de linha, nao envio');
      expect(discards, 0);
    });

    testWidgets('Tab discards', (tester) async {
      await show(tester, 'texto');
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pump();

      expect(discards, 1);
      expect(sent, isEmpty);
    });

    testWidgets('Esc discards', (tester) async {
      await show(tester, 'texto');
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pump();

      expect(discards, 1);
    });

    testWidgets('an emptied box discards instead of sending nothing', (tester) async {
      await show(tester, 'texto');
      await tester.enterText(find.byType(TextField), '   ');
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();

      expect(sent, isEmpty);
      expect(discards, 1);
    });
  });

  group('obsidian switch', () {
    testWidgets('it starts OFF on every recording', (tester) async {
      await show(tester, 'ata');
      expect(find.text('Obsidian'), findsOneWidget);
      expect(tester.widget<Switch>(find.byType(Switch)).value, isFalse);
    });

    testWidgets('turning it on rides along with the send', (tester) async {
      await show(tester, 'ata', meeting: true);
      await tester.tap(find.byType(Switch));
      await tester.pump();
      expect(tester.widget<Switch>(find.byType(Switch)).value, isTrue);

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(sent.single.toVault, isTrue);
    });

    testWidgets('a second card starts off again, never remembering', (tester) async {
      await show(tester, 'primeira');
      await tester.tap(find.byType(Switch));
      await tester.pump();

      await show(tester, 'segunda');
      expect(tester.widget<Switch>(find.byType(Switch)).value, isFalse);
    });
  });

  group('chrome', () {
    testWidgets('the Obsidian switch is present and the key hints are visible',
        (tester) async {
      await show(tester, 'texto');

      // O switch roxo do Obsidian agora existe (era um toggle de texto escondido).
      expect(find.byType(Switch), findsOneWidget);
      expect(find.byType(FilledButton), findsNothing);
      expect(find.byType(TextButton), findsNothing);
      expect(find.textContaining('Enter envia'), findsOneWidget);
      expect(find.textContaining('Tab descarta'), findsOneWidget);
    });
  });

  group('no scrolling', () {
    testWidgets('a normal text never gets a scrollable editor', (tester) async {
      await show(tester, List<String>.filled(30, 'palavra').join(' '));
      final field = tester.widget<TextField>(find.byType(TextField));
      expect(field.scrollPhysics, isA<NeverScrollableScrollPhysics>());
    });
  });

  group('contrast', () {
    testWidgets('the editor pins a light text colour, never dark on dark',
        (tester) async {
      await show(tester, 'texto para editar');
      final theme = tester.widget<Theme>(
        find.ancestor(of: find.byType(TextField), matching: find.byType(Theme)).first,
      );
      expect(theme.data.colorScheme.onSurface.computeLuminance(), greaterThan(0.5),
          reason: 'o texto do cartao tem que ser claro sobre o fundo escuro');
    });
  });
}
