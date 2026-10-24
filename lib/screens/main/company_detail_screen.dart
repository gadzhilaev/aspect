import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../models/onboarding_data.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

Future<void> openCompanyDetail(
  BuildContext context, {
  required OnboardingData profile,
}) {
  return Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => CompanyDetailScreen(profile: profile),
    ),
  );
}

class CompanyDetailScreen extends StatelessWidget {
  const CompanyDetailScreen({super.key, required this.profile});

  final OnboardingData profile;

  static String _surnameInitials(String fullName) {
    final parts = fullName.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '—';
    final surname = parts.first;
    if (parts.length == 1) return surname;
    final initials = [
      for (final part in parts.skip(1))
        if (part.isNotEmpty) '${part[0].toUpperCase()}.',
    ].join();
    return initials.isEmpty ? surname : '$surname $initials';
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;

    final name = profile.companyName.trim().isEmpty
        ? 'Компания не указана'
        : profile.companyName.trim();
    final industry = profile.companyIndustry.trim().isNotEmpty
        ? profile.companyIndustry.trim()
        : (profile.businessType.trim().isNotEmpty
            ? profile.businessType.trim()
            : 'Отрасль не указана');
    final city = profile.companyCity.trim().isNotEmpty
        ? profile.companyCity.trim()
        : '—';
    final size = () {
      final raw = profile.companySize.trim();
      if (raw.isEmpty) return 'Размер не указан';
      // «Средняя • 100–500 сотрудников» → «100–500 сотрудников»
      final parts = raw.split(RegExp(r'[•·]'));
      if (parts.length >= 2) return parts.sublist(1).join('•').trim();
      return raw;
    }();
    final inn = profile.companyInn.trim().isNotEmpty
        ? profile.companyInn.trim()
        : '—';
    final director = profile.fullName.trim().isNotEmpty
        ? _surnameInitials(profile.fullName)
        : '—';

    final rows = <(String, String)>[
      ('ИНН', inn),
      ('КПП', '456098765'),
      ('ОГРН', '4560987659087'),
      ('Дата регистрации', '14.09.2018'),
      ('Юридический адрес', city == '—' ? '—' : 'г. $city'),
      ('Руководитель', director),
      (
        'Основной ОКВЭД',
        industry == 'Отрасль не указана'
            ? '28.13\nПроизводство насосов и компрессоров'
            : industry,
      ),
    ];

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
      ),
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
                      '‹ Компания',
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
                  padding: EdgeInsets.fromLTRB(
                    hPad,
                    10 * s,
                    hPad,
                    24 * s + bottom,
                  ),
                  children: [
                    Text(
                      name,
                      style: AppTypography.bold(
                        24.83 * s,
                        color: AppColors.textInput,
                      ),
                    ),
                    SizedBox(height: 6 * s),
                    Text(
                      '$industry · $city',
                      style: AppTypography.regular(
                        13 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                    SizedBox(height: 14 * s),
                    Wrap(
                      spacing: 6 * s,
                      runSpacing: 6 * s,
                      children: [
                        for (final label in [
                          size,
                          'Действующая',
                          'Демонстрационный профиль',
                        ])
                          IntrinsicWidth(
                            child: Container(
                              height: 30 * s,
                              padding:
                                  EdgeInsets.symmetric(horizontal: 15 * s),
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(16 * s),
                                border: Border.all(
                                  color: AppColors.textMuted,
                                  width: 1,
                                ),
                              ),
                              child: Text(
                                label,
                                softWrap: false,
                                style: AppTypography.regular(
                                  13 * s,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                    SizedBox(height: 28 * s),
                    for (var i = 0; i < rows.length; i++) ...[
                      if (i > 0)
                        Divider(
                          height: 1 * s,
                          thickness: 1 * s,
                          color: AppColors.divider,
                        ),
                      Padding(
                        padding: EdgeInsets.symmetric(vertical: 14 * s),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              flex: 5,
                              child: Text(
                                rows[i].$1,
                                style: AppTypography.regular(
                                  13 * s,
                                  color: AppColors.textMuted,
                                ),
                              ),
                            ),
                            SizedBox(width: 12 * s),
                            Expanded(
                              flex: 6,
                              child: Text(
                                rows[i].$2,
                                textAlign: TextAlign.right,
                                style: AppTypography.regular(
                                  13 * s,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                            ),
                          ],
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
