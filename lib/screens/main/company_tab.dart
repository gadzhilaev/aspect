import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../theme/app_colors.dart';
import '../../widgets/main_widgets.dart';

class CompanyTab extends StatelessWidget {
  const CompanyTab({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      children: [
        const AspectBrandHeader(dateText: '12 октября 2026 г'),
        const SizedBox(height: 18),
        const Text(
          'Ваша компания',
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
            letterSpacing: -0.4,
            height: 1.15,
          ),
        ),
        const SizedBox(height: 18),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: Colors.black.withValues(alpha: 0.08)),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  SvgPicture.asset(
                    'assets/images/welcome_logo.svg',
                    height: 28,
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'ООО «СеверПром»',
                          style: TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: AppColors.textInput,
                          ),
                        ),
                        SizedBox(height: 2),
                        Text(
                          'Промышленное производство',
                          style: TextStyle(
                            fontSize: 13,
                            color: Color(0xFF68707C),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              const Divider(height: 1, color: AppColors.divider),
              const SizedBox(height: 12),
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Средняя компания · 500–1 000 сотрудников',
                  style: TextStyle(
                    fontSize: 13,
                    color: Color(0xFF8A919B),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        const Text(
          'Ваш контекст',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: AppColors.textSecondary,
          ),
        ),
        const SizedBox(height: 12),
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
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
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF7A18DC),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Center(
        child: Opacity(
          opacity: 0.35,
          child: SvgPicture.asset(
            'assets/images/welcome_logo.svg',
            height: 56,
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
    final fg = dark ? Colors.white : AppColors.textInput;
    final sub = dark ? Colors.white.withValues(alpha: 0.85) : const Color(0xFF65717A);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: dark ? const Color(0xFF7A18DC) : AppColors.surface,
        borderRadius: BorderRadius.circular(18),
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
              size: 16,
              color: dark ? Colors.white : AppColors.textSecondary,
            ),
          ),
          const Spacer(),
          Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: sub,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: fg,
              height: 1.25,
            ),
          ),
        ],
      ),
    );
  }
}
