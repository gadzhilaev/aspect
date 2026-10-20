import 'package:flutter/material.dart';

/// Brand font from Figma: Styrene A Web.
abstract final class AppTypography {
  static const family = 'Styrene A Web';

  static TextStyle medium(double size, {Color? color, double height = 1}) {
    return TextStyle(
      fontFamily: family,
      fontWeight: FontWeight.w500,
      fontSize: size,
      height: height,
      letterSpacing: 0,
      color: color,
    );
  }

  static TextStyle regular(double size, {Color? color, double height = 1}) {
    return TextStyle(
      fontFamily: family,
      fontWeight: FontWeight.w400,
      fontSize: size,
      height: height,
      letterSpacing: 0,
      color: color,
    );
  }

  static TextStyle bold(double size, {Color? color, double height = 1}) {
    return TextStyle(
      fontFamily: family,
      fontWeight: FontWeight.w700,
      fontSize: size,
      height: height,
      letterSpacing: 0,
      color: color,
    );
  }
}
