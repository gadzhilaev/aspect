import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Палитра Аспекта. Светлая — Figma; тёмная — читаемые карточки и границы.
abstract final class AppColors {
  static Brightness _brightness = Brightness.light;

  static Brightness get brightness => _brightness;

  static void applyBrightness(Brightness brightness) {
    _brightness = brightness;
  }

  static bool get isDark => _brightness == Brightness.dark;

  /// Яркий бренд (светлая тема / splash).
  static const brandRedLight = Color.fromRGBO(239, 49, 36, 1);

  /// Приглушённый красный для тёмной темы (как плитки в Компании).
  static const brandRedDark = Color(0xFFB83A32);

  /// Акцент: в dark — приглушённый, в light — #EF3124.
  static Color get brandRed => isDark ? brandRedDark : brandRedLight;

  /// Плитки контекста компании.
  static Color get tileRed => brandRed;

  static Color get brandRedBorderSoft => isDark
      ? brandRedDark.withValues(alpha: 0.45)
      : brandRedLight.withValues(alpha: 0.14);

  /// Текст на warning-фоне — читаемый в dark.
  static Color get warningText =>
      isDark ? const Color(0xFFFFC9C4) : brandRedLight;

  static Color get textPrimary =>
      isDark ? const Color(0xFFF2F4F7) : const Color.fromRGBO(0, 0, 0, 1);

  static Color get textSecondary =>
      isDark ? const Color(0xFFB0B8C4) : const Color.fromRGBO(107, 107, 107, 1);

  static Color get textInput =>
      isDark ? const Color(0xFFF0F3F7) : const Color.fromRGBO(24, 35, 44, 1);

  static Color get textInk =>
      isDark ? const Color(0xFFE8ECF1) : const Color.fromRGBO(17, 24, 39, 1);

  static Color get textHint =>
      isDark ? const Color(0xFF7A8494) : const Color.fromRGBO(181, 181, 181, 1);

  static Color get textMuted =>
      isDark ? const Color(0xFF9AA3B0) : const Color.fromRGBO(101, 113, 122, 1);

  static Color get navInactive =>
      isDark ? const Color(0xFF9AA3B0) : const Color.fromRGBO(117, 117, 117, 1);

  static Color get textCaption =>
      isDark ? const Color(0xFF9AA3B0) : const Color.fromRGBO(104, 112, 124, 1);

  static Color get textTertiary =>
      isDark ? const Color(0xFF8A94A3) : const Color.fromRGBO(138, 145, 155, 1);

  /// Фон экрана.
  static Color get surface =>
      isDark ? const Color(0xFF1A1F28) : const Color.fromRGBO(255, 255, 255, 1);

  /// Карточки / приподнятые блоки — заметно светлее фона в dark.
  static Color get surfaceRaised =>
      isDark ? const Color(0xFF2C3440) : const Color.fromRGBO(255, 255, 255, 1);

  static Color get divider =>
      isDark ? const Color(0xFF4A5568) : const Color.fromRGBO(229, 229, 229, 1);

  static Color get border =>
      isDark ? const Color(0xFF5C6A7D) : const Color.fromRGBO(227, 229, 227, 1);

  static Color get progressTrack =>
      isDark ? const Color(0xFF3A4250) : const Color.fromRGBO(217, 217, 217, 1);

  static const impactPurple = Color.fromRGBO(122, 24, 220, 1);

  static Color get tilePurple =>
      isDark ? const Color(0xFF6E35B8) : impactPurple;

  static Color get impactPurpleBright =>
      isDark ? const Color(0xFFA078E0) : impactPurple;

  static const impactGreen = Color.fromRGBO(11, 138, 106, 1);

  static Color get impactGreenBright =>
      isDark ? const Color(0xFF2DD4A8) : impactGreen;

  static Color get warningBg => isDark
      ? brandRedDark.withValues(alpha: 0.22)
      : const Color.fromRGBO(254, 243, 242, 1);

  static Color get warningBorder => isDark
      ? brandRedDark.withValues(alpha: 0.55)
      : const Color.fromRGBO(252, 216, 213, 1);

  static const screenPadding = 16.0;

  static Color get filterChipBorder => isDark
      ? const Color.fromRGBO(255, 255, 255, 0.12)
      : const Color.fromRGBO(101, 113, 122, 0.06);

  static Color get filterChipBg =>
      isDark ? const Color(0xFF2A313C) : const Color.fromRGBO(247, 247, 247, 1);

  static Color get scrollEdge => isDark
      ? const Color.fromRGBO(255, 255, 255, 0.12)
      : const Color.fromRGBO(0, 0, 0, 0.06);

  /// Тёмная «чёрная» плитка (мои данные) — не сливается с фоном.
  static Color get tileDark =>
      isDark ? const Color(0xFF353D4A) : const Color(0xFF000000);

  static SystemUiOverlayStyle get systemOverlay => isDark
      ? const SystemUiOverlayStyle(
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: Brightness.light,
          statusBarBrightness: Brightness.dark,
          systemNavigationBarColor: Color(0xFF1A1F28),
          systemNavigationBarIconBrightness: Brightness.light,
        )
      : const SystemUiOverlayStyle(
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: Brightness.dark,
          statusBarBrightness: Brightness.light,
          systemNavigationBarColor: Color.fromRGBO(255, 255, 255, 1),
          systemNavigationBarIconBrightness: Brightness.dark,
        );
}
