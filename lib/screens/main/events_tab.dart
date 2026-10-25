import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/companies_api.dart';
import '../../api/feed_models.dart';
import '../../demo/alfa_demo_data.dart';
import '../../l10n/app_localizations.dart';
import '../../services/auth_store.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import 'news_detail_screen.dart';

enum _EventsState { loading, noCompany, error, empty, ready }

class EventsTab extends StatefulWidget {
  const EventsTab({super.key, this.onUnreadChanged});

  final ValueChanged<int>? onUnreadChanged;

  @override
  State<EventsTab> createState() => _EventsTabState();
}

class _EventsTabState extends State<EventsTab> {
  int _filter = 0;
  Set<String> _viewedIds = {};
  bool _viewedLoaded = false;
  _EventsState _state = _EventsState.loading;
  String? _errorMessage;
  List<Map<String, dynamic>> _apiCards = const [];

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await Future.wait([_loadViewed(), _loadEvents()]);
  }

  Future<void> _loadViewed() async {
    final viewed = await SessionStore.viewedEventIds();
    if (!mounted) return;
    setState(() {
      _viewedIds = viewed;
      _viewedLoaded = true;
    });
    _notifyUnread();
  }

  void _notifyUnread() {
    if (!_viewedLoaded) return;
    final l10n = mounted ? context.l10n : null;
    if (l10n == null) return;
    final all = [for (final c in _apiCards) FeedEvent.fromCard(c, l10n)];
    final count = all.where((e) => !_viewedIds.contains(e.id)).length;
    widget.onUnreadChanged?.call(count);
  }

  Future<void> _openSource(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    try {
      if (!await canLaunchUrl(uri)) return;
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {}
  }

  Future<bool> _useAlfaDemoFeed() async {
    if (await SessionStore.isAlfaDemo()) return true;
    if (await AuthStore.hasSession()) return false;
    final profile = await SessionStore.loadProfile();
    final hasCompany = profile != null && profile.companyName.trim().isNotEmpty;
    if (!hasCompany) return false;
    await SessionStore.markAlfaDemo(enabled: true);
    return true;
  }

  Future<void> _loadEvents() async {
    setState(() {
      _state = _EventsState.loading;
      _errorMessage = null;
    });
    final companyId = await AuthStore.companyId();
    if (companyId == null || companyId.isEmpty) {
      if (await _useAlfaDemoFeed()) {
        if (!mounted) return;
        setState(() {
          _apiCards = AlfaDemoData.feedCards();
          _state = _EventsState.ready;
        });
        _notifyUnread();
        return;
      }
      if (mounted) {
        setState(() {
          _apiCards = const [];
          _state = _EventsState.noCompany;
        });
        _notifyUnread();
      }
      return;
    }
    try {
      final res = await CompaniesApi.instance.listEvents(companyId, limit: 40);
      final items = (res['items'] as List?) ?? const [];
      final cards = <Map<String, dynamic>>[
        for (final raw in items)
          if (raw is Map) Map<String, dynamic>.from(raw),
      ];
      if (!mounted) return;
      setState(() {
        _apiCards = cards;
        _state = cards.isEmpty ? _EventsState.empty : _EventsState.ready;
      });
      _notifyUnread();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _apiCards = const [];
        _state = _EventsState.error;
        _errorMessage = e.toString();
      });
      _notifyUnread();
    }
  }

  Future<void> _markViewed(String id) async {
    if (_viewedIds.contains(id)) return;
    setState(() => _viewedIds = {..._viewedIds, id});
    await SessionStore.markEventViewed(id);
    _notifyUnread();
  }

  List<FeedEvent> _visible(List<FeedEvent> all) {
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
    final all = [for (final c in _apiCards) FeedEvent.fromCard(c, l10n)];
    final newCount = _viewedLoaded
        ? all.where((e) => !_viewedIds.contains(e.id)).length
        : all.length;
    final visible = _visible(all);
    const hPad = AppColors.screenPadding;

    return RefreshIndicator(
      onRefresh: _loadEvents,
      color: AppColors.brandRed,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
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
          if (_state == _EventsState.ready) ...[
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
          ],
          Padding(
            padding: EdgeInsets.symmetric(horizontal: hPad * s),
            child: Column(
              children: [
                SizedBox(height: 16 * s),
                if (_state == _EventsState.loading)
                  Padding(
                    padding: EdgeInsets.symmetric(vertical: 40 * s),
                    child: const Center(
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                else if (_state == _EventsState.noCompany)
                  _HonestBox(
                    title: l10n.feedNoCompanyTitle,
                    body: l10n.feedNoCompanyBody,
                  )
                else if (_state == _EventsState.error)
                  _HonestBox(
                    title: l10n.feedErrorTitle,
                    body: _errorMessage ?? l10n.feedErrorBody,
                  )
                else if (_state == _EventsState.empty)
                  _HonestBox(
                    title: l10n.feedEmptyTitle,
                    body: l10n.feedEmptyBody,
                  )
                else
                  for (var i = 0; i < visible.length; i++) ...[
                    if (i > 0) SizedBox(height: 12 * s),
                    EventSignalCard(
                      key: ValueKey(visible[i].id),
                      level: visible[i].level,
                      meta: visible[i].meta,
                      title: visible[i].title,
                      contextLead: visible[i].contextLead,
                      contextBody: visible[i].contextBody,
                      timeLabel: visible[i].timeLabel,
                      sourceLabel: visible[i].sourceLabel,
                      sourceUrl: visible[i].sourceUrl,
                      warning: visible[i].warning,
                      actionLabel: visible[i].actionLabel,
                      onSourceTap: visible[i].sourceUrl.isEmpty
                          ? null
                          : () => _openSource(visible[i].sourceUrl),
                      onOpen: () {
                        final e = visible[i];
                        openNewsDetail(
                          context,
                          newsDetailFor(
                            level: e.level,
                            title: e.title,
                            meta: e.meta,
                            timeLabel: e.timeLabel,
                            sourceUrl: e.sourceUrl,
                            sourceLabel: e.sourceLabel,
                            levelHint: e.levelHint,
                            warning: e.warning,
                            reason: e.contextBody,
                            l10n: l10n,
                          ),
                          backLabel: l10n.navEvents,
                          eventId: e.id,
                          onOpened: () => _markViewed(e.id),
                        );
                      },
                    ),
                  ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HonestBox extends StatelessWidget {
  const _HonestBox({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(16 * s),
      decoration: BoxDecoration(
        color: AppColors.surfaceRaised,
        borderRadius: BorderRadius.circular(14 * s),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: AppTypography.bold(15 * s, color: AppColors.textInput),
          ),
          SizedBox(height: 8 * s),
          Text(
            body,
            style: AppTypography.regular(13 * s, color: AppColors.textMuted),
          ),
        ],
      ),
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
