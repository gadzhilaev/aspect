import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import 'news_detail_screen.dart';

class OverviewTab extends StatelessWidget {
  const OverviewTab({super.key, this.userName = ''});

  final String userName;

  @override
  Widget build(BuildContext context) {
    final s = designScale(context);
    final l10n = context.l10n;
    final name = userName.trim().isEmpty ? l10n.defaultUserName : userName;
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
                l10n.overviewGoodMorning(name),
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
              CurrencyChipCard(
                code: 'CNY',
                country: l10n.countryChina,
                rate: '12,75 ₽',
              ),
              SizedBox(width: 9 * s),
              CurrencyChipCard(
                code: '10 AMD',
                country: l10n.countryArmenia,
                rate: '2,36 ₽',
              ),
              SizedBox(width: 9 * s),
              CurrencyChipCard(
                code: 'KRW',
                country: l10n.countrySouthKorea,
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
                meta: l10n.impactMeta(l10n.impactHigh, '08:24'),
                title: l10n.eventChinaTitle,
                contextLead: l10n.whyForYou,
                contextBody: l10n.eventChinaContext,
                warning: l10n.eventChinaWarning,
                actionLabel: l10n.openImpact,
                onOpen: () => openNewsDetail(
                  context,
                  chinaExportDetail,
                  backLabel: l10n.navOverview,
                ),
              ),
              SizedBox(height: 30 * s),
              Text(
                l10n.onWatch,
                style: AppTypography.bold(
                  17.09 * s,
                  color: AppColors.textInput,
                ),
              ),
              SizedBox(height: 14 * s),
              MonitorTile(
                dotColor: AppColors.impactPurple,
                title: l10n.eventCnyTitle,
                subtitle: l10n.eventCnyContext,
              ),
              SizedBox(height: 9 * s),
              MonitorTile(
                dotColor: AppColors.impactGreen,
                title: l10n.eventKzTitle,
                subtitle: l10n.eventCnyContext,
              ),
            ],
          ),
        ),
      ],
    );
  }
}
