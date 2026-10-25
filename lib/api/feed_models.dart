import '../l10n/app_localizations.dart';
import '../utils/text_sanitize.dart';
import '../widgets/main_widgets.dart';

/// Карточка события из API → UI.
class FeedEvent {
  const FeedEvent({
    required this.id,
    required this.level,
    required this.meta,
    required this.levelHint,
    required this.title,
    required this.contextLead,
    required this.contextBody,
    this.warning,
    required this.actionLabel,
    this.timeLabel = '',
    this.sourceUrl = '',
    this.sourceLabel = '',
  });

  final String id;
  final ImpactLevel level;
  final String meta;
  final String levelHint;
  final String title;
  final String contextLead;
  final String contextBody;
  final String? warning;
  final String actionLabel;
  final String timeLabel;
  final String sourceUrl;
  final String sourceLabel;

  factory FeedEvent.fromCard(
    Map<String, dynamic> card,
    AppLocalizations l10n, {
    String decisionMakerRole = '',
  }) {
    final priority = (card['priority'] ?? '').toString().toLowerCase();
    final score = (card['impact_score'] as num?)?.toDouble();
    final scoreKind = (card['score_kind'] ?? '').toString();
    final level = _levelFrom(priority, score, scoreKind);
    final title = decodeHtmlEntities((card['title'] ?? '').toString());
    final reason = decodeHtmlEntities((card['reason_summary'] ?? '').toString());
    final profileRel = card['profile_relevance'];
    String whyBody = reason;
    String whyLead = l10n.whyForYouForRole(decisionMakerRole);
    if (profileRel is Map && profileRel['matched'] == true) {
      final label = (profileRel['label'] ?? '').toString().trim();
      if (label.isNotEmpty) whyLead = label;
      final summary = decodeHtmlEntities(
        (profileRel['summary'] ?? '').toString(),
      ).trim();
      if (summary.isNotEmpty) whyBody = summary;
    }
    if (whyBody.isEmpty) whyBody = title;
    final when = _formatUpdated(
      card['updated_at'] ?? card['occurred_at'] ?? card['published_at'],
      l10n,
    );
    final thematic = scoreKind == 'case_profile_match' ||
        scoreKind == 'industry_profile_match' ||
        score == null;
    final impactLabel = thematic
        ? ((profileRel is Map &&
                (profileRel['label']?.toString().isNotEmpty ?? false))
            ? profileRel['label'].toString()
            : l10n.impactOpportunity)
        : switch (level) {
            ImpactLevel.high => l10n.impactHigh,
            ImpactLevel.medium => l10n.impactMedium,
            ImpactLevel.opportunity => l10n.impactOpportunity,
          };
    final levelHint = switch (level) {
      ImpactLevel.high => l10n.impactHighHint,
      ImpactLevel.medium => l10n.impactMediumHint,
      ImpactLevel.opportunity => l10n.impactOpportunityHint,
    };
    final exposure = card['exposure'];
    String? warning;
    // Never show money exposure on thematic-only cards.
    if (!thematic && exposure is Map && exposure['label'] != null) {
      final v = exposure['value'];
      final unit = exposure['unit']?.toString() ?? '';
      warning = '${exposure['label']}: $v$unit';
    }
    final action = level == ImpactLevel.high
        ? l10n.openImpact
        : level == ImpactLevel.opportunity
            ? l10n.viewScenario
            : l10n.openAction;
    final sources = card['sources'];
    String sourceUrl = '';
    String sourceLabel = '';
    if (sources is List) {
      for (final s in sources) {
        if (s is! Map) continue;
        final url = s['url']?.toString() ?? '';
        if (url.isEmpty) continue;
        sourceUrl = url;
        sourceLabel = url;
        break;
      }
    }
    return FeedEvent(
      id: card['id']?.toString() ?? title,
      level: level,
      meta: l10n.impactMeta(impactLabel, when),
      levelHint: levelHint,
      title: title,
      contextLead: whyLead.endsWith(':') ? whyLead : '$whyLead:',
      contextBody: whyBody,
      warning: warning,
      actionLabel: action,
      timeLabel: when,
      sourceUrl: sourceUrl,
      sourceLabel: sourceLabel,
    );
  }
}

ImpactLevel _levelFrom(String priority, double? score, String scoreKind) {
  // null impact_score must never be treated as zero.
  if (scoreKind == 'case_profile_match' ||
      scoreKind == 'industry_profile_match' ||
      priority == 'low') {
    return ImpactLevel.opportunity;
  }
  if (priority == 'high' || (score != null && score >= 80)) {
    return ImpactLevel.high;
  }
  if (priority == 'medium' || (score != null && score >= 50)) {
    return ImpactLevel.medium;
  }
  if (score == null) {
    return ImpactLevel.opportunity;
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
  final time = '$hh:$mm';
  if (sameDay) return '${l10n.today} $time';
  if (isYesterday) return '${l10n.yesterday} $time';
  final dd = dt.day.toString().padLeft(2, '0');
  final mo = dt.month.toString().padLeft(2, '0');
  return '$dd.$mo.${dt.year} $time';
}
