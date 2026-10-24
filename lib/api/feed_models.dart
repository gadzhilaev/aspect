import '../l10n/app_localizations.dart';
import '../widgets/main_widgets.dart';

/// Карточка события из API → UI.
class FeedEvent {
  const FeedEvent({
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

  factory FeedEvent.fromCard(
    Map<String, dynamic> card,
    AppLocalizations l10n,
  ) {
    final priority = (card['priority'] ?? '').toString().toLowerCase();
    final score = (card['impact_score'] as num?)?.toDouble();
    final scoreKind = (card['score_kind'] ?? '').toString();
    final level = _levelFrom(priority, score, scoreKind);
    final title = (card['title'] ?? '').toString();
    final reason = (card['reason_summary'] ?? '').toString();
    final updated = _formatUpdated(card['updated_at'], l10n);
    final impactLabel = switch (level) {
      ImpactLevel.high => l10n.impactHigh,
      ImpactLevel.medium => l10n.impactMedium,
      ImpactLevel.opportunity => l10n.impactOpportunity,
    };
    final exposure = card['exposure'];
    String? warning;
    if (exposure is Map && exposure['label'] != null) {
      final v = exposure['value'];
      final unit = exposure['unit']?.toString() ?? '';
      warning = '${exposure['label']}: $v$unit';
    }
    final action = level == ImpactLevel.high
        ? l10n.openImpact
        : level == ImpactLevel.opportunity
            ? l10n.viewScenario
            : l10n.openAction;
    return FeedEvent(
      id: card['id']?.toString() ?? title,
      level: level,
      meta: l10n.impactMeta(impactLabel, updated),
      title: title,
      contextLead: l10n.whyForYou,
      contextBody: reason.isNotEmpty ? reason : title,
      warning: warning,
      actionLabel: action,
    );
  }
}

ImpactLevel _levelFrom(String priority, double? score, String scoreKind) {
  if (scoreKind == 'case_profile_match' || priority == 'low') {
    return ImpactLevel.opportunity;
  }
  if (priority == 'high' || (score != null && score >= 80)) {
    return ImpactLevel.high;
  }
  if (priority == 'medium' || (score != null && score >= 50)) {
    return ImpactLevel.medium;
  }
  return ImpactLevel.opportunity;
}

String _formatUpdated(dynamic raw, AppLocalizations l10n) {
  if (raw == null) return '';
  final dt = DateTime.tryParse(raw.toString())?.toLocal();
  if (dt == null) return raw.toString();
  final now = DateTime.now();
  final sameDay =
      dt.year == now.year && dt.month == now.month && dt.day == now.day;
  final yesterday = now.subtract(const Duration(days: 1));
  final isYesterday = dt.year == yesterday.year &&
      dt.month == yesterday.month &&
      dt.day == yesterday.day;
  final hh = dt.hour.toString().padLeft(2, '0');
  final mm = dt.minute.toString().padLeft(2, '0');
  if (sameDay) return '$hh:$mm';
  if (isYesterday) return l10n.yesterday.toLowerCase();
  return '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')}';
}
