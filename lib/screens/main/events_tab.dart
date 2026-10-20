import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
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
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        const AspectBrandHeader(),
        const SizedBox(height: 18),
        const Text(
          'Главные новости для вас',
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
          'Сигналы, отобранные для вашей компании',
          style: TextStyle(
            fontSize: 14,
            color: Color(0xFF65717A),
          ),
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          runSpacing: 8,
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
        const SizedBox(height: 16),
        const EventSignalCard(
          level: ImpactLevel.high,
          meta: 'Высокое влияние • 08:24',
          title: 'Китай ограничивает экспорт электроники',
          contextText:
              'Почему вам: Китай указан как страна поставки электронных компонентов',
          warning: 'Риск роста себестоимости и переноса сроков поставки',
          actionLabel: 'Открыть влияние',
        ),
        const SizedBox(height: 12),
        const EventSignalCard(
          level: ImpactLevel.medium,
          meta: 'Среднее влияние • вчера',
          title: 'Курс CNY вырос на 1,8% за неделю',
          contextText: 'Валюта используется в расчетах с поставщиками',
          actionLabel: 'Открыть',
        ),
        const SizedBox(height: 12),
        const EventSignalCard(
          level: ImpactLevel.opportunity,
          meta: 'Возможность • вчера',
          title: 'Спрос на электронику в Казахстане растет',
          contextText: 'Казахстан указан как рынок сбыта',
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
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        decoration: BoxDecoration(
          color: selected ? AppColors.brandRed : AppColors.surface,
          borderRadius: BorderRadius.circular(20),
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
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: selected ? Colors.white : AppColors.textInput,
              ),
            ),
            if (badge != null) ...[
              const SizedBox(width: 4),
              Text(
                badge!,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
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
