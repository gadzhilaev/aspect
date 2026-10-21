import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';

class CompanyTab extends StatelessWidget {
  const CompanyTab({super.key});

  /// 2 per row: продукты|рынки, география|мои данные, финансы|контрагенты.
  static const _contextTiles = <String>[
    'assets/images/company/products.svg',
    'assets/images/company/markets.svg',
    'assets/images/company/geography.svg',
    'assets/images/company/my_data.svg',
    'assets/images/company/finance.svg',
    'assets/images/company/counterparties.svg',
  ];

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final gap = 10 * s;

    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        24 * s,
      ),
      children: [
        Text('Ваша компания', style: pageTitleStyle(context)),
        SizedBox(height: 18 * s),
        const _CompanyCard(),
        SizedBox(height: 15 * s),
        Padding(
          padding: EdgeInsets.only(left: (34 - AppColors.screenPadding) * s),
          child: Text(
            'Ваш контекст',
            style: AppTypography.medium(13 * s, color: AppColors.textMuted),
          ),
        ),
        SizedBox(height: 14 * s),
        LayoutBuilder(
          builder: (context, constraints) {
            final tileW = (constraints.maxWidth - gap) / 2;
            final tileH = tileW * (95 / 173);
            return Wrap(
              spacing: gap,
              runSpacing: gap,
              children: [
                for (final asset in _contextTiles)
                  _ContextTile(
                    asset: asset,
                    width: tileW,
                    height: tileH,
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _ContextTile extends StatelessWidget {
  const _ContextTile({
    required this.asset,
    required this.width,
    required this.height,
  });

  final String asset;
  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(17 * s),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.25),
            offset: Offset(0, 2 * s),
            blurRadius: 7.5 * s,
            spreadRadius: 0,
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(17 * s),
        child: SvgPicture.asset(
          asset,
          width: width,
          height: height,
          fit: BoxFit.cover,
        ),
      ),
    );
  }
}

class _CompanyCard extends StatelessWidget {
  const _CompanyCard();

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(
          color: Colors.black.withValues(alpha: 0.08),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.13),
            offset: Offset(0, 5 * s),
            blurRadius: 14.2 * s,
            spreadRadius: 0,
          ),
        ],
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(13 * s, 24 * s, 13 * s, 20 * s),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SvgPicture.asset(
                  'assets/images/welcome_logo.svg',
                  width: 48 * s,
                  height: 38 * s,
                  fit: BoxFit.contain,
                ),
                SizedBox(width: 15 * s),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'ООО «СеверПром»',
                        style: AppTypography.bold(
                          20 * s,
                          color: AppColors.textInk,
                        ),
                      ),
                      SizedBox(height: 2 * s),
                      Text(
                        'Промышленное производство',
                        style: AppTypography.regular(
                          14 * s,
                          color: AppColors.textCaption,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            SizedBox(height: 20 * s),
            Divider(height: 1 * s, thickness: 1 * s, color: AppColors.divider),
            SizedBox(height: 14 * s),
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SvgPicture.asset(
                  'assets/images/icon_company_size.svg',
                  width: 16 * s,
                  height: 18 * s,
                  fit: BoxFit.contain,
                ),
                SizedBox(width: 15 * s),
                Expanded(
                  child: Text(
                    'Средняя компания · 500–1 000 сотрудников',
                    style: AppTypography.regular(
                      11.72 * s,
                      color: AppColors.textTertiary,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
