import 'package:flutter/material.dart';

/// Figma frame reference: 393×852.
const double kDesignWidth = 393;

double designScale(BuildContext context) {
  final width = MediaQuery.sizeOf(context).width;
  return (width / kDesignWidth).clamp(1.12, 1.45);
}

double ds(BuildContext context, double px) => px * designScale(context);

extension DesignScaleContext on BuildContext {
  double get scale => designScale(this);

  double ds(double px) => px * scale;
}
