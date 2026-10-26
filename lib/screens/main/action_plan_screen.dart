import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/app_localizations.dart';
import '../../navigation/app_page_route.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import 'confirm_plan_screen.dart';

Future<ConfirmPlanData?> openActionPlanScreen(
  BuildContext context, {
  required String eventTitle,
}) {
  return Navigator.of(context).push<ConfirmPlanData>(
    AppPageRoute<ConfirmPlanData>(
      builder: (_) => ActionPlanScreen(eventTitle: eventTitle),
    ),
  );
}

class ActionPlanScreen extends StatelessWidget {
  const ActionPlanScreen({super.key, required this.eventTitle});

  final String eventTitle;

  static const _items = [
    (
      'Проверить условия долга',
      'Собрать даты пересмотра и условия по действующим договорам.',
      'Подходит, если условия ещё не собраны.',
      [
        'Собрать условия действующих кредитов',
        'Уточнить даты пересмотра ставок',
        'Вернуться к сравнению вариантов',
      ],
      'Сначала уточняем фактические условия, чтобы не выбирать решение вслепую.',
    ),
    (
      'Оценить фиксацию ставки',
      'Запросить доступные условия и сравнить стоимость с текущими договорами.',
      'Нужны предложения и стоимость перехода.',
      [
        'Запросить условия фиксации ставки',
        'Сравнить стоимость с текущими договорами',
        'Вернуться к сравнению вариантов',
      ],
      'Сравниваем стоимость перехода, чтобы выбрать фиксацию осознанно.',
    ),
    (
      'Обновить план ликвидности',
      'Проверить ближайшие платежи и доступные источники покрытия.',
      'Нужны график платежей и остатки.',
      [
        'Собрать ближайшие платежи',
        'Проверить источники покрытия',
        'Вернуться к сравнению вариантов',
      ],
      'Сначала смотрим платежи и остатки, чтобы обновить план ликвидности.',
    ),
  ];

  Future<void> _select(BuildContext context, int index) async {
    final item = _items[index];
    final data = ConfirmPlanData(
      actionTitle: item.$1,
      eventTitle: eventTitle,
      steps: item.$4,
      reason: item.$5,
    );
    final confirmed = await openConfirmPlanScreen(context, data);
    if (confirmed == true && context.mounted) {
      Navigator.of(context).pop(data);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: AppColors.surface,
        body: SafeArea(
          bottom: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 8 * s),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: GestureDetector(
                    onTap: () => Navigator.of(context).maybePop(),
                    behavior: HitTestBehavior.opaque,
                    child: Text(
                      '‹ ${l10n.discussionBack}',
                      style: AppTypography.regular(
                        15 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ),
                ),
              ),
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(
                    hPad,
                    8 * s,
                    hPad,
                    16 * s + bottom,
                  ),
                  children: [
                    Text(
                      l10n.actionOptions,
                      style: AppTypography.bold(
                        24.83 * s,
                        color: AppColors.textInput,
                      ),
                    ),
                    SizedBox(height: 10 * s),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: IntrinsicWidth(
                        child: Container(
                          height: 25 * s,
                          padding: EdgeInsets.symmetric(horizontal: 8 * s),
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: AppColors.brandRed,
                            borderRadius: BorderRadius.circular(6 * s),
                          ),
                          child: Text(
                            l10n.qualityComparison,
                            softWrap: false,
                            style: AppTypography.medium(
                              9.4 * s,
                              color: AppColors.onBrand,
                            ),
                          ),
                        ),
                      ),
                    ),
                    SizedBox(height: 20 * s),
                    for (var i = 0; i < _items.length; i++) ...[
                      if (i > 0) SizedBox(height: 12 * s),
                      _ActionCard(
                        index: i + 1,
                        title: _items[i].$1,
                        body: _items[i].$2,
                        note: _items[i].$3,
                        selectLabel: l10n.selectForPlan,
                        onSelect: () => _select(context, i),
                      ),
                    ],
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

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.index,
    required this.title,
    required this.body,
    required this.note,
    required this.selectLabel,
    required this.onSelect,
  });

  final int index;
  final String title;
  final String body;
  final String note;
  final String selectLabel;
  final VoidCallback onSelect;

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
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      IntrinsicWidth(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Text(
                              '$index',
                              textAlign: TextAlign.center,
                              style: AppTypography.medium(
                                28.37 * s,
                                color: AppColors.brandRedBright,
                              ),
                            ),
                            SizedBox(height: 2 * s),
                            Container(
                              height: 2 * s,
                              color: AppColors.brandRedBright,
                            ),
                          ],
                        ),
                      ),
                      SizedBox(height: 8 * s),
                      Text(
                        title,
                        style: AppTypography.bold(
                          15.13 * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 10 * s),
                      Text(
                        body,
                        style: AppTypography.regular(
                          15.13 * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 8 * s),
                      Text(
                        note,
                        style: AppTypography.regular(
                          13 * s,
                          color: AppColors.textSecondary,
                        ).copyWith(
                          decoration: TextDecoration.underline,
                          decorationColor: AppColors.textSecondary,
                          decorationStyle: TextDecorationStyle.solid,
                        ),
                      ),
                      SizedBox(height: 21 * s),
                      GestureDetector(
                        onTap: onSelect,
                        behavior: HitTestBehavior.opaque,
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            Text(
                              selectLabel,
                              style: AppTypography.bold(
                                13 * s,
                                color: AppColors.brandRedBright,
                              ),
                            ),
                            SizedBox(width: 4 * s),
                            Icon(
                              Icons.arrow_forward,
                              size: 14 * s,
                              color: AppColors.brandRedBright,
                            ),
                          ],
                        ),
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
