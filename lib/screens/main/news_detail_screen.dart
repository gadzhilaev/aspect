import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';

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

Future<void> openNewsDetail(
  BuildContext context,
  NewsDetailData data, {
  required String backLabel,
  VoidCallback? onOpened,
}) {
  onOpened?.call();
  return Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => NewsDetailScreen(
        data: data,
        backLabel: backLabel,
      ),
    ),
  );
}

class NewsDetailScreen extends StatelessWidget {
  const NewsDetailScreen({
    super.key,
    required this.data,
    required this.backLabel,
  });

  final NewsDetailData data;
  final String backLabel;

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
    final s = context.scale;
    final accent = ImpactColors.accent(data.level);
    final hPad = AppColors.screenPadding * s;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
      ),
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
                        '‹ $backLabel',
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
                            const TextSpan(text: 'Источник: '),
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
                              const ColoredBox(color: AppColors.progressTrack),
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
                      'Что произошло',
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
                      'Что это значит для вас',
                      style: AppTypography.bold(
                        _bodySize * s,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: 10 * s),
                    _ChangeLine(label: 'Риск:', text: data.risk),
                    SizedBox(height: 8 * s),
                    _ChangeLine(label: 'Возможность:', text: data.opportunity),
                    SizedBox(height: 20 * s),
                    Text(
                      'Следующее действие',
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
                              ImpactLevel.high => 'Высокое влияние',
                              ImpactLevel.medium => 'Среднее влияние',
                              ImpactLevel.opportunity => 'Возможность',
                            };
                            openChatScreen(
                              context,
                              ChatScreenData(
                                title: data.title,
                                meta: '$impact · ${data.timeLabel}',
                                level: data.level,
                                backLabel: backLabel,
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
                            data.ctaLabel,
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
                        data.ctaCaption,
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
    this.onMaterialTap,
  });

  final String title;
  final String body;
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
                  'Аналитика Альфа-Банка',
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
            label: 'Посмотреть материал',
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
