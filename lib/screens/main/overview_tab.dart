import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../../widgets/main_widgets.dart';

class OverviewTab extends StatelessWidget {
  const OverviewTab({super.key, this.userName = 'Магомед'});

  final String userName;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        const AspectBrandHeader(dateText: '12 октября 2026 г'),
        const SizedBox(height: 18),
        Text(
          'Доброе утро, $userName',
          style: const TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
            letterSpacing: -0.4,
            height: 1.15,
          ),
        ),
        const SizedBox(height: 18),
        SizedBox(
          height: 88,
          child: ListView(
            scrollDirection: Axis.horizontal,
            children: const [
              CurrencyChipCard(
                code: 'CNY',
                country: 'Китай',
                rate: '12,75 ₽',
              ),
              SizedBox(width: 10),
              CurrencyChipCard(
                code: '10 AMD',
                country: 'Армения',
                rate: '2,36 ₽',
              ),
              SizedBox(width: 10),
              CurrencyChipCard(
                code: 'KRW',
                country: 'Южная Корея',
                rate: '6,36 ₽',
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        const EventSignalCard(
          level: ImpactLevel.high,
          meta: 'Высокое влияние · 08:24',
          title: 'Китай ограничивает экспорт электроники',
          contextText:
              'Почему вам: Китай указан как страна поставки электронных компонентов',
          warning: 'Риск роста себестоимости и переноса сроков поставки',
          actionLabel: 'Открыть влияние',
        ),
        const SizedBox(height: 22),
        const Text(
          'На контроле',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
        ),
        const SizedBox(height: 12),
        const MonitorTile(
          dotColor: Color(0xFF7A18DC),
          title: 'Курс CNY вырос на 1,8% за неделю',
          subtitle: 'Валюта используется в расчетах с поставщиками',
        ),
        const SizedBox(height: 10),
        const MonitorTile(
          dotColor: Color(0xFF0B8A6A),
          title: 'Спрос на электронику в Казахстане растет',
          subtitle: 'Валюта используется в расчетах с поставщиками',
        ),
      ],
    );
  }
}
