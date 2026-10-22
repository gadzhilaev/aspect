import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../models/onboarding_data.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import 'context_edit_screen.dart';

class CompanyTab extends StatefulWidget {
  const CompanyTab({super.key});

  @override
  State<CompanyTab> createState() => _CompanyTabState();
}

class _CompanyTabState extends State<CompanyTab> {
  OnboardingData? _profile;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final profile = await SessionStore.loadProfile();
    if (!mounted) return;
    setState(() => _profile = profile);
  }

  static String _join(
    Iterable<String> values, {
    String empty = 'Пока пусто',
  }) {
    final parts = [
      for (final v in values)
        if (v.trim().isNotEmpty) v.trim(),
    ];
    if (parts.isEmpty) return empty;
    return parts.join(' · ');
  }

  static String _shortRole(String role) {
    const map = {
      'Генеральный директор': 'Ген директор',
      'Операционный директор': 'Оп директор',
      'Финансовый директор': 'Фин директор',
      'Коммерческий директор': 'Ком директор',
      'Руководитель подразделения': 'Рук подразделения',
      'Сотрудник': 'Сотрудник',
    };
    final trimmed = role.trim();
    if (trimmed.isEmpty) return '';
    return map[trimmed] ?? trimmed;
  }

  /// «Фамилия Имя Отчество» → «Фамилия И. О.»
  static String _surnameWithInitials(String fullName) {
    final parts = fullName.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '';
    final surname = parts.first;
    if (parts.length == 1) return surname;
    final initials = [
      for (final part in parts.skip(1))
        if (part.isNotEmpty) '${part[0].toUpperCase()}.',
    ].join(' ');
    return initials.isEmpty ? surname : '$surname $initials';
  }

  /// Три строки: роль / фамилия И. О. / почта.
  static String _myDataSubtitle(OnboardingData d) {
    final lines = [
      _shortRole(d.role),
      _surnameWithInitials(d.fullName),
      d.email.trim(),
    ].where((v) => v.isNotEmpty);
    if (lines.isEmpty) return 'Пока пусто';
    return lines.join('\n');
  }

  List<_TileSpec> _tilesFor(OnboardingData? data) {
    final d = data ?? OnboardingData();
    final products = _join(
      d.products.isNotEmpty
          ? d.products
          : [
              if (d.businessTypeSubtitle.trim().isNotEmpty)
                d.businessTypeSubtitle,
              if (d.businessType.trim().isNotEmpty) d.businessType,
            ],
    );
    final markets = _join(
      d.countries.isNotEmpty
          ? d.countries
          : d.salesRegions.isNotEmpty
              ? d.salesRegions
              : [d.mainMarket],
    );
    final geography = _join(
      d.cities.isNotEmpty ? d.cities : [d.companyCity],
    );
    return [
      _TileSpec(
        title: 'Продукты',
        subtitle: products,
        background: AppColors.brandRed,
        foreground: Colors.white,
        decor: Colors.white.withValues(alpha: 0.17),
        section: ContextSection.products,
      ),
      _TileSpec(
        title: 'Рынки',
        subtitle: markets,
        background: AppColors.surface,
        foreground: AppColors.textPrimary,
        decor: Colors.black.withValues(alpha: 0.06),
        section: ContextSection.markets,
      ),
      _TileSpec(
        title: 'География',
        subtitle: geography,
        background: AppColors.impactPurple,
        foreground: Colors.white,
        decor: Colors.white.withValues(alpha: 0.17),
        section: ContextSection.geography,
      ),
      _TileSpec(
        title: 'Мои данные',
        subtitle: _myDataSubtitle(d),
        background: Colors.black,
        foreground: Colors.white,
        decor: const Color(0xFF1F1F1F),
        section: ContextSection.myData,
      ),
      _TileSpec(
        title: 'Финансы',
        subtitle: d.finances.isEmpty ? '' : _join(d.finances),
        background: AppColors.surface,
        foreground: AppColors.textPrimary,
        decor: Colors.black.withValues(alpha: 0.06),
        centerTitle: d.finances.isEmpty,
      ),
      _TileSpec(
        title: 'Контрагенты и связи',
        subtitle: d.counterparties.isEmpty ? '' : _join(d.counterparties),
        background: AppColors.brandRed,
        foreground: Colors.white,
        decor: Colors.white.withValues(alpha: 0.17),
        centerTitle: d.counterparties.isEmpty,
      ),
    ];
  }

  Future<void> _openSection(ContextSection section) async {
    final profile = _profile ?? OnboardingData();
    final saved = await openContextEdit(
      context,
      section: section,
      profile: profile,
    );
    if (!mounted || !saved) return;
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final gap = 10 * s;
    final tiles = _tilesFor(_profile);

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
        _CompanyCard(profile: _profile),
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
            final tileH = tileW * (98 / 173);
            return Wrap(
              spacing: gap,
              runSpacing: gap,
              children: [
                for (final tile in tiles)
                  _ContextTile(
                    spec: tile,
                    width: tileW,
                    height: tileH,
                    onTap: tile.section == null
                        ? null
                        : () => _openSection(tile.section!),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _TileSpec {
  const _TileSpec({
    required this.title,
    required this.subtitle,
    required this.background,
    required this.foreground,
    required this.decor,
    this.section,
    this.centerTitle = false,
  });

  final String title;
  final String subtitle;
  final Color background;
  final Color foreground;
  final Color decor;
  final ContextSection? section;
  final bool centerTitle;
}

class _ContextTile extends StatelessWidget {
  const _ContextTile({
    required this.spec,
    required this.width,
    required this.height,
    this.onTap,
  });

  final _TileSpec spec;
  final double width;
  final double height;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final onDark = spec.foreground == Colors.white;

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
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
        child: Stack(
          fit: StackFit.expand,
          children: [
            ColoredBox(color: spec.background),
            Positioned.fill(
              child: SvgPicture.asset(
                'assets/images/company/tile_watermark.svg',
                fit: BoxFit.fill,
                colorFilter: ColorFilter.mode(spec.decor, BlendMode.srcIn),
              ),
            ),
            Positioned(
              top: 10 * s,
              right: 10 * s,
              child: Icon(
                Icons.north_east_rounded,
                size: 25 * s,
                color: spec.foreground,
              ),
            ),
            if (spec.centerTitle)
              Padding(
                padding: EdgeInsets.fromLTRB(14 * s, 0, 28 * s, 0),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    spec.title,
                    textAlign: TextAlign.left,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.bold(
                      15 * s,
                      color: spec.foreground,
                    ).copyWith(height: 1.15),
                  ),
                ),
              )
            else
              Padding(
                padding: EdgeInsets.fromLTRB(14 * s, 14 * s, 28 * s, 10 * s),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      spec.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: AppTypography.bold(
                        15 * s,
                        color: spec.foreground,
                      ).copyWith(height: 1.15),
                    ),
                    const Spacer(),
                    Text(
                      spec.subtitle,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: AppTypography.regular(
                        10 * s,
                        color: spec.foreground.withValues(
                          alpha: onDark ? 0.92 : 0.75,
                        ),
                      ).copyWith(height: 1.15),
                    ),
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

class _CompanyCard extends StatelessWidget {
  const _CompanyCard({this.profile});

  final OnboardingData? profile;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final name = profile?.companyName.trim().isNotEmpty == true
        ? profile!.companyName.trim()
        : 'Компания не указана';
    final industry = () {
      final industry = profile?.companyIndustry.trim() ?? '';
      if (industry.isNotEmpty) return industry;
      final type = profile?.businessType.trim() ?? '';
      if (type.isNotEmpty) return type;
      return 'Отрасль не указана';
    }();
    final size = profile?.companySize.trim().isNotEmpty == true
        ? profile!.companySize.trim()
        : 'Размер не указан';

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
                        name,
                        style: AppTypography.bold(
                          20 * s,
                          color: AppColors.textInk,
                        ),
                      ),
                      SizedBox(height: 2 * s),
                      Text(
                        industry,
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
                    size,
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
