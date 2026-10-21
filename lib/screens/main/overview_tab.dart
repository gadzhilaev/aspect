import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import 'news_detail_screen.dart';

class OverviewTab extends StatelessWidget {
  const OverviewTab({super.key, this.userName = 'Пользователь'});

  final String userName;

  @override
  Widget build(BuildContext context) {
    final s = designScale(context);
    final chipH = 70 * s;
    const hPad = AppColors.screenPadding;

    return ListView(
      padding: EdgeInsets.only(
        top: AppColors.screenPadding,
        bottom: 24 * s,
      ),
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: hPad),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Доброе утро, $userName',
                style: pageTitleStyle(context),
              ),
              SizedBox(height: 18 * s),
            ],
          ),
        ),
        SizedBox(
          height: chipH,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.only(left: hPad),
            children: [
              const CurrencyChipCard(
                code: 'CNY',
                country: 'Китай',
                rate: '12,75 ₽',
              ),
              SizedBox(width: 9 * s),
              const CurrencyChipCard(
                code: '10 AMD',
                country: 'Армения',
                rate: '2,36 ₽',
              ),
              SizedBox(width: 9 * s),
              const CurrencyChipCard(
                code: 'KRW',
                country: 'Южная Корея',
                rate: '6,36 ₽',
              ),
              const SizedBox(width: hPad),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: hPad),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(height: 20 * s),
              EventSignalCard(
                level: ImpactLevel.high,
                meta: 'Высокое влияние · 08:24',
                title: 'Китай ограничивает экспорт электроники',
                contextLead: 'Почему вам:',
                contextBody:
                    'Китай указан как страна поставки электронных компонентов',
                warning:
                    'Риск роста себестоимости и переноса сроков поставки',
                actionLabel: 'Открыть влияние',
                onOpen: () => openNewsDetail(
                  context,
                  chinaExportDetail,
                  backLabel: 'Обзор',
                ),
              ),
              SizedBox(height: 30 * s),
              Text(
                'На контроле',
                style: AppTypography.bold(
                  17.09 * s,
                  color: AppColors.textInput,
                ),
              ),
              SizedBox(height: 14 * s),
              const MonitorTile(
                dotColor: AppColors.impactPurple,
                title: 'Курс CNY вырос на 1,8% за неделю',
                subtitle: 'Валюта используется в расчетах с поставщиками',
              ),
              SizedBox(height: 9 * s),
              const MonitorTile(
                dotColor: AppColors.impactGreen,
                title: 'Спрос на электронику в Казахстане растет',
                subtitle: 'Валюта используется в расчетах с поставщиками',
              ),
            ],
          ),
        ),
      ],
    );
  }
}
