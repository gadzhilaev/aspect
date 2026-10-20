import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';

export '../theme/design_scale.dart';

class AspectBrandHeader extends StatelessWidget {
  const AspectBrandHeader({
    super.key,
    this.dateText,
  });

  final String? dateText;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            SvgPicture.asset(
              'assets/images/welcome_logo.svg',
              height: ds(context, 24),
            ),
            SizedBox(width: ds(context, 8)),
            Text(
              'АСПЕКТ',
              style: AppTypography.medium(
                ds(context, 18.26),
                color: AppColors.brandRed,
              ),
            ),
          ],
        ),
        if (dateText != null) ...[
          SizedBox(height: ds(context, 6)),
          Text(
            dateText!,
            style: AppTypography.regular(
              ds(context, 13),
              color: AppColors.textMuted,
            ),
          ),
        ],
      ],
    );
  }
}

String formatOverviewDate([DateTime? date]) {
  const months = [
    'января',
    'февраля',
    'марта',
    'апреля',
    'мая',
    'июня',
    'июля',
    'августа',
    'сентября',
    'октября',
    'ноября',
    'декабря',
  ];
  final d = date ?? DateTime.now();
  return '${d.day} ${months[d.month - 1]} ${d.year} г';
}

enum ImpactLevel { high, medium, opportunity }

class ImpactColors {
  static Color accent(ImpactLevel level) {
    switch (level) {
      case ImpactLevel.high:
        return AppColors.brandRed;
      case ImpactLevel.medium:
        return AppColors.impactPurple;
      case ImpactLevel.opportunity:
        return AppColors.impactGreen;
    }
  }
}

class EventSignalCard extends StatelessWidget {
  const EventSignalCard({
    super.key,
    required this.level,
    required this.meta,
    required this.title,
    required this.contextLead,
    required this.contextBody,
    this.warning,
    required this.actionLabel,
  });

  final ImpactLevel level;
  final String meta;
  final String title;
  final String contextLead;
  final String contextBody;
  final String? warning;
  final String actionLabel;

  @override
  Widget build(BuildContext context) {
    final accent = ImpactColors.accent(level);
    final s = designScale(context);

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16 * s),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 16 * s,
            spreadRadius: 0,
            offset: Offset(0, 4 * s),
          ),
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 6 * s,
            spreadRadius: 0,
            offset: Offset(0, 1 * s),
          ),
        ],
      ),
      child: Material(
        color: AppColors.surface,
        elevation: 0,
        shadowColor: Colors.transparent,
        borderRadius: BorderRadius.circular(16 * s),
        child: Ink(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16 * s),
            border: Border.all(
              color: const Color(0x3D000000),
              width: 0.1,
            ),
          ),
          child: IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  width: 3 * s,
                  margin: EdgeInsets.fromLTRB(14 * s, 14 * s, 0, 14 * s),
                  decoration: BoxDecoration(
                    color: accent,
                    borderRadius: BorderRadius.circular(2 * s),
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(
                      12 * s,
                      14 * s,
                      16 * s,
                      14 * s,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          meta,
                          style: AppTypography.medium(
                            11 * s,
                            color: accent,
                          ),
                        ),
                        SizedBox(height: 2 * s),
                        Text(
                          title,
                          style: AppTypography.bold(
                            14.3 * s,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        SizedBox(height: 10 * s),
                        Text.rich(
                          TextSpan(
                            children: [
                              TextSpan(
                                text: contextLead,
                                style: AppTypography.bold(
                                  11 * s,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                              TextSpan(
                                text: ' $contextBody',
                                style: AppTypography.medium(
                                  11 * s,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (warning != null) ...[
                          SizedBox(height: 10 * s),
                          Container(
                            width: double.infinity,
                            padding: EdgeInsets.symmetric(
                              horizontal: 10 * s,
                              vertical: 10 * s,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.warningBg,
                              borderRadius: BorderRadius.circular(10 * s),
                              border: Border.all(
                                color: AppColors.warningBorder,
                              ),
                            ),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                SvgPicture.asset(
                                  'assets/images/icon_risk.svg',
                                  width: 23 * s,
                                  height: 23 * s,
                                ),
                                SizedBox(width: 8 * s),
                                Expanded(
                                  child: Text(
                                    warning!,
                                    style: AppTypography.medium(
                                      11 * s,
                                      color: accent,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                        SizedBox(height: 10 * s),
                        Text(
                          actionLabel,
                          style: AppTypography.medium(
                            13 * s,
                            color: accent,
                          ).copyWith(
                            decoration: TextDecoration.underline,
                            decorationColor: accent,
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
      ),
    );
  }
}

class CurrencyChipCard extends StatelessWidget {
  const CurrencyChipCard({
    super.key,
    required this.code,
    required this.country,
    required this.rate,
  });

  final String code;
  final String country;
  final String rate;

  @override
  Widget build(BuildContext context) {
    final s = designScale(context);
    return Container(
      width: 115 * s,
      height: 70 * s,
      padding: EdgeInsets.fromLTRB(10 * s, 10 * s, 8 * s, 10 * s),
      decoration: BoxDecoration(
        color: AppColors.brandRed,
        borderRadius: BorderRadius.circular(16 * s),
      ),
      child: Stack(
        children: [
          Align(
            alignment: Alignment.topLeft,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  code,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.medium(14.67 * s, color: Colors.white),
                ),
                Text(
                  country,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.regular(9.03 * s, color: Colors.white),
                ),
              ],
            ),
          ),
          Align(
            alignment: Alignment.bottomRight,
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: 8 * s,
                vertical: 5 * s,
              ),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(20 * s),
              ),
              child: Text(
                rate,
                style: AppTypography.medium(
                  8.78 * s,
                  color: AppColors.brandRed,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class MonitorTile extends StatelessWidget {
  const MonitorTile({
    super.key,
    required this.dotColor,
    required this.title,
    required this.subtitle,
    this.onTap,
  });

  final Color dotColor;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final s = designScale(context);
    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(14 * s),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14 * s),
        child: Ink(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(14 * s),
            border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: 14 * s,
              vertical: 12 * s,
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  width: 8 * s,
                  height: 8 * s,
                  decoration: BoxDecoration(
                    color: dotColor,
                    shape: BoxShape.circle,
                  ),
                ),
                SizedBox(width: 10 * s),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: AppTypography.bold(
                          12.7 * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 6 * s),
                      Text(
                        subtitle,
                        style: AppTypography.medium(
                          9.77 * s,
                          color: AppColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(width: 8 * s),
                Icon(
                  Icons.chevron_right_rounded,
                  size: 22 * s,
                  color: AppColors.textMuted,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
