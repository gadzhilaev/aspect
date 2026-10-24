import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../app/app_controller.dart';
import '../l10n/app_localizations.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';

export '../theme/design_scale.dart';

/// Page title style matching overview greeting «Доброе утро, …».
TextStyle pageTitleStyle(BuildContext context) {
  final s = designScale(context);
  return AppTypography.medium(24.83 * s, color: AppColors.textInput);
}

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

String formatOverviewDate([DateTime? date, AppLocalizations? l10n]) {
  final d = date ?? DateTime.now();
  if (l10n != null) return l10n.formatDate(d);
  // Fallback without context (e.g. early build).
  return AppLocalizations(AppController.instance.locale).formatDate(d);
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
    this.onOpen,
  });

  final ImpactLevel level;
  final String meta;
  final String title;
  final String contextLead;
  final String contextBody;
  final String? warning;
  final String actionLabel;
  final VoidCallback? onOpen;

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
        color: AppColors.surfaceRaised,
        elevation: 0,
        shadowColor: Colors.transparent,
        borderRadius: BorderRadius.circular(16 * s),
        child: InkWell(
          onTap: onOpen,
          borderRadius: BorderRadius.circular(16 * s),
          child: Ink(
            decoration: BoxDecoration(
              color: AppColors.surfaceRaised,
              borderRadius: BorderRadius.circular(16 * s),
              border: Border.all(
                color: AppColors.border,
                width: AppColors.isDark ? 1 : 0.1,
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
                          SizedBox(height: 6 * s),
                          Text(
                            title,
                            style: AppTypography.bold(
                              14.3 * s,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          SizedBox(height: 14 * s),
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
                            SizedBox(height: 14 * s),
                            Container(
                              width: double.infinity,
                              padding: EdgeInsets.fromLTRB(
                                10 * s,
                                10 * s,
                                12 * s,
                                10 * s,
                              ),
                              decoration: BoxDecoration(
                                color: AppColors.warningBg,
                                borderRadius: BorderRadius.circular(6.5 * s),
                                border: Border.all(
                                  color: AppColors.warningBorder,
                                  width: 1,
                                ),
                              ),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.center,
                                children: [
                                  SizedBox(
                                    width: 23 * s,
                                    height: 23 * s,
                                    child: Center(
                                      child: SvgPicture.asset(
                                        'assets/images/icon_risk.svg',
                                        width: 23 * s,
                                        height: 23 * s,
                                        fit: BoxFit.contain,
                                      ),
                                    ),
                                  ),
                                  SizedBox(width: 10 * s),
                                  Expanded(
                                    child: Text(
                                      warning!,
                                      style: AppTypography.medium(
                                        11 * s,
                                        color: AppColors.warningText,
                                      ).copyWith(height: 1.25),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                          SizedBox(height: 14 * s),
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
        clipBehavior: Clip.hardEdge,
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
                vertical: 4 * s,
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
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceRaised,
        borderRadius: BorderRadius.circular(14 * s),
        border: Border.all(
          color: AppColors.border,
          width: AppColors.isDark ? 1 : 0.11,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: AppColors.isDark ? 0.35 : 0.15),
            offset: Offset(0, 2 * s),
            blurRadius: 7.71 * s,
            spreadRadius: 0,
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(14 * s),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(14 * s),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: 14 * s,
              vertical: 15 * s,
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
                CustomPaint(
                  size: Size(5.5 * s, 11 * s),
                  painter: _MonitorChevronPainter(AppColors.textMuted),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MonitorChevronPainter extends CustomPainter {
  const _MonitorChevronPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final path = Path()
      ..moveTo(size.width * 0.15, size.height * 0.12)
      ..lineTo(size.width * 0.85, size.height * 0.5)
      ..lineTo(size.width * 0.15, size.height * 0.88);
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _MonitorChevronPainter oldDelegate) =>
      oldDelegate.color != color;
}
