import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/events_api.dart';
import '../../api/feed_models.dart';
import '../../l10n/app_localizations.dart';
import '../../navigation/app_page_route.dart';
import '../../services/auth_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../utils/text_sanitize.dart';
import '../../widgets/main_widgets.dart';
import 'bank_material_screen.dart';
import 'chat_screen.dart';
import 'conclusion_basis_screen.dart';

class NewsDetailData {
  const NewsDetailData({
    required this.level,
    required this.title,
    required this.timeLabel,
    required this.sourceUrl,
    this.sourceLabel = '',
    this.levelHint = '',
    required this.body,
    required this.whatHappened,
    required this.concernTitle,
    required this.callout,
    required this.risk,
    required this.opportunity,
    required this.nextAction,
    this.heroAsset = 'assets/images/news_detail_hero.jpg',
    this.ctaLabel = 'Обсудить с Аспект',
    this.ctaCaption = 'На чем основан вывод?',
    this.bankTitle = '',
    this.bankBody = '',
  });

  final ImpactLevel level;
  final String title;
  final String timeLabel;
  final String sourceUrl;
  final String sourceLabel;
  final String levelHint;
  final String body;
  final String whatHappened;
  final String concernTitle;
  final String callout;
  final String risk;
  final String opportunity;
  final String nextAction;
  final String heroAsset;
  final String ctaLabel;
  final String ctaCaption;
  final String bankTitle;
  final String bankBody;
}

String _levelHintFor(ImpactLevel level, AppLocalizations l10n) => switch (level) {
      ImpactLevel.high => l10n.impactHighHint,
      ImpactLevel.medium => l10n.impactMediumHint,
      ImpactLevel.opportunity => l10n.impactOpportunityHint,
    };

const chinaExportDetail = NewsDetailData(
  level: ImpactLevel.high,
  title: 'Китай ограничивает экспорт электроники',
  timeLabel: 'Сегодня 08:24',
  sourceUrl: 'https://pin.it/2FPGIqkTI',
  sourceLabel: 'https://pin.it/2FPGIqkTI',
  levelHint: 'Сильный риск для вашей компании — лучше разобрать сейчас',
  body:
      'Китай расширил ограничения на экспорт отдельных категорий электроники и компонентов. Мера затрагивает поставки продукции двойного назначения.\n\nНовые правила могут повлиять на сроки поставок и условия контрактов для зарубежных покупателей. Подробные требования будут опубликованы в ближайшие дни.',
  whatHappened:
      'Ограничения вводятся поэтапно и распространяются на ряд технологических категорий.',
  concernTitle: 'Почему это про вашу компанию',
  callout: 'Китай — один из рынков поставок вашей компании',
  risk: 'Задержка поставок критичных компонентов',
  opportunity: 'Заранее пересмотреть пул поставщиков',
  nextAction:
      'Заранее пересмотреть пул поставщиков. Уточнить структуру долга и обсудить, какие условия требуют внимания.',
);

ConclusionBasisData _basisFromNews(NewsDetailData news) {
  final sections = <(String, String)>[];
  sections.add((
    'Данные компании',
    news.callout.trim().isNotEmpty
        ? news.callout.trim()
        : 'Признаки из профиля / case-контекста. Пустые поля не заполняем нулями.',
  ));
  sections.add((
    'Факт события',
    news.whatHappened.trim().isNotEmpty
        ? news.whatHappened.trim()
        : (news.body.trim().isNotEmpty
            ? news.body.trim()
            : 'Факты берутся из первоисточника новости.'),
  ));
  final bank = news.bankBody.trim();
  final bankTitle = news.bankTitle.trim();
  sections.add((
    'Аналитика Альфа-Банка',
    bank.isNotEmpty
        ? (bankTitle.isNotEmpty ? '$bankTitle\n$bank' : bank)
        : 'Связанный материал банка не подобран для этого события (или только поиск по корпусу).',
  ));
  final ai = <String>[
    if (news.risk.trim().isNotEmpty) 'Риск / расчёт (модель): ${news.risk.trim()}',
    if (news.opportunity.trim().isNotEmpty)
      'Возможность / пробелы: ${news.opportunity.trim()}',
    if (news.nextAction.trim().isNotEmpty)
      'Следующий шаг: ${news.nextAction.trim()}',
  ];
  sections.add((
    'Вывод модели (AI)',
    ai.isNotEmpty
        ? ai.join('\n')
        : 'Персонализированная интерпретация формируется ассистентом на основе доступных данных.',
  ));
  sections.add((
    'Что пока неизвестно',
    'Поля без подтверждённых данных не заполняются нулями. Уточните финансы или откройте материал банка.',
  ));
  return ConclusionBasisData(sections: sections);
}

NewsDetailData newsDetailFor({
  required ImpactLevel level,
  required String title,
  required String meta,
  String timeLabel = '',
  String sourceUrl = '',
  String sourceLabel = '',
  String levelHint = '',
  String? warning,
  String reason = '',
  AppLocalizations? l10n,
}) {
  if (title.contains('Китай ограничивает')) {
    return chinaExportDetail;
  }
  final when = timeLabel.isNotEmpty
      ? timeLabel
      : (meta.contains('вчера') || meta.contains('Вчера')
          ? 'Вчера'
          : meta);
  final hint = levelHint.isNotEmpty
      ? levelHint
      : (l10n != null ? _levelHintFor(level, l10n) : '');
  return NewsDetailData(
    level: level,
    title: decodeHtmlEntities(title),
    timeLabel: when,
    sourceUrl: sourceUrl,
    sourceLabel: sourceUrl.isNotEmpty
        ? sourceUrl
        : sourceLabel,
    levelHint: hint,
    body: '',
    whatHappened: '',
    concernTitle: 'Почему это про вашу компанию',
    callout: reason.isNotEmpty
        ? decodeHtmlEntities(reason)
        : (warning ?? ''),
    risk: '',
    opportunity: '',
    nextAction: '',
  );
}

String _pickLongestText(Iterable<String> parts) {
  var best = '';
  for (final raw in parts) {
    final t = decodeHtmlEntities(raw).trim();
    if (t.length > best.length) best = t;
  }
  return best;
}

String _humanizeRelevance(Map<String, dynamic>? relevance, AppLocalizations l10n) {
  if (relevance == null) return l10n.whyRelevantFallback;
  final summary = decodeHtmlEntities((relevance['summary'] ?? '').toString()).trim();
  final matches = relevance['matched_features'];
  final bits = <String>[];
  if (matches is List) {
    for (final m in matches.take(3)) {
      if (m is! Map) continue;
      final axis = m['axis']?.toString() ?? '';
      final eventValue = m['event_value']?.toString() ?? '';
      final companyValue = m['company_value']?.toString() ?? '';
      final nodeName = m['node_name']?.toString() ?? '';
      final axisRu = switch (axis) {
        'country' || 'market' => 'рынок',
        'product' => 'продукт',
        'supplier' || 'counterparty' => 'поставщик',
        'industry' || 'okved' => 'отрасль',
        _ => axis.isEmpty ? 'профиль' : axis,
      };
      if (nodeName.isNotEmpty) {
        bits.add('$axisRu: $nodeName');
      } else if (companyValue.isNotEmpty && eventValue.isNotEmpty) {
        bits.add('$axisRu — совпало «$eventValue» с вашим «$companyValue»');
      } else if (companyValue.isNotEmpty) {
        bits.add('$axisRu: $companyValue');
      }
    }
  }
  if (bits.isNotEmpty) {
    final head = summary.isNotEmpty ? summary : 'Совпало с профилем компании';
    return '$head\n\nСовпадения: ${bits.join('; ')}.';
  }
  if (summary.isNotEmpty) return summary;
  return l10n.whyRelevantFallback;
}

NewsDetailData _detailFromApi({
  required Map<String, dynamic> detail,
  Map<String, dynamic>? impact,
  Map<String, dynamic>? evidence,
  required NewsDetailData fallback,
  required AppLocalizations l10n,
}) {
  final impactCard = detail['impact'] is Map
      ? Map<String, dynamic>.from(detail['impact'] as Map)
      : impact;
  final feed = impactCard != null
      ? FeedEvent.fromCard({
          ...impactCard,
          'id': detail['id'] ?? impactCard['id'],
          'title': detail['title'] ?? impactCard['title'],
          'updated_at': detail['occurred_at'] ??
              impactCard['updated_at'] ??
              detail['updated_at'],
          'sources': detail['sources'] ?? impactCard['sources'],
        }, l10n)
      : null;
  final sources = (detail['sources'] as List?) ?? const [];
  String sourceUrl = fallback.sourceUrl;
  String sourceLabel = fallback.sourceLabel;
  final excerpts = <String>[];
  for (final s in sources) {
    if (s is! Map) continue;
    final url = s['url']?.toString() ?? '';
    if (sourceUrl.isEmpty && url.isNotEmpty) {
      sourceUrl = url;
      sourceLabel = url;
    }
    final excerpt = s['excerpt']?.toString() ?? '';
    if (excerpt.trim().isNotEmpty) excerpts.add(excerpt);
  }
  final summary = decodeHtmlEntities((detail['summary'] ?? '').toString());
  final reason = decodeHtmlEntities(
    (impact?['reason_summary'] ?? impactCard?['reason_summary'] ?? '').toString(),
  );
  final body = _pickLongestText([summary, ...excerpts, fallback.body]);
  final expl = impact?['assessment_explanation'];
  String risk = fallback.risk;
  String opportunity = fallback.opportunity;
  String nextAction = fallback.nextAction;
  if (expl is Map) {
    final missing = (expl['missing_data'] as List?)?.join('; ') ?? '';
    final calc = expl['calculation']?.toString() ?? '';
    if (calc.isNotEmpty) risk = decodeHtmlEntities(calc);
    if (missing.isNotEmpty) opportunity = decodeHtmlEntities(missing);
    final summaryExpl = expl['summary']?.toString() ?? '';
    if (summaryExpl.isNotEmpty) nextAction = decodeHtmlEntities(summaryExpl);
  }
  if (risk.isEmpty && reason.isNotEmpty) risk = reason;
  if (opportunity.isEmpty) {
    opportunity = switch (feed?.level ?? fallback.level) {
      ImpactLevel.opportunity => l10n.impactOpportunityHint,
      ImpactLevel.high => 'Проверить поставки, контракты и запас по критичным позициям',
      ImpactLevel.medium => 'Учесть в планах закупок и сроках',
    };
  }
  if (nextAction.isEmpty) {
    nextAction = switch (feed?.level ?? fallback.level) {
      ImpactLevel.high => 'Открыть влияние и разобрать риски с Аспект',
      ImpactLevel.opportunity => 'Посмотреть сценарий и зафиксировать шаги',
      ImpactLevel.medium => 'Сохранить в контроль и уточнить детали у источника',
    };
  }

  String bankTitle = '';
  String bankBody = '';
  final evidenceItems = evidence?['evidence'];
  final status = evidence?['status']?.toString() ?? '';
  if (evidenceItems is List &&
      evidenceItems.isNotEmpty &&
      evidenceItems.first is Map) {
    final m = Map<String, dynamic>.from(evidenceItems.first as Map);
    bankTitle = decodeHtmlEntities(
      (m['document_title'] ?? m['title'] ?? '').toString(),
    );
    bankBody = decodeHtmlEntities(
      (m['text'] ?? m['excerpt'] ?? m['body'] ?? '').toString(),
    );
  } else if (status.isNotEmpty && status != 'available') {
    bankTitle = l10n.alfaBankAnalytics;
    bankBody = l10n.bankEvidenceUnavailable;
  }

  final relevance = detail['relevance'] is Map
      ? Map<String, dynamic>.from(detail['relevance'] as Map)
      : null;
  final callout = _humanizeRelevance(relevance, l10n);
  final whatHappened = body.isNotEmpty
      ? body
      : (reason.isNotEmpty ? reason : summary);
  final level = feed?.level ?? fallback.level;

  return NewsDetailData(
    level: level,
    title: decodeHtmlEntities(
      (detail['title'] ?? fallback.title).toString(),
    ),
    timeLabel: feed?.timeLabel.isNotEmpty == true
        ? feed!.timeLabel
        : fallback.timeLabel,
    sourceUrl: sourceUrl.isNotEmpty ? sourceUrl : '',
    sourceLabel: sourceUrl.isNotEmpty ? sourceUrl : sourceLabel,
    levelHint: fallback.levelHint.isNotEmpty
        ? fallback.levelHint
        : _levelHintFor(level, l10n),
    body: body,
    whatHappened: whatHappened,
    concernTitle: l10n.whyRelevantTitle,
    callout: callout.isNotEmpty ? callout : fallback.callout,
    risk: risk,
    opportunity: opportunity,
    nextAction: nextAction,
    bankTitle: bankTitle,
    bankBody: bankBody,
  );
}

Future<void> openNewsDetail(
  BuildContext context,
  NewsDetailData data, {
  required String backLabel,
  String? eventId,
  VoidCallback? onOpened,
}) {
  onOpened?.call();
  return Navigator.of(context).push(
    AppPageRoute<void>(
      builder: (_) => NewsDetailScreen(
        data: data,
        backLabel: backLabel,
        eventId: eventId,
      ),
    ),
  );
}

class NewsDetailScreen extends StatefulWidget {
  const NewsDetailScreen({
    super.key,
    required this.data,
    required this.backLabel,
    this.eventId,
  });

  final NewsDetailData data;
  final String backLabel;
  final String? eventId;

  @override
  State<NewsDetailScreen> createState() => _NewsDetailScreenState();
}

class _NewsDetailScreenState extends State<NewsDetailScreen> {
  late NewsDetailData data;

  @override
  void initState() {
    super.initState();
    data = widget.data;
    final id = widget.eventId;
    if (id != null && id.isNotEmpty) {
      _loadFromApi(id);
    }
  }

  Future<void> _loadFromApi(String eventId) async {
    // Без видимого прогресса: сразу карточка из ленты,
    // детали с API подмешиваем тихо.
    try {
      final companyId = await AuthStore.companyId();
      final detail = await EventsApi.instance.getEvent(
        eventId,
        companyId: companyId,
      );
      final impact = companyId == null || companyId.isEmpty
          ? null
          : await EventsApi.instance.getImpact(
              eventId,
              companyId: companyId,
            );
      Map<String, dynamic>? evidence;
      try {
        evidence = await EventsApi.instance.bankEvidence(
          eventId,
          companyId: companyId,
        );
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        data = _detailFromApi(
          detail: detail,
          impact: impact,
          evidence: evidence,
          fallback: widget.data,
          l10n: context.l10n,
        );
      });
    } catch (_) {}
  }

  static const _bodySize = 15.13;

  double _titleFontSize(double s) {
    final len = data.title.trim().length;
    if (len > 90) return 18 * s;
    if (len > 55) return 20.5 * s;
    return 24.83 * s;
  }

  Future<void> _openSource() async {
    final uri = Uri.tryParse(data.sourceUrl);
    if (uri == null) return;
    try {
      final ok = await canLaunchUrl(uri);
      if (!ok) return;
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      // Plugin not ready until a full rebuild; ignore soft launch failures.
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    final accent = ImpactColors.accent(data.level);
    final hPad = AppColors.screenPadding * s;
    final sourceShown =
        data.sourceUrl.isNotEmpty ? data.sourceUrl : data.sourceLabel;
    final bodyStyle = AppTypography.regular(
      _bodySize * s,
      color: AppColors.textPrimary,
    ).copyWith(height: 1.5);

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: AppColors.surface,
        body: SafeArea(
          bottom: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Material(
                color: AppColors.surface,
                child: Padding(
                  padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 8 * s),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: GestureDetector(
                      onTap: () => Navigator.of(context).maybePop(),
                      behavior: HitTestBehavior.opaque,
                      child: Text(
                        '‹ ${widget.backLabel}',
                        style: AppTypography.regular(
                          15 * s,
                          color: AppColors.brandRedBright,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(
                    hPad,
                    10 * s,
                    hPad,
                    24 * s + MediaQuery.paddingOf(context).bottom,
                  ),
                  children: [
                    IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Container(
                            width: 5 * s,
                            decoration: BoxDecoration(
                              color: accent,
                              borderRadius: BorderRadius.circular(2.5 * s),
                            ),
                          ),
                          SizedBox(width: 12 * s),
                          Expanded(
                            child: Text(
                              data.title,
                              style: AppTypography.bold(
                                _titleFontSize(s),
                                color: AppColors.textInput,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (data.levelHint.isNotEmpty) ...[
                      SizedBox(height: 8 * s),
                      Padding(
                        padding: EdgeInsets.only(left: 17 * s),
                        child: Text(
                          data.levelHint,
                          style: AppTypography.regular(
                            13 * s,
                            color: AppColors.textMuted,
                          ).copyWith(height: 1.35),
                        ),
                      ),
                    ],
                    SizedBox(height: 8 * s),
                    Padding(
                      padding: EdgeInsets.only(left: 17 * s),
                      child: Text(
                        data.timeLabel,
                        style: AppTypography.regular(
                          13 * s,
                          color: AppColors.textMuted,
                        ),
                      ),
                    ),
                    if (sourceShown.isNotEmpty) ...[
                      SizedBox(height: 8 * s),
                      Padding(
                        padding: EdgeInsets.only(left: 17 * s),
                        child: Row(
                          children: [
                            Text(
                              l10n.sourcePrefix,
                              style: AppTypography.regular(
                                13 * s,
                                color: AppColors.textMuted,
                              ),
                            ),
                            Expanded(
                              child: GestureDetector(
                                onTap: data.sourceUrl.isEmpty
                                    ? null
                                    : _openSource,
                                child: Text(
                                  sourceShown,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: AppTypography.regular(
                                    13 * s,
                                    color: AppColors.brandRed,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                    SizedBox(height: 15 * s),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(20 * s),
                      child: SizedBox(
                        width: double.infinity,
                        height: 160 * s,
                        child: Image.asset(
                          data.heroAsset,
                          fit: BoxFit.cover,
                          errorBuilder: (context, error, stackTrace) =>
                              ColoredBox(color: AppColors.progressTrack),
                        ),
                      ),
                    ),
                    if (data.body.isNotEmpty) ...[
                      SizedBox(height: 16 * s),
                      Text(data.body, style: bodyStyle),
                    ],
                    if (data.whatHappened.isNotEmpty &&
                        data.whatHappened != data.body) ...[
                      SizedBox(height: 20 * s),
                      Text(
                        l10n.whatHappened,
                        style: AppTypography.bold(
                          _bodySize * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 8 * s),
                      Text(data.whatHappened, style: bodyStyle),
                    ] else if (data.body.isEmpty &&
                        data.whatHappened.isNotEmpty) ...[
                      SizedBox(height: 20 * s),
                      Text(
                        l10n.whatHappened,
                        style: AppTypography.bold(
                          _bodySize * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 8 * s),
                      Text(data.whatHappened, style: bodyStyle),
                    ],
                    if (data.callout.isNotEmpty) ...[
                      SizedBox(height: 20 * s),
                      _ConcernCard(
                        title: data.concernTitle,
                        body: data.callout,
                      ),
                    ],
                    SizedBox(height: 20 * s),
                    Text(
                      l10n.whatItMeansForYou,
                      style: AppTypography.bold(
                        _bodySize * s,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    if (data.risk.isNotEmpty ||
                        data.opportunity.isNotEmpty ||
                        data.nextAction.isNotEmpty) ...[
                      SizedBox(height: 6 * s),
                      Text(
                        'Вывод модели (AI), не позиция банка',
                        style: AppTypography.medium(
                          11 * s,
                          color: AppColors.textMuted,
                        ),
                      ),
                    ],
                    SizedBox(height: 10 * s),
                    if (data.risk.isNotEmpty)
                      _ChangeLine(label: l10n.riskLabel, text: data.risk),
                    if (data.risk.isNotEmpty && data.opportunity.isNotEmpty)
                      SizedBox(height: 8 * s),
                    if (data.opportunity.isNotEmpty)
                      _ChangeLine(
                        label: l10n.opportunityLabel,
                        text: data.opportunity,
                      ),
                    if (data.nextAction.isNotEmpty) ...[
                      SizedBox(height: 20 * s),
                      Text(
                        l10n.nextActionTitle,
                        style: AppTypography.bold(
                          _bodySize * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 8 * s),
                      Text(
                        data.nextAction,
                        style: AppTypography.regular(
                          _bodySize * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                    ],
                    if (data.bankTitle.isNotEmpty ||
                        data.bankBody.isNotEmpty) ...[
                      SizedBox(height: 20 * s),
                      Text(
                        'Аналитика Альфа-Банка (не AI)',
                        style: AppTypography.medium(
                          11 * s,
                          color: AppColors.brandRedBright,
                        ),
                      ),
                      SizedBox(height: 8 * s),
                      _BankCard(
                        title: data.bankTitle.isNotEmpty
                            ? data.bankTitle
                            : l10n.alfaBankAnalytics,
                        body: data.bankBody,
                        analyticsLabel: l10n.alfaBankAnalytics,
                        materialLinkLabel: l10n.viewMaterial,
                        onMaterialTap: () => openBankMaterialScreen(context),
                      ),
                      SizedBox(height: 24 * s),
                    ],
                    Center(
                      child: SizedBox(
                        width: 342 * s,
                        height: 52 * s,
                        child: FilledButton(
                          onPressed: () {
                            final impact = switch (data.level) {
                              ImpactLevel.high => l10n.impactHigh,
                              ImpactLevel.medium => l10n.impactMedium,
                              ImpactLevel.opportunity =>
                                l10n.impactOpportunity,
                            };
                            openChatScreen(
                              context,
                              ChatScreenData(
                                title: data.title,
                                meta: '$impact · ${data.timeLabel}',
                                level: data.level,
                                backLabel: widget.backLabel,
                                eventId: widget.eventId,
                              ),
                            );
                          },
                          style: FilledButton.styleFrom(
                            backgroundColor: AppColors.brandRed,
                            foregroundColor: AppColors.onBrand,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(16 * s),
                            ),
                            textStyle: AppTypography.bold(
                              14.06 * s,
                              color: AppColors.onBrand,
                            ),
                          ),
                          child: Text(
                            l10n.discussWithAspect,
                            textAlign: TextAlign.center,
                            style: AppTypography.bold(
                              14.06 * s,
                              color: AppColors.onBrand,
                            ),
                          ),
                        ),
                      ),
                    ),
                    SizedBox(height: 12 * s),
                    GestureDetector(
                      onTap: () => openConclusionBasisScreen(
                        context,
                        data: _basisFromNews(data),
                      ),
                      behavior: HitTestBehavior.opaque,
                      child: Text(
                        l10n.conclusionBasisPrompt,
                        textAlign: TextAlign.center,
                        style: AppTypography.medium(
                          13 * s,
                          color: AppColors.brandRedBright,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ConcernCard extends StatelessWidget {
  const _ConcernCard({
    required this.title,
    required this.body,
  });

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(7 * s),
        border: Border.all(color: AppColors.border, width: 1),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(
              alpha: AppColors.isDark ? 0.35 : 0.17,
            ),
            offset: Offset(-1 * s, -1 * s),
            blurRadius: 14.2 * s,
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(7 * s),
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(width: 3 * s, color: AppColors.brandRed),
              Expanded(
                child: Padding(
                  padding: EdgeInsets.all(16 * s),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: AppTypography.bold(
                          15.13 * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 6 * s),
                      Text(
                        body,
                        style: AppTypography.regular(
                          15.13 * s,
                          color: AppColors.textPrimary,
                        ).copyWith(height: 1.45),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BankCard extends StatelessWidget {
  const _BankCard({
    required this.title,
    required this.body,
    required this.analyticsLabel,
    required this.materialLinkLabel,
    this.onMaterialTap,
  });

  final String title;
  final String body;
  final String analyticsLabel;
  final String materialLinkLabel;
  final VoidCallback? onMaterialTap;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(7 * s),
        border: Border.all(color: AppColors.border, width: 1),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(
              alpha: AppColors.isDark ? 0.35 : 0.13,
            ),
            offset: Offset(-1 * s, 0),
            blurRadius: 12.8 * s,
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(7 * s),
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(width: 3 * s, color: AppColors.brandRed),
              Expanded(
                child: Padding(
                  padding: EdgeInsets.all(16 * s),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            height: 19 * s,
                            padding: EdgeInsets.symmetric(horizontal: 8 * s),
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: AppColors.brandRed,
                              borderRadius: BorderRadius.circular(6.56 * s),
                            ),
                            child: Text(
                              analyticsLabel,
                              style: AppTypography.bold(
                                9.19 * s,
                                color: AppColors.onBrand,
                              ),
                            ),
                          ),
                          SizedBox(width: 3 * s),
                          Container(
                            width: 68 * s,
                            height: 19 * s,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: AppColors.card,
                              borderRadius: BorderRadius.circular(6.56 * s),
                              border: Border.all(
                                color: AppColors.brandRedBright,
                                width: 1,
                              ),
                            ),
                            child: SvgPicture.asset(
                              'assets/images/alfa_bank_logo.svg',
                              width: 51 * s,
                              height: 10 * s,
                              fit: BoxFit.contain,
                              colorFilter: AppColors.isDark
                                  ? const ColorFilter.mode(
                                      Color(0xFFFF7A70),
                                      BlendMode.srcIn,
                                    )
                                  : null,
                            ),
                          ),
                        ],
                      ),
                      SizedBox(height: 14 * s),
                      Text(
                        title,
                        style: AppTypography.bold(
                          15.13 * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 8 * s),
                      Text(
                        body,
                        style: AppTypography.regular(
                          15.13 * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 14 * s),
                      _RedLink(
                        label: materialLinkLabel,
                        onTap: onMaterialTap,
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RedLink extends StatelessWidget {
  const _RedLink({required this.label, this.onTap});

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            label,
            style: AppTypography.bold(13 * s, color: AppColors.brandRedBright),
          ),
          SizedBox(width: 4 * s),
          Icon(
            Icons.arrow_forward,
            size: 14 * s,
            color: AppColors.brandRedBright,
          ),
        ],
      ),
    );
  }
}

class _ChangeLine extends StatelessWidget {
  const _ChangeLine({required this.label, required this.text});

  final String label;
  final String text;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: '$label ',
            style: AppTypography.medium(15.13 * s, color: AppColors.brandRed),
          ),
          TextSpan(
            text: text,
            style: AppTypography.regular(
              15.13 * s,
              color: AppColors.textPrimary,
            ).copyWith(height: 1.45),
          ),
        ],
      ),
    );
  }
}
