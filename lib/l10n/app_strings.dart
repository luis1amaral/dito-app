import 'dart:ui' show PlatformDispatcher;

import 'package:flutter/widgets.dart';

import 'app_strings.g.dart';

export 'app_strings.g.dart';

/// Turns the stored preference into a locale; null means "follow the system".
Locale? localeFromCode(String? code) {
  if (code == null || code.isEmpty || code == 'auto') return null;
  return Locale(code.startsWith('pt') ? 'pt' : 'en');
}

/// The code a window sends to its sub-windows, which have no access to the config.
String localeCodeOf(BuildContext context) => Localizations.localeOf(context).languageCode;

/// Catalogue for code with no BuildContext: the tray and the balloon notifications.
AppStrings stringsFor(String? code) {
  final escolhido = localeFromCode(code);
  if (escolhido != null) return lookupAppStrings(escolhido);
  // PlatformDispatcher, not WidgetsBinding: this runs from the controller, with no binding up.
  final sistema = PlatformDispatcher.instance.locale;
  return lookupAppStrings(
      AppStrings.supportedLocales.any((l) => l.languageCode == sistema.languageCode)
          ? Locale(sistema.languageCode)
          : const Locale('en'));
}

extension AppStringsExtension on BuildContext {
  AppStrings get strings => AppStrings.of(this);
}
