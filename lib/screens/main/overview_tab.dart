import 'package:flutter/material.dart';

import '../../api/companies_api.dart';
import '../../api/feed_models.dart';
import '../../l10n/app_localizations.dart';
import '../../services/auth_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import 'news_detail_screen.dart';

enum _FeedState { loading, noCompany, error, empty, ready }

class OverviewTab extends StatefulWidget {
  const OverviewTab({super.key, this.userName = ''});

  final String userName;

  @override
  State<OverviewTab> createState() => _OverviewTabState();
}

class _OverviewTabState extends State<OverviewTab> {
  List<Map<String, dynamic>> _cards = const [];
  _FeedState _state = _FeedState.loading;
  String? _errorMessage;
  String? _emptyDetail;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _state = _FeedState.loading;
      _errorMessage = null;
    });
    final companyId = await AuthStore.companyId();
    if (companyId == null || companyId.isEmpty) {
      if (mounted) setState(() => _state = _FeedState.noCompany);
      return;
    }
    try {
      final dash = await CompaniesApi.instance.getDashboard(companyId);
      final cards = (dash['priority_events'] as List?) ?? const [];
      final mapped = <Map<String, dynamic>>[
        for (final raw in cards)
          if (raw is Map) Map<String, dynamic>.from(raw),
      ];
      final feedEmpty = dash['feed_empty'];
      String? emptyDetail;
      if (feedEmpty is Map) {
        emptyDetail = [
          feedEmpty['title']?.toString(),
          feedEmpty['detail']?.toString(),
        ].whereType<String>().where((s) => s.isNotEmpty).join('\n');
      }
      if (!mounted) return;
      setState(() {
        _cards = mapped;
        _emptyDetail = emptyDetail;
        _state = mapped.isEmpty ? _FeedState.empty : _FeedState.ready;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _cards = const [];
        _state = _FeedState.error;
        _errorMessage = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = designScale(context);
    final l10n = context.l10n;
    final name =
        widget.userName.trim().isEmpty ? l10n.defaultUserName : widget.userName;
    const hPad = AppColors.screenPadding;
    final apiEvents = [
      for (final c in _cards) FeedEvent.fromCard(c, l10n),
    ];

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
                if (_state == _FeedState.loading)
                  Padding(
                    padding: EdgeInsets.symmetric(vertical: 40 * s),
                    child: const Center(
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                else if (_state == _FeedState.noCompany)
                  _HonestBox(
                    title: l10n.feedNoCompanyTitle,
                    body: l10n.feedNoCompanyBody,
                  )
                else if (_state == _FeedState.error)
                  _HonestBox(
                    title: l10n.feedErrorTitle,
                    body: _errorMessage ?? l10n.feedErrorBody,
                  )
                else if (_state == _FeedState.empty)
                  _HonestBox(
                    title: l10n.feedEmptyTitle,
                    body: _emptyDetail ?? l10n.feedEmptyBody,
                  )
                else ...[
                  for (final e in apiEvents.take(1)) ...[
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
                        eventId: e.id,
                      ),
                    ),
                    SizedBox(height: 30 * s),
                  ],
                  if (apiEvents.length > 1) ...[
                    Text(
                      l10n.onWatch,
                      style: AppTypography.bold(
                        17.09 * s,
                        color: AppColors.textInput,
                      ),
                    ),
                    SizedBox(height: 14 * s),
                    for (var i = 1; i < apiEvents.length; i++) ...[
                      if (i > 1) SizedBox(height: 9 * s),
                      MonitorTile(
                        dotColor: ImpactColors.accent(apiEvents[i].level),
                        title: apiEvents[i].title,
                        subtitle: apiEvents[i].contextBody,
                      ),
                    ],
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

class _HonestBox extends StatelessWidget {
  const _HonestBox({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final s = designScale(context);
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
