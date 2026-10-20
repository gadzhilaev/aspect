import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../../widgets/main_widgets.dart';

class ScenariosTab extends StatelessWidget {
  const ScenariosTab({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        const AspectBrandHeader(),
        const SizedBox(height: 18),
        const Text(
          'Сценарии',
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
            letterSpacing: -0.4,
            height: 1.15,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Диалоги по важным событиям',
          style: TextStyle(
            fontSize: 14,
            color: Color(0xFF65717A),
          ),
        ),
        const SizedBox(height: 18),
        TextField(
          decoration: InputDecoration(
            hintText: 'Поиск по событиям',
            hintStyle: const TextStyle(color: AppColors.textHint),
            suffixIcon: const Icon(
              Icons.search,
              color: AppColors.textSecondary,
            ),
            enabledBorder: const UnderlineInputBorder(
              borderSide: BorderSide(color: AppColors.divider),
            ),
            focusedBorder: const UnderlineInputBorder(
              borderSide: BorderSide(color: AppColors.brandRed, width: 1.5),
            ),
          ),
        ),
        const SizedBox(height: 12),
        const _ScenarioRow(
          accent: AppColors.brandRed,
          title: 'Китай ограничивает экспорт электроники',
          subtitle: 'Аспект: подготовил сценарии для поставок',
          time: '08:24',
          badge: 1,
        ),
        const _ScenarioRow(
          accent: Color(0xFF7A18DC),
          title: 'Курс CNY вырос на 1,8% за неделю',
          subtitle: 'Аспект: оценил влияние на покупки',
          time: 'Вчера',
        ),
        const _ScenarioRow(
          accent: Color(0xFF0B8A6A),
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
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 14),
          child: IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  width: 3,
                  decoration: BoxDecoration(
                    color: accent,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(width: 12),
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
                              style: const TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: AppColors.textInput,
                                height: 1.25,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            time,
                            style: const TextStyle(
                              fontSize: 12,
                              color: Color(0xFF65717A),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              subtitle,
                              style: const TextStyle(
                                fontSize: 13,
                                color: Color(0xFF65717A),
                              ),
                            ),
                          ),
                          if (badge != null)
                            Container(
                              width: 18,
                              height: 18,
                              alignment: Alignment.center,
                              decoration: const BoxDecoration(
                                color: AppColors.brandRed,
                                shape: BoxShape.circle,
                              ),
                              child: Text(
                                '$badge',
                                style: const TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700,
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
        const Divider(height: 1, color: AppColors.divider),
      ],
    );
  }
}
