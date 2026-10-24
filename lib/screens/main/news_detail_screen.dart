import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/events_api.dart';
import '../../api/feed_models.dart';
import '../../l10n/app_localizations.dart';
import '../../services/auth_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
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
    this.bankTitle = 'Ключевая ставка ЦБ РФ',
    this.bankBody =
        'Место для подтверждённого фрагмента из предоставленного документа. В макете позиция банка не придумана.',
  });

  final ImpactLevel level;
  final String title;
  final String timeLabel;
  final String sourceUrl;
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

const chinaExportDetail = NewsDetailData(
  level: ImpactLevel.high,
  title: 'Китай ограничивает экспорт электроники',
  timeLabel: 'Сегодня 08:24',
  sourceUrl: 'https://pin.it/2FPGIqkTI',
  body:
      'Китай расширил ограничения на экспорт отдельных категорий электроники и компонентов. Мера затрагивает поставки продукции двойного назначения.\n\nНовые правила могут повлиять на сроки поставок и условия контрактов для зарубежных покупателей. Подробные требования будут опубликованы в ближайшие дни.',
  whatHappened:
      'Ограничения вводятся поэтапно и распространяются на ряд технологических категорий.',
  concernTitle: 'Почему касается СеверПрома',
  callout: 'Китай - один из рынков поставок вашей компании',
  risk: 'Задержка поставок критичных компонентов',
  opportunity: 'Заранее пересмотреть пул поставщиков',
  nextAction:
      'Заранее пересмотреть пул поставщиков. Уточнить структуру долга и обсудить, какие условия требуют внимания.',
);

NewsDetailData newsDetailFor({
  required ImpactLevel level,
  required String title,
  required String meta,
  String? warning,
}) {
  if (title.contains('Китай ограничивает')) {
    return chinaExportDetail;
  }
  final time = meta.contains('вчера') || meta.contains('Вчера')
      ? 'Вчера'
      : meta.contains('08:24')
          ? 'Сегодня 08:24'
          : meta;
  return NewsDetailData(
    level: level,
    title: title,
    timeLabel: time,
    sourceUrl: 'https://pin.it/2FPGIqkTI',
    body:
        'Аспект собрал ключевые факты по событию и оценил влияние на ваш профиль компании.',
    whatHappened: 'Сигнал отмечен в ленте как значимый для вашей отрасли.',
    concernTitle: 'Почему касается вашей компании',
    callout: warning ?? 'Событие связано с рынками и поставками вашей компании',
    risk: 'Возможны изменения условий закупок и сроков',
    opportunity: 'Пересмотреть сценарии поставок заранее',
    nextAction: 'Пересмотреть сценарии поставок заранее.',
  );
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
        }, l10n)
      : null;
  final sources = (detail['sources'] as List?) ?? const [];
  String sourceUrl = fallback.sourceUrl;
  for (final s in sources) {
    if (s is Map && s['url'] != null && s['url'].toString().isNotEmpty) {
      sourceUrl = s['url'].toString();
      break;
    }
  }
  final summary = (detail['summary'] ?? '').toString();
  final reason = (impact?['reason_summary'] ??
          impactCard?['reason_summary'] ??
          '')
      .toString();
  final expl = impact?['assessment_explanation'];
  String risk = fallback.risk;
  String opportunity = fallback.opportunity;
  String nextAction = fallback.nextAction;
  if (expl is Map) {
    final missing = (expl['missing_data'] as List?)?.join('; ') ?? '';
    final calc = expl['calculation']?.toString() ?? '';
    if (calc.isNotEmpty) risk = calc;
    if (missing.isNotEmpty) opportunity = missing;
    final summaryExpl = expl['summary']?.toString() ?? '';
    if (summaryExpl.isNotEmpty) nextAction = summaryExpl;
  }
  String bankTitle = fallback.bankTitle;
  String bankBody = fallback.bankBody;
  final materials = evidence?['materials'] ?? evidence?['items'];
  if (materials is List && materials.isNotEmpty && materials.first is Map) {
    final m = Map<String, dynamic>.from(materials.first as Map);
    bankTitle = (m['title'] ?? bankTitle).toString();
    bankBody = (m['excerpt'] ?? m['body'] ?? bankBody).toString();
  }
  return NewsDetailData(
    level: feed?.level ?? fallback.level,
    title: (detail['title'] ?? fallback.title).toString(),
    timeLabel: feed?.meta ?? fallback.timeLabel,
    sourceUrl: sourceUrl,
    body: summary.isNotEmpty ? summary : fallback.body,
    whatHappened: reason.isNotEmpty ? reason : fallback.whatHappened,
    concernTitle: fallback.concernTitle,
    callout: reason.isNotEmpty ? reason : fallback.callout,
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
    MaterialPageRoute<void>(
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
  bool _loading = false;

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
    setState(() => _loading = true);
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
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  static const _bodySize = 15.13;

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

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: AppColors.surface,
        body: SafeArea(
          bottom: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_loading)
                const LinearProgressIndicator(minHeight: 2),
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
                          color: AppColors.brandRed,
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
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Container(
                          width: 5 * s,
                          height: 48 * s,
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
                              24.83 * s,
                              color: AppColors.textInput,
                            ),
                          ),
                        ),
                      ],
                    ),
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
                    SizedBox(height: 8 * s),
                    Padding(
                      padding: EdgeInsets.only(left: 17 * s),
                      child: Text.rich(
                        TextSpan(
                          style: AppTypography.regular(
                            13 * s,
                            color: AppColors.textMuted,
                          ),
                          children: [
                            TextSpan(text: l10n.sourcePrefix),
                            WidgetSpan(
                              alignment: PlaceholderAlignment.baseline,
                              baseline: TextBaseline.alphabetic,
                              child: GestureDetector(
                                onTap: _openSource,
                                child: Text(
                                  data.sourceUrl,
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
                    ),
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
                    SizedBox(height: 16 * s),
                    Text(
                      data.body,
                      style: AppTypography.regular(
                        _bodySize * s,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: 20 * s),
                    Text(
                      l10n.whatHappened,
                      style: AppTypography.bold(
                        _bodySize * s,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: 8 * s),
                    Text(
                      data.whatHappened,
                      style: AppTypography.regular(
                        _bodySize * s,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: 20 * s),
                    _ConcernCard(
                      title: data.concernTitle,
                      body: data.callout,
                    ),
                    SizedBox(height: 20 * s),
                    Text(
                      l10n.whatItMeansForYou,
                      style: AppTypography.bold(
                        _bodySize * s,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: 10 * s),
                    _ChangeLine(label: l10n.riskLabel, text: data.risk),
                    SizedBox(height: 8 * s),
                    _ChangeLine(
                      label: l10n.opportunityLabel,
                      text: data.opportunity,
                    ),
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
                    SizedBox(height: 20 * s),
                    _BankCard(
                      title: data.bankTitle,
                      body: data.bankBody,
                      analyticsLabel: l10n.alfaBankAnalytics,
                      materialLinkLabel: l10n.viewMaterial,
                      onMaterialTap: () => openBankMaterialScreen(context),
                    ),
                    SizedBox(height: 24 * s),
                    Center(
                      child: SizedBox(
                        width: 342 * s,
                        height: 52 * s,
                        child: FilledButton(
                          onPressed: () {
                            final impact = switch (data.level) {
                              ImpactLevel.high => l10n.impactHigh,
                              ImpactLevel.medium => l10n.impactMedium,
                              ImpactLevel.opportunity => l10n.impactOpportunity,
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
                            foregroundColor: AppColors.surface,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(16 * s),
                            ),
                            textStyle: AppTypography.bold(
                              14.06 * s,
                              color: AppColors.surface,
                            ),
                          ),
                          child: Text(
                            l10n.discussWithAspect,
                            textAlign: TextAlign.center,
                            style: AppTypography.bold(
                              14.06 * s,
                              color: AppColors.surface,
                            ),
                          ),
                        ),
                      ),
                    ),
                    SizedBox(height: 12 * s),
                    GestureDetector(
                      onTap: () => openConclusionBasisScreen(context),
                      behavior: HitTestBehavior.opaque,
                      child: Text(
                        l10n.conclusionBasisPrompt,
                        textAlign: TextAlign.center,
                        style: AppTypography.medium(
                          13 * s,
                          color: AppColors.brandRed,
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
  const _ConcernCard({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 16 * s, 16 * s),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(7 * s),
        border: Border(
          left: BorderSide(color: AppColors.brandRed, width: 3 * s),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.17),
            offset: Offset(-1 * s, -1 * s),
            blurRadius: 14.2 * s,
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: AppTypography.bold(
              15.13 * s,
              color: const Color.fromRGBO(24, 27, 34, 1),
            ),
          ),
          SizedBox(height: 2 * s),
          Text(
            body,
            style: AppTypography.regular(
              15.13 * s,
              color: AppColors.textPrimary,
            ),
          ),
        ],
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
      padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 16 * s, 16 * s),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(7 * s),
        border: Border(
          left: BorderSide(color: AppColors.brandRed, width: 3 * s),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.13),
            offset: Offset(-1 * s, 0),
            blurRadius: 12.8 * s,
          ),
        ],
      ),
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
                  style: AppTypography.bold(9.19 * s, color: AppColors.surface),
                ),
              ),
              SizedBox(width: 3 * s),
              Container(
                width: 68 * s,
                height: 19 * s,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(6.56 * s),
                  border: Border.all(color: AppColors.brandRed, width: 1),
                ),
                child: SvgPicture.asset(
                  'assets/images/alfa_bank_logo.svg',
                  width: 51 * s,
                  height: 10 * s,
                  fit: BoxFit.contain,
                ),
              ),
            ],
          ),
          SizedBox(height: 14 * s),
          Text(
            title,
            style: AppTypography.bold(
              15.13 * s,
              color: const Color.fromRGBO(24, 27, 34, 1),
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
            style: AppTypography.bold(13 * s, color: AppColors.brandRed),
          ),
          SizedBox(width: 4 * s),
          Icon(
            Icons.arrow_forward,
            size: 14 * s,
            color: AppColors.brandRed,
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
            ),
          ),
        ],
      ),
    );
  }
}
