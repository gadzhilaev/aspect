import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/app_colors.dart';

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
              height: 22,
            ),
            const SizedBox(width: 8),
            const Text(
              'АСПЕКТ',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.8,
                color: AppColors.brandRed,
              ),
            ),
          ],
        ),
        if (dateText != null) ...[
          const SizedBox(height: 6),
          Text(
            dateText!,
            style: const TextStyle(
              fontSize: 13,
              color: Color(0xFF65717A),
            ),
          ),
        ],
      ],
    );
  }
}

enum ImpactLevel { high, medium, opportunity }

class ImpactColors {
  static Color accent(ImpactLevel level) {
    switch (level) {
      case ImpactLevel.high:
        return AppColors.brandRed;
      case ImpactLevel.medium:
        return const Color(0xFF7A18DC);
      case ImpactLevel.opportunity:
        return const Color(0xFF0B8A6A);
    }
  }
}

class EventSignalCard extends StatelessWidget {
  const EventSignalCard({
    super.key,
    required this.level,
    required this.meta,
    required this.title,
    required this.contextText,
    this.warning,
    required this.actionLabel,
  });

  final ImpactLevel level;
  final String meta;
  final String title;
  final String contextText;
  final String? warning;
  final String actionLabel;

  @override
  Widget build(BuildContext context) {
    final accent = ImpactColors.accent(level);
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
      ),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              width: 3,
              margin: const EdgeInsets.symmetric(vertical: 14),
              decoration: BoxDecoration(
                color: accent,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 14, 16, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      meta,
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: accent,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      title,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textInput,
                        height: 1.25,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      contextText,
                      style: const TextStyle(
                        fontSize: 13,
                        height: 1.35,
                        color: Color(0xFF65717A),
                      ),
                    ),
                    if (warning != null) ...[
                      const SizedBox(height: 10),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFEF3F2),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              Icons.error_outline,
                              size: 18,
                              color: accent,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                warning!,
                                style: TextStyle(
                                  fontSize: 13,
                                  height: 1.35,
                                  color: accent,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                    const SizedBox(height: 10),
                    Text(
                      actionLabel,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: accent,
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
    return Container(
      width: 148,
      height: 88,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.brandRed,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            '$code $country',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              height: 1.15,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              rate,
              style: const TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w700,
                height: 1.15,
                color: AppColors.textInput,
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
  });

  final Color dotColor;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.black.withValues(alpha: 0.06)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 5),
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: dotColor,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textInput,
                    height: 1.25,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: const TextStyle(
                    fontSize: 13,
                    color: Color(0xFF65717A),
                    height: 1.3,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
