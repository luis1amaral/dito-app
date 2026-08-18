import 'package:flutter/material.dart';

/// Colour tokens ported 1-to-1 from src/dito/ui/theme.py.

class AppColors {
  final Brightness brightness;

  final Color bg;
  final Color surface;
  final Color surfaceAlt;
  final Color border;
  final Color borderStrong;

  final Color textPrimary;
  final Color textSecondary;
  final Color textMuted;
  final Color textInverse;

  final Color primary;
  final Color primaryHover;
  final Color primaryActive;

  final Color danger;
  final Color dangerHover;
  final Color dangerActive;

  final Color success;
  final Color alert;

  final Color overlayScrim;
  final Color focusRing;

  // HUD (pill overlay) - dark in both themes.
  final Color hudSurface;
  final Color hudText;
  final Color hudMuted;
  final Color hudDanger;
  final Color hudRecording;
  final Color hudAlert;
  final Color hudOk;
  final Color hudWash;
  final Color hudWashStrong;
  final Color hudEdge;
  final Color hudField;
  final Color hudSolidHover;
  final Color hudSolidActive;
  final Color hudOnDanger;
  final Color hudOnDangerMuted;

  const AppColors({
    required this.brightness,
    required this.bg,
    required this.surface,
    required this.surfaceAlt,
    required this.border,
    required this.borderStrong,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.textInverse,
    required this.primary,
    required this.primaryHover,
    required this.primaryActive,
    required this.danger,
    required this.dangerHover,
    required this.dangerActive,
    required this.success,
    required this.alert,
    required this.overlayScrim,
    required this.focusRing,
    required this.hudSurface,
    required this.hudText,
    required this.hudMuted,
    required this.hudDanger,
    required this.hudRecording,
    required this.hudAlert,
    required this.hudOk,
    required this.hudWash,
    required this.hudWashStrong,
    required this.hudEdge,
    required this.hudField,
    required this.hudSolidHover,
    required this.hudSolidActive,
    required this.hudOnDanger,
    required this.hudOnDangerMuted,
  });
}

// ---------------------------------------------------------------------------
// Light palette
// ---------------------------------------------------------------------------

const lightColors = AppColors(
  brightness: Brightness.light,
  bg: Color(0xFFF0F0F2),
  surface: Color(0xFFFFFFFF),
  surfaceAlt: Color(0xFFE8E8EE),
  border: Color(0xFFDCDCE3),
  borderStrong: Color(0xFF8F8F9A),
  textPrimary: Color(0xFF16161A),
  textSecondary: Color(0xFF43434E),
  textMuted: Color(0xFF6B6B7A),
  textInverse: Color(0xFFFFFFFF),
  primary: Color(0xFF4B3BD4),
  primaryHover: Color(0xFF3F31B8),
  primaryActive: Color(0xFF342899),
  danger: Color(0xFFC62A30),
  dangerHover: Color(0xFFAB2126),
  dangerActive: Color(0xFF8F1A1E),
  success: Color(0xFF1F7A4D),
  alert: Color(0xFF8A5A06),
  overlayScrim: Color(0x6B000000),
  focusRing: Color(0xFF4B3BD4),
  hudSurface: Color(0xFF17171C),
  hudText: Color(0xFFF7F7F9),
  hudMuted: Color(0xFFA3A3B2),
  hudDanger: Color(0xFFD02A30),
  hudRecording: Color(0xFFFF6B6F),
  hudAlert: Color(0xFFF0B95C),
  hudOk: Color(0xFF4ECF8F),
  hudWash: Color(0x1AFFFFFF),
  hudWashStrong: Color(0x2EFFFFFF),
  hudEdge: Color(0x59FFFFFF),
  hudField: Color(0x0FFFFFFF),
  hudSolidHover: Color(0xDBFFFFFF),
  hudSolidActive: Color(0xBDFFFFFF),
  hudOnDanger: Color(0xE0FFFFFF),
  hudOnDangerMuted: Color(0xBFFFFFFF),
);

// ---------------------------------------------------------------------------
// Dark palette
// ---------------------------------------------------------------------------

const darkColors = AppColors(
  brightness: Brightness.dark,
  bg: Color(0xFF0E0E13),
  surface: Color(0xFF1B1B21),
  surfaceAlt: Color(0xFF25252E),
  border: Color(0xFF33333E),
  borderStrong: Color(0xFF6C6C77),
  textPrimary: Color(0xFFF5F5F7),
  textSecondary: Color(0xFFC2C2CD),
  textMuted: Color(0xFF8E8E9D),
  textInverse: Color(0xFF16161A),
  primary: Color(0xFF8B7CFF),
  primaryHover: Color(0xFF9C90FF),
  primaryActive: Color(0xFF7E6EF4),
  danger: Color(0xFFFF6B6F),
  dangerHover: Color(0xFFFF8285),
  dangerActive: Color(0xFFE85054),
  success: Color(0xFF4ECF8F),
  alert: Color(0xFFF0B95C),
  overlayScrim: Color(0x99000000),
  focusRing: Color(0xFF8B7CFF),
  hudSurface: Color(0xFF17171C),
  hudText: Color(0xFFF7F7F9),
  hudMuted: Color(0xFFA3A3B2),
  hudDanger: Color(0xFFD02A30),
  hudRecording: Color(0xFFFF6B6F),
  hudAlert: Color(0xFFF0B95C),
  hudOk: Color(0xFF4ECF8F),
  hudWash: Color(0x1AFFFFFF),
  hudWashStrong: Color(0x2EFFFFFF),
  hudEdge: Color(0x59FFFFFF),
  hudField: Color(0x0FFFFFFF),
  hudSolidHover: Color(0xDBFFFFFF),
  hudSolidActive: Color(0xBDFFFFFF),
  hudOnDanger: Color(0xE0FFFFFF),
  hudOnDangerMuted: Color(0xBFFFFFFF),
);

AppColors colorsFor(Brightness brightness) =>
    brightness == Brightness.dark ? darkColors : lightColors;

extension AppColorsExtension on BuildContext {
  AppColors get appColors => colorsFor(Theme.of(this).brightness);
}
