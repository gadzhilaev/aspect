import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

class CompanyTab extends StatelessWidget {
  const CompanyTab({super.key});

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        24 * s,
      ),
      children: [
        Text(
          'Ваша компания',
          style: AppTypography.bold(28 * s, color: AppColors.textPrimary)
              .copyWith(letterSpacing: -0.4, height: 1.15),
        ),
        SizedBox(height: 18 * s),
        Container(
          padding: EdgeInsets.all(16 * s),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(18 * s),
            border: Border.all(color: Colors.black.withValues(alpha: 0.08)),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  SvgPicture.asset(
                    'assets/images/welcome_logo.svg',
                    height: 28 * s,
                  ),
                  SizedBox(width: 12 * s),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'ООО «СеверПром»',
                          style: AppTypography.bold(
                            17 * s,
                            color: AppColors.textInput,
                          ),
                        ),
                        SizedBox(height: 2 * s),
                        Text(
                          'Промышленное производство',
                          style: AppTypography.regular(
                            13 * s,
                            color: AppColors.textCaption,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              SizedBox(height: 14 * s),
              Divider(height: 1 * s, color: AppColors.divider),
              SizedBox(height: 12 * s),
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Средняя компания · 500–1 000 сотрудников',
                  style: AppTypography.regular(
                    13 * s,
                    color: AppColors.textTertiary,
                  ),
                ),
              ),
            ],
          ),
        ),
        SizedBox(height: 24 * s),
        Text(
          'Ваш контекст',
          style: AppTypography.bold(16 * s, color: AppColors.textSecondary),
        ),
        SizedBox(height: 12 * s),
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 10 * s,
          crossAxisSpacing: 10 * s,
          childAspectRatio: 1.15,
          children: const [
            _BrandTile(),
            _ContextTile(
              label: 'Рынки',
              value: 'Россия · Казахстан · Беларусь',
              dark: false,
            ),
            _ContextTile(
              label: 'География',
              value: 'Тула · Москва',
              dark: true,
            ),
            _ContextTile(
              label: 'Продукты',
              value: 'Насосы · системы управления',
              dark: false,
            ),
          ],
        ),
      ],
    );
  }
}

class _BrandTile extends StatelessWidget {
  const _BrandTile();

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      decoration: BoxDecoration(
        color: AppColors.impactPurple,
        borderRadius: BorderRadius.circular(18 * s),
      ),
      child: Center(
        child: Opacity(
          opacity: 0.35,
          child: SvgPicture.asset(
            'assets/images/welcome_logo.svg',
            height: 56 * s,
            colorFilter: const ColorFilter.mode(
              Colors.white,
              BlendMode.srcIn,
            ),
          ),
        ),
      ),
    );
  }
}

class _ContextTile extends StatelessWidget {
  const _ContextTile({
    required this.label,
    required this.value,
    required this.dark,
  });

  final String label;
  final String value;
  final bool dark;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final fg = dark ? Colors.white : AppColors.textInput;
    final sub =
        dark ? Colors.white.withValues(alpha: 0.85) : AppColors.textMuted;
    return Container(
      padding: EdgeInsets.all(14 * s),
      decoration: BoxDecoration(
        color: dark ? AppColors.impactPurple : AppColors.surface,
        borderRadius: BorderRadius.circular(18 * s),
        border: dark
            ? null
            : Border.all(color: Colors.black.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Align(
            alignment: Alignment.topRight,
            child: Icon(
              Icons.north_east,
              size: 16 * s,
              color: dark ? Colors.white : AppColors.textSecondary,
            ),
          ),
          const Spacer(),
          Text(
            label,
            style: AppTypography.medium(13 * s, color: sub),
          ),
          SizedBox(height: 4 * s),
          Text(
            value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: AppTypography.bold(14 * s, color: fg).copyWith(height: 1.25),
          ),
        ],
      ),
    );
  }
}
