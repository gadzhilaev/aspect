import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';

class EventsTab extends StatefulWidget {
  const EventsTab({super.key});

  @override
  State<EventsTab> createState() => _EventsTabState();
}

class _EventsTabState extends State<EventsTab> {
  int _filter = 0;

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
          'Главные новости для вас',
          style: AppTypography.bold(28 * s, color: AppColors.textPrimary)
              .copyWith(letterSpacing: -0.4, height: 1.15),
        ),
        SizedBox(height: 8 * s),
        Text(
          'Сигналы, отобранные для вашей компании',
          style: AppTypography.regular(14 * s, color: AppColors.textMuted),
        ),
        SizedBox(height: 16 * s),
        Wrap(
          spacing: 8 * s,
          runSpacing: 8 * s,
          children: [
            _FilterChip(
              label: 'Все',
              selected: _filter == 0,
              onTap: () => setState(() => _filter = 0),
            ),
            _FilterChip(
              label: 'Новые',
              badge: '3',
              selected: _filter == 1,
              onTap: () => setState(() => _filter = 1),
            ),
            _FilterChip(
              label: 'Высокое влияние',
              selected: _filter == 2,
              onTap: () => setState(() => _filter = 2),
            ),
          ],
        ),
        SizedBox(height: 16 * s),
        const EventSignalCard(
          level: ImpactLevel.high,
          meta: 'Высокое влияние • 08:24',
          title: 'Китай ограничивает экспорт электроники',
          contextLead: 'Почему вам:',
          contextBody:
              'Китай указан как страна поставки электронных компонентов',
          warning: 'Риск роста себестоимости и переноса сроков поставки',
          actionLabel: 'Открыть влияние',
        ),
        SizedBox(height: 12 * s),
        const EventSignalCard(
          level: ImpactLevel.medium,
          meta: 'Среднее влияние • вчера',
          title: 'Курс CNY вырос на 1,8% за неделю',
          contextLead: 'Почему вам:',
          contextBody: 'Валюта используется в расчетах с поставщиками',
          actionLabel: 'Открыть',
        ),
        SizedBox(height: 12 * s),
        const EventSignalCard(
          level: ImpactLevel.opportunity,
          meta: 'Возможность • вчера',
          title: 'Спрос на электронику в Казахстане растет',
          contextLead: 'Почему вам:',
          contextBody: 'Казахстан указан как рынок сбыта',
          actionLabel: 'Посмотреть сценарий',
        ),
      ],
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onTap,
    this.badge,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 14 * s, vertical: 9 * s),
        decoration: BoxDecoration(
          color: selected ? AppColors.brandRed : AppColors.surface,
          borderRadius: BorderRadius.circular(20 * s),
          border: Border.all(
            color: selected
                ? AppColors.brandRed
                : Colors.black.withValues(alpha: 0.12),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: AppTypography.medium(
                13 * s,
                color: selected ? Colors.white : AppColors.textInput,
              ),
            ),
            if (badge != null) ...[
              SizedBox(width: 4 * s),
              Text(
                badge!,
                style: AppTypography.bold(
                  13 * s,
                  color: selected ? Colors.white : AppColors.brandRed,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
