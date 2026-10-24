import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_typography.dart';

/// Wordmark «Альфа Бизнес» с полоской под «А», цвет как у текста кнопки.
class AlfaBusinessMark extends StatelessWidget {
  const AlfaBusinessMark({
    super.key,
    this.height = 13,
    this.color = AppColors.brandRed,
  });

  final double height;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final style = AppTypography.bold(height, color: color).copyWith(
      height: 1,
    );
    final barH = (height * 0.11).clamp(1.2, 2.0);
    final gap = height * 0.08;

    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('А', style: style),
            SizedBox(height: gap),
            Container(
              width: height * 0.7,
              height: barH,
              color: color,
            ),
          ],
        ),
        Transform.translate(
          offset: Offset(0, -(barH + gap) / 2),
          child: Text('льфа Бизнес', style: style),
        ),
      ],
    );
  }
}
