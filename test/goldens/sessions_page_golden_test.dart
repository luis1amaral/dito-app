@Tags(<String>['golden'])
library;

import 'package:dito_app/config/config_service.dart';
import 'package:dito_app/l10n/app_strings.dart';
import 'package:dito_app/library/library_reader.dart';
import 'package:dito_app/ui/main/sessions_page.dart';
import 'package:dito_app/ui/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Baseline pixels for the sessions list: empty and populated, light and dark.
void main() {
  setUp(() {
    final view = TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(1280, 900);
    view.devicePixelRatio = 1.0;
  });

  tearDown(() {
    TestWidgetsFlutterBinding.instance.platformDispatcher.views.first
      ..resetPhysicalSize()
      ..resetDevicePixelRatio();
  });

  Future<void> show(
    WidgetTester tester, {
    required LibraryReader library,
    required Brightness brightness,
  }) async {
    final config = ConfigService();
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppStrings.localizationsDelegates,
      supportedLocales: AppStrings.supportedLocales,
      locale: const Locale('pt'),
      theme: appTheme(brightness),
      home: Scaffold(
        body: SessionsPage(library: library, config: config),
      ),
    ));
    await tester.pumpAndSettle();
  }

  SessionRef fakeSession(String id, {bool meeting = false, String preview = 'texto ditado'}) =>
      SessionRef(
        id: id,
        started: DateTime(2026, 8, 23, 10, 30),
        mode: meeting ? 'meeting' : 'dictation',
        state: 'done',
        seconds: 42,
        preview: preview,
        jsonPath: 'C:\\lib\\2026\\08\\23\\10-30-00.json',
        hasAudio: false,
        sizeBytes: 1024,
      );

  for (final brightness in Brightness.values) {
    final name = brightness == Brightness.light ? 'light' : 'dark';

    testWidgets('empty ($name)', (tester) async {
      final library = LibraryReader();
      await show(tester, library: library, brightness: brightness);
      await expectLater(
          find.byType(SessionsPage), matchesGoldenFile('sessions_page_empty_$name.png'));
    });

    testWidgets('with sessions ($name)', (tester) async {
      final library = LibraryReader()
        ..sessions = <SessionRef>[
          fakeSession('a', meeting: true, preview: 'ata da reuniao de hoje'),
          fakeSession('b'),
        ]
        ..isLoading = false;
      await show(tester, library: library, brightness: brightness);
      await expectLater(
          find.byType(SessionsPage), matchesGoldenFile('sessions_page_filled_$name.png'));
    });
  }
}
