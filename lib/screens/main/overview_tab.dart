import 'package:flutter/material.dart';

import '../../api/companies_api.dart';
import '../../api/feed_models.dart';
import '../../l10n/app_localizations.dart';
import '../../services/auth_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import 'news_detail_screen.dart';

class OverviewTab extends StatefulWidget {
  const OverviewTab({super.key, this.userName = ''});

  final String userName;

  @override
  State<OverviewTab> createState() => _OverviewTabState();
}

class _OverviewTabState extends State<OverviewTab> {
  List<Map<String, dynamic>> _cards = const [];
  bool _loading = true;
  bool _fromApi = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final companyId = await AuthStore.companyId();
    if (companyId == null || companyId.isEmpty) {
      if (mounted) setState(() => _loading = false);
      return;
    }
    try {
      final dash = await CompaniesApi.instance.getDashboard(companyId);
      final cards = (dash['priority_events'] as List?) ?? const [];
      final mapped = <Map<String, dynamic>>[
        for (final raw in cards)
          if (raw is Map) Map<String, dynamic>.from(raw),
      ];
      if (!mounted) return;
      setState(() {
        _cards = mapped;
        _fromApi = mapped.isNotEmpty;
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<FeedEvent> _fallback(AppLocalizations l10n) => [
        FeedEvent(
          id: 'china_export',
          level: ImpactLevel.high,
          meta: l10n.impactMeta(l10n.impactHigh, '08:24'),
          title: l10n.eventChinaTitle,
          contextLead: l10n.whyForYou,
          contextBody: l10n.eventChinaContext,
          warning: l10n.eventChinaWarning,
          actionLabel: l10n.openImpact,
        ),
        FeedEvent(
          id: 'cny_rate',
          level: ImpactLevel.medium,
          meta: l10n.impactMeta(l10n.impactMedium, l10n.yesterday.toLowerCase()),
          title: l10n.eventCnyTitle,
          contextLead: l10n.whyForYou,
          contextBody: l10n.eventCnyContext,
          actionLabel: l10n.openAction,
        ),
        FeedEvent(
          id: 'kz_demand',
          level: ImpactLevel.opportunity,
          meta: l10n.impactMeta(
            l10n.impactOpportunity,
            l10n.yesterday.toLowerCase(),
          ),
          title: l10n.eventKzTitle,
          contextLead: l10n.whyForYou,
          contextBody: l10n.eventKzContext,
          actionLabel: l10n.viewScenario,
        ),
      ];

  @override
  Widget build(BuildContext context) {
    final s = designScale(context);
    final l10n = context.l10n;
    final name =
        widget.userName.trim().isEmpty ? l10n.defaultUserName : widget.userName;
    final chipH = 70 * s;
    const hPad = AppColors.screenPadding;

    final fallback = _fallback(l10n);
    final apiEvents = [
      for (final c in _cards) FeedEvent.fromCard(c, l10n),
    ];
    final priority = _fromApi && apiEvents.isNotEmpty
        ? [apiEvents.first]
        : [fallback.first];
    final watch =
        _fromApi ? apiEvents.skip(1).toList() : fallback.sublist(1);

    return RefreshIndicator(
      onRefresh: _load,
      color: AppColors.brandRed,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
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
                if (_loading)
                  Padding(
                    padding: EdgeInsets.symmetric(vertical: 24 * s),
                    child: const Center(
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                else ...[
                  for (final e in priority) ...[
                    EventSignalCard(
                      level: e.level,
                      meta: e.meta,
                      title: e.title,
                      contextLead: e.contextLead,
                      contextBody: e.contextBody,
                      warning: e.warning,
                      actionLabel: e.actionLabel,
                      onOpen: () => openNewsDetail(
                        context,
                        newsDetailFor(
                          level: e.level,
                          title: e.title,
                          meta: e.meta,
                          warning: e.warning,
                        ),
                        backLabel: l10n.navOverview,
                        eventId: _fromApi ? e.id : null,
                      ),
                    ),
                    SizedBox(height: 30 * s),
                  ],
                  Text(
                    l10n.onWatch,
                    style: AppTypography.bold(
                      17.09 * s,
                      color: AppColors.textInput,
                    ),
                  ),
                  SizedBox(height: 14 * s),
                  for (var i = 0; i < watch.length; i++) ...[
                    if (i > 0) SizedBox(height: 9 * s),
                    MonitorTile(
                      dotColor: ImpactColors.accent(watch[i].level),
                      title: watch[i].title,
                      subtitle: watch[i].contextBody,
                    ),
                  ],
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
