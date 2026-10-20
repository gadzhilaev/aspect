import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

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
        Text(
          'Сценарии',
          style: AppTypography.bold(28 * s, color: AppColors.textPrimary)
              .copyWith(letterSpacing: -0.4, height: 1.15),
        ),
        SizedBox(height: 8 * s),
        Text(
          'Диалоги по важным событиям',
          style: AppTypography.regular(14 * s, color: AppColors.textMuted),
        ),
        SizedBox(height: 18 * s),
        TextField(
          style: AppTypography.regular(15 * s, color: AppColors.textPrimary),
          decoration: InputDecoration(
            hintText: 'Поиск по событиям',
            hintStyle: AppTypography.regular(15 * s, color: AppColors.textHint),
            suffixIcon: Icon(
              Icons.search,
              color: AppColors.textSecondary,
              size: 22 * s,
            ),
            enabledBorder: const UnderlineInputBorder(
              borderSide: BorderSide(color: AppColors.divider),
            ),
            focusedBorder: const UnderlineInputBorder(
              borderSide: BorderSide(color: AppColors.brandRed, width: 1.5),
            ),
          ),
        ),
        SizedBox(height: 12 * s),
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
          padding: EdgeInsets.symmetric(vertical: 14 * s),
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
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Text(
                              title,
                              style: AppTypography.bold(
                                15 * s,
                                color: AppColors.textInput,
                              ).copyWith(height: 1.25),
                            ),
                          ),
                          SizedBox(width: 8 * s),
                          Text(
                            time,
                            style: AppTypography.regular(
                              12 * s,
                              color: AppColors.textMuted,
                            ),
                          ),
                        ],
                      ),
                      SizedBox(height: 4 * s),
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              subtitle,
                              style: AppTypography.regular(
                                13 * s,
                                color: AppColors.textMuted,
                              ),
                            ),
                          ),
                          if (badge != null)
                            Container(
                              width: 18 * s,
                              height: 18 * s,
                              alignment: Alignment.center,
                              decoration: const BoxDecoration(
                                color: AppColors.brandRed,
                                shape: BoxShape.circle,
                              ),
                              child: Text(
                                '$badge',
                                style: AppTypography.bold(
                                  11 * s,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ],
                  ),
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
