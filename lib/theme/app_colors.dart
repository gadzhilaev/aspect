import 'package:flutter/material.dart';

/// Exact Figma tokens as rgba — no ColorScheme.fromSeed / hex reinterpretation.
abstract final class AppColors {
  /// #EF3124 / rgba(239, 49, 36, 1)
  static const brandRed = Color.fromRGBO(239, 49, 36, 1);

  /// Selected option border: rgba(239, 49, 36, 0.14)
  static const brandRedBorderSoft = Color.fromRGBO(239, 49, 36, 0.14);

  /// #000000 / rgba(0, 0, 0, 1)
  static const textPrimary = Color.fromRGBO(0, 0, 0, 1);

  /// #6B6B6B / rgba(107, 107, 107, 1)
  static const textSecondary = Color.fromRGBO(107, 107, 107, 1);

  /// #18232C / rgba(24, 35, 44, 1)
  static const textInput = Color.fromRGBO(24, 35, 44, 1);

  /// #111827 / rgba(17, 24, 39, 1)
  static const textInk = Color.fromRGBO(17, 24, 39, 1);

  /// #B5B5B5 / rgba(181, 181, 181, 1)
  static const textHint = Color.fromRGBO(181, 181, 181, 1);

  /// #65717A / rgba(101, 113, 122, 1)
  static const textMuted = Color.fromRGBO(101, 113, 122, 1);

  /// #757575 / rgba(117, 117, 117, 1)
  static const navInactive = Color.fromRGBO(117, 117, 117, 1);

  /// #68707C / rgba(104, 112, 124, 1)
  static const textCaption = Color.fromRGBO(104, 112, 124, 1);

  /// #8A919B / rgba(138, 145, 155, 1)
  static const textTertiary = Color.fromRGBO(138, 145, 155, 1);

  /// #FFFFFF / rgba(255, 255, 255, 1)
  static const surface = Color.fromRGBO(255, 255, 255, 1);

  /// #E5E5E5 / rgba(229, 229, 229, 1)
  static const divider = Color.fromRGBO(229, 229, 229, 1);

  /// #E3E5E3 / rgba(227, 229, 227, 1)
  static const border = Color.fromRGBO(227, 229, 227, 1);

  /// #D9D9D9 / rgba(217, 217, 217, 1)
  static const progressTrack = Color.fromRGBO(217, 217, 217, 1);

  /// #7A18DC / rgba(122, 24, 220, 1)
  static const impactPurple = Color.fromRGBO(122, 24, 220, 1);

  /// #0B8A6A / rgba(11, 138, 106, 1)
  static const impactGreen = Color.fromRGBO(11, 138, 106, 1);

  /// #FEF3F2 / rgba(254, 243, 242, 1)
  static const warningBg = Color.fromRGBO(254, 243, 242, 1);

  /// #FCD8D5 / rgba(252, 216, 213, 1)
  static const warningBorder = Color.fromRGBO(252, 216, 213, 1);

  /// Screen horizontal inset from Figma.
  static const screenPadding = 16.0;

  /// Unselected filter chip border: rgba(101, 113, 122, 0.06).
  static const filterChipBorder = Color.fromRGBO(101, 113, 122, 0.06);

  /// Unselected filter chip fill: rgba(247, 247, 247, 1).
  static const filterChipBg = Color.fromRGBO(247, 247, 247, 1);

  /// App bar / nav hairline when content scrolls underneath.
  static const scrollEdge = Color.fromRGBO(0, 0, 0, 0.06);
}
