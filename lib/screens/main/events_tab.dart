import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import 'news_detail_screen.dart';

class _EventItem {
  const _EventItem({
    required this.id,
    required this.level,
    required this.meta,
    required this.title,
    required this.contextLead,
    required this.contextBody,
    this.warning,
    required this.actionLabel,
  });

  final String id;
  final ImpactLevel level;
  final String meta;
  final String title;
  final String contextLead;
  final String contextBody;
  final String? warning;
  final String actionLabel;
}

List<_EventItem> _eventsFor(AppLocalizations l10n) => [
      _EventItem(
        id: 'china_export',
        level: ImpactLevel.high,
        meta: l10n.impactMeta(l10n.impactHigh, '08:24'),
        title: l10n.eventChinaTitle,
        contextLead: l10n.whyForYou,
        contextBody: l10n.eventChinaContext,
        warning: l10n.eventChinaWarning,
        actionLabel: l10n.openImpact,
      ),
      _EventItem(
        id: 'cny_rate',
        level: ImpactLevel.medium,
        meta: l10n.impactMeta(l10n.impactMedium, l10n.yesterday.toLowerCase()),
        title: l10n.eventCnyTitle,
        contextLead: l10n.whyForYou,
        contextBody: l10n.eventCnyContext,
        actionLabel: l10n.openAction,
      ),
      _EventItem(
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

class EventsTab extends StatefulWidget {
  const EventsTab({super.key});

  @override
  State<EventsTab> createState() => _EventsTabState();
}

class _EventsTabState extends State<EventsTab> {
  int _filter = 0;
  Set<String> _viewedIds = {};
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    _loadViewed();
  }

  Future<void> _loadViewed() async {
    final viewed = await SessionStore.viewedEventIds();
    if (!mounted) return;
    setState(() {
      _viewedIds = viewed;
      _loaded = true;
    });
  }

  Future<void> _markViewed(String id) async {
    if (_viewedIds.contains(id)) return;
    setState(() => _viewedIds = {..._viewedIds, id});
    await SessionStore.markEventViewed(id);
  }

  List<_EventItem> _visible(List<_EventItem> all) {
    switch (_filter) {
      case 1:
        return [
          for (final e in all)
            if (!_viewedIds.contains(e.id)) e,
        ];
      case 2:
        return [
          for (final e in all)
            if (e.level == ImpactLevel.high) e,
        ];
      default:
        return all;
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final all = _eventsFor(l10n);
    final newCount =
        _loaded ? all.where((e) => !_viewedIds.contains(e.id)).length : all.length;
    final visible = _visible(all);
    const hPad = AppColors.screenPadding;

    return ListView(
      padding: EdgeInsets.only(
        top: AppColors.screenPadding * s,
        bottom: 24 * s,
      ),
      children: [
        Padding(
          padding: EdgeInsets.symmetric(horizontal: hPad * s),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.eventsTitle, style: pageTitleStyle(context)),
              SizedBox(height: 8 * s),
              Text(
                l10n.eventsSubtitle,
                style: AppTypography.regular(
                  13 * s,
                  color: AppColors.textMuted,
                ),
              ),
              SizedBox(height: 20 * s),
            ],
          ),
        ),
        SizedBox(
          height: 36 * s,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: EdgeInsets.only(left: hPad * s),
            children: [
              _FilterChip(
                label: l10n.filterAll,
                selected: _filter == 0,
                onTap: () => setState(() => _filter = 0),
              ),
              SizedBox(width: 8 * s),
              _FilterChip(
                label: l10n.filterNew,
                badge: newCount > 0 ? '$newCount' : null,
                selected: _filter == 1,
                onTap: () => setState(() => _filter = 1),
              ),
              SizedBox(width: 8 * s),
              _FilterChip(
                label: l10n.filterHighImpact,
                selected: _filter == 2,
                onTap: () => setState(() => _filter = 2),
              ),
              SizedBox(width: hPad * s),
            ],
          ),
        ),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: hPad * s),
          child: Column(
            children: [
              SizedBox(height: 16 * s),
              for (var i = 0; i < visible.length; i++) ...[
                if (i > 0) SizedBox(height: 12 * s),
                EventSignalCard(
                  key: ValueKey(visible[i].id),
                  level: visible[i].level,
                  meta: visible[i].meta,
                  title: visible[i].title,
                  contextLead: visible[i].contextLead,
                  contextBody: visible[i].contextBody,
                  warning: visible[i].warning,
                  actionLabel: visible[i].actionLabel,
                  onOpen: () {
                    final e = visible[i];
                    openNewsDetail(
                      context,
                      newsDetailFor(
                        level: e.level,
                        title: e.title,
                        meta: e.meta,
                        warning: e.warning,
                      ),
                      backLabel: l10n.navEvents,
                      onOpened: () => _markViewed(e.id),
                    );
                  },
                ),
              ],
            ],
          ),
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
        height: 36 * s,
        padding: EdgeInsets.symmetric(horizontal: 14 * s),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: selected ? AppColors.brandRed : AppColors.filterChipBg,
          borderRadius: BorderRadius.circular(14 * s),
          border: Border.all(
            color: selected ? AppColors.brandRed : AppColors.filterChipBorder,
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: AppTypography.regular(
                13 * s,
                color: selected ? AppColors.surface : AppColors.textMuted,
              ),
            ),
            if (badge != null) ...[
              SizedBox(width: 4 * s),
              Text(
                badge!,
                style: AppTypography.regular(
                  13 * s,
                  color: selected ? AppColors.surface : AppColors.brandRed,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
