import 'package:flutter/material.dart';

import 'palette.dart';
import 'tokens.dart';

ThemeData appTheme(Brightness brightness) {
  final c = colorsFor(brightness);
  return ThemeData(
    brightness: brightness,
    scaffoldBackgroundColor: c.bg,
    colorScheme: ColorScheme(
      brightness: brightness,
      primary: c.primary,
      onPrimary: c.textInverse,
      secondary: c.primary,
      onSecondary: c.textInverse,
      error: c.danger,
      onError: c.textInverse,
      surface: c.surface,
      onSurface: c.textPrimary,
    ),
    cardTheme: CardThemeData(
      color: c.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.card),
        side: BorderSide(color: c.border, width: AppSize.hairline),
      ),
      elevation: 0,
      margin: EdgeInsets.zero,
    ),
    textTheme: TextTheme(
      displayLarge: TextStyle(
          fontSize: AppType.display, fontWeight: FontWeight.w700, color: c.textPrimary),
      titleLarge: TextStyle(
          fontSize: AppType.title, fontWeight: FontWeight.w600, color: c.textPrimary),
      bodyMedium: TextStyle(fontSize: AppType.body, color: c.textPrimary),
      bodySmall: TextStyle(fontSize: AppType.caption, color: c.textSecondary),
      labelSmall: TextStyle(fontSize: AppType.caption, color: c.textMuted),
    ),
    iconTheme: IconThemeData(color: c.textSecondary, size: AppSpacing.xl),
    dividerTheme:
        DividerThemeData(color: c.border, thickness: AppSize.hairline, space: 0),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: c.primary,
        foregroundColor: c.textInverse,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.control)),
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: c.primary,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.control)),
      ),
    ),
  );
}

/// auto follows the desktop and keeps following it when it changes.
ThemeMode themeModeFrom(String setting) => switch (setting) {
      'dark' => ThemeMode.dark,
      'light' => ThemeMode.light,
      _ => ThemeMode.system,
    };
