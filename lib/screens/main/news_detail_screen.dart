import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/auth_widgets.dart';
import '../../widgets/main_widgets.dart';

class NewsDetailData {
  const NewsDetailData({
    required this.level,
    required this.title,
    required this.timeLabel,
    required this.lead,
    required this.body,
    required this.whatHappened,
    required this.risk,
    required this.opportunity,
    this.heroAsset = 'assets/images/news_detail_hero.jpg',
    this.ctaLabel = 'Обсудить с Аспект',
    this.ctaCaption = 'Аспект подготовил 3 варианта действий',
  });

  final ImpactLevel level;
  final String title;
  final String timeLabel;
  final String lead;
  final String body;
  final String whatHappened;
  final String risk;
  final String opportunity;
  final String heroAsset;
  final String ctaLabel;
  final String ctaCaption;
}

const chinaExportDetail = NewsDetailData(
  level: ImpactLevel.high,
  title: 'Китай ограничивает экспорт электроники',
  timeLabel: 'Сегодня 08:24',
  lead:
      'Китай расширил ограничения на экспорт отдельных категорий электроники и компонентов. Мера затрагивает поставки продукции двойного назначения.',
  body:
      'Новые правила могут повлиять на сроки поставок и условия контрактов для зарубежных покупателей. Подробные требования будут опубликованы в ближайшие дни.',
  whatHappened:
      'Ограничения вводятся поэтапно и распространяются на ряд технологических категорий.',
  risk: 'Задержка поставок критичных компонентов',
  opportunity: 'Заранее пересмотреть пул поставщиков',
);

NewsDetailData newsDetailFor({
  required ImpactLevel level,
  required String title,
  required String meta,
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
    lead: title,
    body:
        'Аспект собрал ключевые факты по событию и оценил влияние на ваш профиль компании.',
    whatHappened: 'Сигнал отмечен в ленте как значимый для вашей отрасли.',
    risk: 'Возможны изменения условий закупок и сроков',
    opportunity: 'Пересмотреть сценарии поставок заранее',
  );
}

Future<void> openNewsDetail(
  BuildContext context,
  NewsDetailData data, {
  VoidCallback? onOpened,
}) {
  onOpened?.call();
  return Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => NewsDetailScreen(data: data),
    ),
  );
}

class NewsDetailScreen extends StatelessWidget {
  const NewsDetailScreen({super.key, required this.data});

  final NewsDetailData data;

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
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 0),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: GestureDetector(
                    onTap: () => Navigator.of(context).maybePop(),
                    behavior: HitTestBehavior.opaque,
                    child: Text(
                      '‹ События',
                      style: AppTypography.regular(
                        15 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                  ),
                ),
              ),
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(hPad, 18 * s, hPad, 24 * s),
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          width: 5 * s,
                          height: 60 * s,
                          margin: EdgeInsets.only(top: 2 * s),
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
                              24 * s,
                              color: AppColors.textInput,
                            ).copyWith(height: 1.15),
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: 10 * s),
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
                    SizedBox(height: 18 * s),
                    _MediaFrame(
                      child: Image.asset(
                        data.heroAsset,
                        fit: BoxFit.cover,
                        width: double.infinity,
                        height: 201 * s,
                        errorBuilder: (context, error, stackTrace) => ColoredBox(
                          color: AppColors.progressTrack,
                          child: SizedBox(height: 201 * s),
                        ),
                      ),
                    ),
                    SizedBox(height: 18 * s),
                    Text(
                      data.lead,
                      style: AppTypography.bold(
                        15 * s,
                        color: AppColors.textPrimary,
                      ).copyWith(height: 1.35),
                    ),
                    SizedBox(height: 12 * s),
                    Text(
                      data.body,
                      style: AppTypography.regular(
                        14 * s,
                        color: AppColors.textPrimary,
                      ).copyWith(height: 1.4),
                    ),
                    SizedBox(height: 20 * s),
                    Divider(height: 1 * s, color: AppColors.divider),
                    SizedBox(height: 18 * s),
                    Text(
                      'Что произошло',
                      style: AppTypography.bold(
                        17 * s,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: 10 * s),
                    Text(
                      data.whatHappened,
                      style: AppTypography.regular(
                        14 * s,
                        color: AppColors.textPrimary,
                      ).copyWith(height: 1.4),
                    ),
                    SizedBox(height: 18 * s),
                    _MediaFrame(
                      child: ColoredBox(
                        color: AppColors.progressTrack,
                        child: SizedBox(
                          height: 140 * s,
                          width: double.infinity,
                        ),
                      ),
                    ),
                    SizedBox(height: 18 * s),
                    Text(
                      'Что изменится',
                      style: AppTypography.bold(
                        17 * s,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: 12 * s),
                    _ChangeLine(
                      label: 'Риск:',
                      text: data.risk,
                      labelColor: AppColors.brandRed,
                    ),
                    SizedBox(height: 10 * s),
                    _ChangeLine(
                      label: 'Возможность:',
                      text: data.opportunity,
                      labelColor: AppColors.brandRed,
                    ),
                    SizedBox(height: 28 * s),
                    AuthPrimaryButton(
                      label: data.ctaLabel,
                      onPressed: () {},
                    ),
                    SizedBox(height: 12 * s),
                    Text(
                      data.ctaCaption,
                      textAlign: TextAlign.center,
                      style: AppTypography.regular(
                        13 * s,
                        color: AppColors.textSecondary,
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

class _MediaFrame extends StatelessWidget {
  const _MediaFrame({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(19 * s),
        border: Border.all(color: Colors.black, width: 1),
      ),
      clipBehavior: Clip.antiAlias,
      child: child,
    );
  }
}

class _ChangeLine extends StatelessWidget {
  const _ChangeLine({
    required this.label,
    required this.text,
    required this.labelColor,
  });

  final String label;
  final String text;
  final Color labelColor;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: '$label ',
            style: AppTypography.bold(14 * s, color: labelColor)
                .copyWith(height: 1.35),
          ),
          TextSpan(
            text: text,
            style: AppTypography.bold(14 * s, color: AppColors.textPrimary)
                .copyWith(height: 1.35),
          ),
        ],
      ),
    );
  }
}
