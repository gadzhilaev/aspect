import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';

class ScenariosTab extends StatelessWidget {
  const ScenariosTab({super.key});

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        24 * s,
      ),
      children: [
        Text('Сценарии', style: pageTitleStyle(context)),
        SizedBox(height: 8 * s),
        Text(
          'Диалоги по важным событиям',
          style: AppTypography.regular(14 * s, color: AppColors.textMuted),
        ),
        SizedBox(height: 14 * s),
        Container(
          height: 50 * s,
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16 * s),
            border: Border.all(color: AppColors.border, width: 1),
          ),
          padding: EdgeInsets.symmetric(horizontal: 16 * s),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  textCapitalization: TextCapitalization.sentences,
                  style: AppTypography.regular(
                    15 * s,
                    color: AppColors.textPrimary,
                  ),
                  cursorColor: AppColors.brandRed,
                  decoration: InputDecoration(
                    isDense: true,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    hintText: 'Поиск по событиям',
                    hintStyle: AppTypography.regular(
                      15 * s,
                      color: AppColors.textHint,
                    ),
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
              ),
              Icon(
                Icons.search,
                color: AppColors.textSecondary,
                size: 22 * s,
              ),
            ],
          ),
        ),
        SizedBox(height: 6 * s),
        const _ScenarioRow(
          accent: AppColors.brandRed,
          title: 'Китай ограничивает экспорт электроники',
          subtitle: 'Аспект: подготовил сценарии для поставок',
          time: '08:24',
          badge: 1,
        ),
        const _ScenarioRow(
          accent: AppColors.impactPurple,
          title: 'Курс CNY вырос на 1,8% за неделю',
          subtitle: 'Аспект: оценил влияние на покупки',
          time: 'Вчера',
        ),
        const _ScenarioRow(
          accent: AppColors.impactGreen,
          title: 'Спрос на электронику в Казахстане растет',
          subtitle: 'Аспект: Возможное окно для роста',
          time: 'Пн',
        ),
      ],
    );
  }
}

class _ScenarioRow extends StatelessWidget {
  const _ScenarioRow({
    required this.accent,
    required this.title,
    required this.subtitle,
    required this.time,
    this.badge,
  });

  final Color accent;
  final String title;
  final String subtitle;
  final String time;
  final int? badge;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Column(
      children: [
        Padding(
          padding: EdgeInsets.symmetric(vertical: 12 * s),
          child: IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  width: 3 * s,
                  decoration: BoxDecoration(
                    color: accent,
                    borderRadius: BorderRadius.circular(2 * s),
                  ),
                ),
                SizedBox(width: 12 * s),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: AppTypography.bold(
                          15 * s,
                          color: AppColors.textInput,
                        ).copyWith(height: 1.25),
                      ),
                      SizedBox(height: 4 * s),
                      Text(
                        subtitle,
                        style: AppTypography.regular(
                          13 * s,
                          color: AppColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(width: 8 * s),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  mainAxisAlignment: MainAxisAlignment.start,
                  children: [
                    Text(
                      time,
                      style: AppTypography.regular(
                        12 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                    if (badge != null) ...[
                      SizedBox(height: 6 * s),
                      Container(
                        width: 22 * s,
                        height: 22 * s,
                        alignment: Alignment.center,
                        decoration: const BoxDecoration(
                          color: AppColors.brandRed,
                          shape: BoxShape.circle,
                        ),
                        child: Text(
                          '$badge',
                          textAlign: TextAlign.center,
                          style: AppTypography.bold(
                            11 * s,
                            color: Colors.white,
                          ).copyWith(height: 1),
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
        ),
        Divider(height: 1 * s, color: AppColors.divider),
      ],
    );
  }
}
