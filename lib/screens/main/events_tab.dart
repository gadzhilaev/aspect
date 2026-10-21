import 'package:flutter/material.dart';

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

const _allEvents = <_EventItem>[
  _EventItem(
    id: 'china_export',
    level: ImpactLevel.high,
    meta: 'Высокое влияние • 08:24',
    title: 'Китай ограничивает экспорт электроники',
    contextLead: 'Почему вам:',
    contextBody: 'Китай указан как страна поставки электронных компонентов',
    warning: 'Риск роста себестоимости и переноса сроков поставки',
    actionLabel: 'Открыть влияние',
  ),
  _EventItem(
    id: 'cny_rate',
    level: ImpactLevel.medium,
    meta: 'Среднее влияние • вчера',
    title: 'Курс CNY вырос на 1,8% за неделю',
    contextLead: 'Почему вам:',
    contextBody: 'Валюта используется в расчетах с поставщиками',
    actionLabel: 'Открыть',
  ),
  _EventItem(
    id: 'kz_demand',
    level: ImpactLevel.opportunity,
    meta: 'Возможность • вчера',
    title: 'Спрос на электронику в Казахстане растет',
    contextLead: 'Почему вам:',
    contextBody: 'Казахстан указан как рынок сбыта',
    actionLabel: 'Посмотреть сценарий',
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

  int get _newCount =>
      _allEvents.where((e) => !_viewedIds.contains(e.id)).length;

  List<_EventItem> get _visible {
    switch (_filter) {
      case 1:
        return [
          for (final e in _allEvents)
            if (!_viewedIds.contains(e.id)) e,
        ];
      case 2:
        return [
          for (final e in _allEvents)
            if (e.level == ImpactLevel.high) e,
        ];
      default:
        return _allEvents;
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final newCount = _loaded ? _newCount : _allEvents.length;
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
              Text('Главные новости для вас', style: pageTitleStyle(context)),
              SizedBox(height: 8 * s),
              Text(
                'Сигналы, отобранные для вашей компании',
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
                label: 'Все',
                selected: _filter == 0,
                onTap: () => setState(() => _filter = 0),
              ),
              SizedBox(width: 8 * s),
              _FilterChip(
                label: 'Новые',
                badge: newCount > 0 ? '$newCount' : null,
                selected: _filter == 1,
                onTap: () => setState(() => _filter = 1),
              ),
              SizedBox(width: 8 * s),
              _FilterChip(
                label: 'Высокое влияние',
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
              for (var i = 0; i < _visible.length; i++) ...[
                if (i > 0) SizedBox(height: 12 * s),
                EventSignalCard(
                  key: ValueKey(_visible[i].id),
                  level: _visible[i].level,
                  meta: _visible[i].meta,
                  title: _visible[i].title,
                  contextLead: _visible[i].contextLead,
                  contextBody: _visible[i].contextBody,
                  warning: _visible[i].warning,
                  actionLabel: _visible[i].actionLabel,
                  onOpen: () {
                    final e = _visible[i];
                    openNewsDetail(
                      context,
                      newsDetailFor(
                        level: e.level,
                        title: e.title,
                        meta: e.meta,
                      ),
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
                color: selected ? AppColors.surface : AppColors.textPrimary,
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
