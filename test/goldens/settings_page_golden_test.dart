@Tags(<String>['golden'])
library;

import 'package:dito_app/app/boot.dart';
import 'package:dito_app/l10n/app_strings.dart';
import 'package:dito_app/ui/main/settings_page.dart';
import 'package:dito_app/ui/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// Baseline pixels for the settings page, light and dark. DitoApp is built but never
/// started(): every field it touches at build time is safe to construct without a platform.
void main() {
  const keysChannel = EventChannel('dito/keys');
  const prefsChannel = MethodChannel('plugins.flutter.io/shared_preferences');

  setUp(() {
    PackageInfo.setMockInitialValues(
      appName: 'Dito',
      packageName: 'dito',
      version: '1.6.9',
      buildNumber: '1',
      buildSignature: '',
    );
    // DitoApp() wires the real key hook eagerly; without a mock, listen() reports a
    // MissingPluginException through FlutterError, not through the stream's onError.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockStreamHandler(
      keysChannel,
      MockStreamHandler.inline(onListen: (args, events) {}),
    );
    // Avoids importing shared_preferences just for setMockInitialValues (depend_on_referenced_packages).
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(prefsChannel, (call) async {
      if (call.method == 'getAll') return <String, Object>{};
      return true;
    });

    final view = TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(1280, 1400);
    view.devicePixelRatio = 1.0;
  });

  tearDown(() {
    TestWidgetsFlutterBinding.instance.platformDispatcher.views.first
      ..resetPhysicalSize()
      ..resetDevicePixelRatio();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockStreamHandler(keysChannel, null);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(prefsChannel, null);
  });

  Future<void> show(WidgetTester tester, Brightness brightness) async {
    final app = DitoApp();
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppStrings.localizationsDelegates,
      supportedLocales: AppStrings.supportedLocales,
      locale: const Locale('pt'),
      theme: appTheme(brightness),
      home: Scaffold(body: SettingsPage(app: app)),
    ));
    await tester.pumpAndSettle();
  }

  for (final brightness in Brightness.values) {
    final name = brightness == Brightness.light ? 'light' : 'dark';

    testWidgets(name, (tester) async {
      await show(tester, brightness);
      await expectLater(
          find.byType(SettingsPage), matchesGoldenFile('settings_page_$name.png'));
    });
  }
}
