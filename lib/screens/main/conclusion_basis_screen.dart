import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../l10n/app_localizations.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

class ConclusionBasisData {
  const ConclusionBasisData({
    this.backLabel = 'Разбор события',
    this.sections = const [
      (
        'Данные компании',
        'Наличие кредитных продуктов\nИсточник: demo-профиль СеверПрома',
      ),
      (
        'Факт события',
        'Сохранение ставки, а не ее повышение. Дата и ссылка берутся из источника',
      ),
      (
        'Аналитика банка',
        'Связанный документ Альфа-Банка. Фрагмент и страница доступны при загрузке.',
      ),
      (
        'Что пока неизвестно',
        'Сумма долга, тип ставки и сроки пересмотра. Персональная сумма эффекта не рассчитана.',
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
    MaterialPageRoute<void>(
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
    const titleDark = Color.fromRGBO(24, 35, 44, 1);
    const heading = Color.fromRGBO(24, 27, 34, 1);
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
                              color: AppColors.brandRed,
                            ),
                          ),
                        ),
                      ),
                    ),
                    const _AlfaBankBadge(),
                  ],
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
                    Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: '${l10n.eventAnalysis}\n',
                            style: AppTypography.bold(
                              24.83 * s,
                              color: titleDark,
                            ),
                          ),
                          TextSpan(
                            text: l10n.conclusionBasisHeading,
                            style: AppTypography.bold(
                              24.83 * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                        ],
                      ),
                    ),
                    SizedBox(height: 24 * s),
                    for (var i = 0; i < data.sections.length; i++) ...[
                      if (i > 0) ...[
                        SizedBox(height: 24 * s),
                        Divider(
                          height: 1 * s,
                          thickness: 1 * s,
                          color: Colors.black.withValues(alpha: 0.08),
                        ),
                        SizedBox(height: 16 * s),
                      ],
                      Text(
                        data.sections[i].$1,
                        style: AppTypography.bold(15.13 * s, color: heading),
                      ),
                      SizedBox(height: 8 * s),
                      Text(
                        data.sections[i].$2,
                        style: AppTypography.regular(
                          15.13 * s,
                          color: Colors.black,
                        ),
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

class _AlfaBankBadge extends StatelessWidget {
  const _AlfaBankBadge();

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      height: 23 * s,
      padding: EdgeInsets.symmetric(horizontal: 10 * s),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppColors.brandRed,
        borderRadius: BorderRadius.circular(6 * s),
      ),
      child: SvgPicture.asset(
        'assets/images/alfa_bank_logo.svg',
        width: 51 * s,
        height: 10 * s,
        fit: BoxFit.contain,
        colorFilter: ColorFilter.mode(
          AppColors.surface,
          BlendMode.srcIn,
        ),
      ),
    );
  }
}
