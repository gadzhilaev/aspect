import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import 'chat_screen.dart';

/// Ids сценариев, которые считаются новыми, пока пользователь их не открыл.
const kNewScenarioIds = <String>{
  'china-electronics-export',
};

class ScenariosTab extends StatefulWidget {
  const ScenariosTab({
    super.key,
    this.onUnreadChanged,
  });

  final ValueChanged<int>? onUnreadChanged;

  @override
  State<ScenariosTab> createState() => _ScenariosTabState();
}

class _ScenariosTabState extends State<ScenariosTab> {
  Set<String> _viewedIds = {};
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    _loadViewed();
  }

  Future<void> _loadViewed() async {
    final viewed = await SessionStore.viewedScenarioIds();
    if (!mounted) return;
    setState(() {
      _viewedIds = viewed;
      _loaded = true;
    });
    _notifyUnread();
  }

  int get _unreadCount {
    if (!_loaded) return kNewScenarioIds.length;
    return kNewScenarioIds.where((id) => !_viewedIds.contains(id)).length;
  }

  void _notifyUnread() {
    widget.onUnreadChanged?.call(_unreadCount);
  }

  Future<void> _openScenario({
    required String id,
    required ChatScreenData data,
  }) async {
    if (!_viewedIds.contains(id)) {
      await SessionStore.markScenarioViewed(id);
      if (!mounted) return;
      setState(() => _viewedIds = {..._viewedIds, id});
      _notifyUnread();
    }
    if (!mounted) return;
    await openChatScreen(context, data);
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final chinaUnread =
        _loaded && !_viewedIds.contains('china-electronics-export');

    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        24 * s,
      ),
      children: [
        Text(l10n.scenariosTitle, style: pageTitleStyle(context)),
        SizedBox(height: 8 * s),
        Text(
          l10n.scenariosSubtitle,
          style: AppTypography.regular(14 * s, color: AppColors.textMuted),
        ),
        SizedBox(height: 14 * s),
        Container(
          height: 50 * s,
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16 * s),
            border: Border.all(color: AppColors.border, width: 1),
          ),
          padding: EdgeInsets.symmetric(horizontal: 16 * s),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  textCapitalization: TextCapitalization.sentences,
                  style: AppTypography.regular(
                    15 * s,
                    color: AppColors.textPrimary,
                  ),
                  cursorColor: AppColors.brandRed,
                  decoration: InputDecoration(
                    isDense: true,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    hintText: l10n.scenariosSearchHint,
                    hintStyle: AppTypography.regular(
                      15 * s,
                      color: AppColors.textHint,
                    ),
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
              ),
              Icon(
                Icons.search,
                color: AppColors.textSecondary,
                size: 22 * s,
              ),
            ],
          ),
        ),
        SizedBox(height: 6 * s),
        _ScenarioRow(
          accent: AppColors.brandRed,
          title: l10n.eventChinaTitle,
          subtitle: l10n.scenarioChinaSub,
          time: '08:24',
          badge: chinaUnread || !_loaded ? 1 : null,
          onTap: () => _openScenario(
            id: 'china-electronics-export',
            data: ChatScreenData(
              title: l10n.eventChinaTitle,
              meta: l10n.impactMeta(l10n.impactHigh, '${l10n.today} 08:24'),
              level: ImpactLevel.high,
            ),
          ),
        ),
        _ScenarioRow(
          accent: AppColors.impactPurple,
          title: l10n.eventCnyTitle,
          subtitle: l10n.scenarioCnySub,
          time: l10n.yesterday,
          onTap: () => _openScenario(
            id: 'cny-rate-week',
            data: ChatScreenData(
              title: l10n.eventCnyTitle,
              meta: l10n.impactMeta(l10n.impactMedium, l10n.yesterday),
              level: ImpactLevel.medium,
            ),
          ),
        ),
        _ScenarioRow(
          accent: AppColors.impactGreen,
          title: l10n.eventKzTitle,
          subtitle: l10n.scenarioKzSub,
          time: l10n.mondayShort,
          onTap: () => _openScenario(
            id: 'kz-electronics-demand',
            data: ChatScreenData(
              title: l10n.eventKzTitle,
              meta: l10n.impactMeta(l10n.impactOpportunity, l10n.mondayShort),
              level: ImpactLevel.opportunity,
            ),
          ),
        ),
      ],
    );
  }
}

class _ScenarioRow extends StatelessWidget {
  const _ScenarioRow({
    required this.accent,
    required this.title,
    required this.subtitle,
    required this.time,
    this.badge,
    this.onTap,
  });

  final Color accent;
  final String title;
  final String subtitle;
  final String time;
  final int? badge;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Column(
      children: [
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 12 * s),
              child: IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Container(
                      width: 3 * s,
                      decoration: BoxDecoration(
                        color: accent,
                        borderRadius: BorderRadius.circular(2 * s),
                      ),
                    ),
                    SizedBox(width: 12 * s),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            style: AppTypography.bold(
                              15 * s,
                              color: AppColors.textInput,
                            ).copyWith(height: 1.25),
                          ),
                          SizedBox(height: 4 * s),
                          Text(
                            subtitle,
                            style: AppTypography.regular(
                              13 * s,
                              color: AppColors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                    SizedBox(width: 8 * s),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      mainAxisAlignment: MainAxisAlignment.start,
                      children: [
                        Text(
                          time,
                          style: AppTypography.regular(
                            12 * s,
                            color: AppColors.textMuted,
                          ),
                        ),
                        if (badge != null) ...[
                          SizedBox(height: 6 * s),
                          Container(
                            width: 22 * s,
                            height: 22 * s,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: AppColors.brandRed,
                              shape: BoxShape.circle,
                            ),
                            child: Text(
                              '$badge',
                              textAlign: TextAlign.center,
                              style: AppTypography.bold(
                                11 * s,
                                color: Colors.white,
                              ).copyWith(height: 1),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        Divider(height: 1 * s, color: AppColors.divider),
      ],
    );
  }
}
