import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/app_localizations.dart';
import '../../navigation/app_page_route.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

class ConclusionBasisData {
  const ConclusionBasisData({
    this.backLabel = 'Разбор события',
    this.sections = const [
      (
        'Данные компании',
        'Признаки из профиля / case-контекста. Пустые поля не заполняем нулями.',
      ),
      (
        'Факт события',
        'Факты берутся из первоисточника новости.',
      ),
      (
        'Аналитика Альфа-Банка',
        'Материал банка подтягивается из evidence API, если доступен.',
      ),
      (
        'Вывод модели (AI)',
        'Отделяется от позиции банка в разборе и в чате.',
      ),
      (
        'Что пока неизвестно',
        'Уточните финансы, контрагентов или откройте материал банка.',
      ),
    ],
  });

  final String backLabel;
  final List<(String, String)> sections;
}

Future<void> openConclusionBasisScreen(
  BuildContext context, {
  ConclusionBasisData data = const ConclusionBasisData(),
}) {
  return Navigator.of(context).push(
    AppPageRoute<void>(
      builder: (_) => ConclusionBasisScreen(data: data),
    ),
  );
}

class ConclusionBasisScreen extends StatelessWidget {
  const ConclusionBasisScreen({super.key, required this.data});

  final ConclusionBasisData data;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final backLabel = data.backLabel == 'Разбор события'
        ? l10n.eventAnalysis
        : data.backLabel;

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
                child: Row(
                  children: [
                    Expanded(
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: GestureDetector(
                          onTap: () => Navigator.of(context).maybePop(),
                          behavior: HitTestBehavior.opaque,
                          child: Text(
                            '‹ $backLabel',
                            style: AppTypography.regular(
                              15 * s,
                              color: AppColors.brandRedBright,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 12 * s),
                child: Text(
                  l10n.conclusionBasis,
                  style: AppTypography.bold(22 * s, color: AppColors.textPrimary),
                ),
              ),
              Expanded(
                child: ListView.separated(
                  padding: EdgeInsets.fromLTRB(hPad, 0, hPad, 24 * s + bottom),
                  itemCount: data.sections.length,
                  separatorBuilder: (_, _) => SizedBox(height: 16 * s),
                  itemBuilder: (context, i) {
                    final (title, body) = data.sections[i];
                    final isBank = title.contains('Альфа-Банка');
                    final isAi =
                        title.contains('AI') || title.contains('модели');
                    return Container(
                      width: double.infinity,
                      padding: EdgeInsets.all(16 * s),
                      decoration: BoxDecoration(
                        color: AppColors.card,
                        borderRadius: BorderRadius.circular(12 * s),
                        border: Border.all(
                          color: isBank
                              ? AppColors.brandRedBright.withValues(alpha: 0.55)
                              : AppColors.border,
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            style: AppTypography.bold(
                              14 * s,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          if (isBank || isAi) ...[
                            SizedBox(height: 6 * s),
                            Text(
                              isBank
                                  ? 'Позиция / материал банка'
                                  : 'Сформировано моделью',
                              style: AppTypography.medium(
                                11 * s,
                                color: isBank
                                    ? AppColors.brandRedBright
                                    : AppColors.textMuted,
                              ),
                            ),
                          ],
                          SizedBox(height: 8 * s),
                          Text(
                            body,
                            style: AppTypography.regular(
                              13 * s,
                              color: AppColors.textPrimary,
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
