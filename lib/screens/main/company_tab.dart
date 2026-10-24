import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../l10n/app_localizations.dart';
import '../../models/onboarding_data.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import '../login_screen.dart';
import 'company_detail_screen.dart';
import 'context_edit_screen.dart';
import 'counterparties_screen.dart';
import 'finance_screen.dart';
import 'settings_screen.dart';

class CompanyTab extends StatefulWidget {
  const CompanyTab({super.key});

  @override
  State<CompanyTab> createState() => _CompanyTabState();
}

class _CompanyTabState extends State<CompanyTab> {
  OnboardingData? _profile;
  String? _telegramUsername;

  static const _telegramBlue = Color(0xFF2AABEE);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final profile = await SessionStore.loadProfile();
    final telegram = await SessionStore.telegramUsername();
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _telegramUsername = telegram;
    });
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
  static String _myDataSubtitle(OnboardingData d, AppLocalizations l10n) {
    final lines = [
      _shortRole(d.role),
      _surnameWithInitials(d.fullName),
      d.email.trim(),
    ].where((v) => v.isNotEmpty);
    if (lines.isEmpty) return l10n.emptyPlaceholder;
    return lines.join('\n');
  }

  List<_TileSpec> _tilesFor(OnboardingData? data, AppLocalizations l10n) {
    final d = data ?? OnboardingData();
    final empty = l10n.emptyPlaceholder;
    final products = _join(
      d.products.isNotEmpty
          ? d.products
          : [
              if (d.businessTypeSubtitle.trim().isNotEmpty)
                d.businessTypeSubtitle,
              if (d.businessType.trim().isNotEmpty) d.businessType,
            ],
      empty: empty,
    );
    final markets = _join(
      d.countries.isNotEmpty
          ? d.countries
          : d.salesRegions.isNotEmpty
              ? d.salesRegions
              : [d.mainMarket],
      empty: empty,
    );
    final geography = _join(
      d.cities.isNotEmpty ? d.cities : [d.companyCity],
      empty: empty,
    );
    return [
      _TileSpec(
        title: l10n.sectionProducts,
        subtitle: products,
        background: AppColors.tileRed,
        foreground: Colors.white,
        decor: Colors.white.withValues(alpha: 0.17),
        section: ContextSection.products,
      ),
      _TileSpec(
        title: l10n.sectionMarkets,
        subtitle: markets,
        background: AppColors.surfaceRaised,
        foreground: AppColors.textPrimary,
        decor: AppColors.isDark
            ? Colors.white.withValues(alpha: 0.08)
            : Colors.black.withValues(alpha: 0.06),
        bordered: AppColors.isDark,
        section: ContextSection.markets,
      ),
      _TileSpec(
        title: l10n.sectionGeography,
        subtitle: geography,
        background: AppColors.tilePurple,
        foreground: Colors.white,
        decor: Colors.white.withValues(alpha: 0.17),
        section: ContextSection.geography,
      ),
      _TileSpec(
        title: l10n.myData,
        subtitle: _myDataSubtitle(d, l10n),
        background: AppColors.tileDark,
        foreground: Colors.white,
        decor: AppColors.isDark
            ? Colors.white.withValues(alpha: 0.08)
            : const Color(0xFF1F1F1F),
        bordered: AppColors.isDark,
        section: ContextSection.myData,
      ),
      _TileSpec(
        title: l10n.finance,
        subtitle: d.finances.isEmpty ? '' : _join(d.finances, empty: empty),
        background: AppColors.surfaceRaised,
        foreground: AppColors.textPrimary,
        decor: AppColors.isDark
            ? Colors.white.withValues(alpha: 0.08)
            : Colors.black.withValues(alpha: 0.06),
        bordered: AppColors.isDark,
        centerTitle: d.finances.isEmpty,
        onTap: _TileAction.finance,
      ),
      _TileSpec(
        title: l10n.counterpartiesAndLinks,
        subtitle: d.counterparties.isEmpty
            ? ''
            : _join(d.counterparties, empty: empty),
        background: AppColors.tileRed,
        foreground: Colors.white,
        decor: Colors.white.withValues(alpha: 0.17),
        centerTitle: d.counterparties.isEmpty,
        onTap: _TileAction.counterparties,
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

  Future<void> _onTileTap(_TileSpec tile) async {
    switch (tile.onTap) {
      case _TileAction.edit:
        if (tile.section != null) await _openSection(tile.section!);
      case _TileAction.finance:
        await openFinanceScreen(context);
      case _TileAction.counterparties:
        await openCounterpartiesScreen(context);
      case null:
        break;
    }
  }

  String _suggestedTelegramUsername() {
    final name = _profile?.fullName.trim() ?? '';
    final parts = name.split(RegExp(r'\s+'));
    final base = parts.length >= 2
        ? '${parts[1]}${parts.first}'.toLowerCase()
        : (parts.isNotEmpty ? parts.first.toLowerCase() : 'aspect');
    final clean = base.replaceAll(RegExp(r'[^a-z0-9_]'), '');
    return clean.isEmpty ? 'aspect_user' : clean;
  }

  Future<void> _onTelegramTap() async {
    final s = context.scale;
    final l10n = context.l10n;
    if (_telegramUsername != null) {
      final disconnect = await showModalBottomSheet<bool>(
        context: context,
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16 * s)),
        ),
        builder: (ctx) {
          return SafeArea(
            child: Padding(
              padding: EdgeInsets.fromLTRB(20 * s, 16 * s, 20 * s, 16 * s),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Telegram',
                    style: AppTypography.bold(
                      18 * s,
                      color: AppColors.textInk,
                    ),
                  ),
                  SizedBox(height: 6 * s),
                  Text(
                    '@$_telegramUsername',
                    style: AppTypography.regular(
                      15 * s,
                      color: _telegramBlue,
                    ),
                  ),
                  SizedBox(height: 16 * s),
                  OutlinedButton(
                    onPressed: () => Navigator.of(ctx).pop(true),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.brandRed,
                      side: BorderSide(
                        color: AppColors.brandRed,
                        width: 1.5 * s,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14 * s),
                      ),
                      minimumSize: Size(double.infinity, 48 * s),
                    ),
                    child: Text(
                      l10n.telegramDisconnect,
                      style: AppTypography.bold(
                        14 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      );
      if (disconnect == true) {
        await SessionStore.saveTelegramUsername(null);
        if (!mounted) return;
        setState(() => _telegramUsername = null);
      }
      return;
    }

    final username = _suggestedTelegramUsername();
    await SessionStore.saveTelegramUsername(username);
    if (!mounted) return;
    setState(() => _telegramUsername = username);
  }

  Future<void> _logout() async {
    final s = context.scale;
    final l10n = context.l10n;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16 * s),
          ),
          title: Text(
            l10n.logoutConfirmTitle,
            style: AppTypography.bold(18 * s, color: AppColors.textInk),
          ),
          content: Text(
            l10n.logoutConfirmBody,
            style: AppTypography.regular(14 * s, color: AppColors.textMuted),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(
                l10n.cancel,
                style: AppTypography.regular(
                  14 * s,
                  color: AppColors.textMuted,
                ),
              ),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: Text(
                l10n.logout,
                style: AppTypography.bold(
                  14 * s,
                  color: AppColors.brandRed,
                ),
              ),
            ),
          ],
        );
      },
    );
    if (confirmed != true || !mounted) return;

    await SessionStore.clear();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      PageRouteBuilder<void>(
        transitionDuration: const Duration(milliseconds: 350),
        pageBuilder: (_, animation, _) => FadeTransition(
          opacity: animation,
          child: const LoginScreen(),
        ),
      ),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final gap = 10 * s;
    final tiles = _tilesFor(_profile, l10n);
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        AppColors.screenPadding * s,
        28 * s + bottomInset,
      ),
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Text(l10n.yourCompany, style: pageTitleStyle(context)),
            ),
            GestureDetector(
              onTap: () => openSettingsScreen(context),
              behavior: HitTestBehavior.opaque,
              child: Padding(
                padding: EdgeInsets.only(left: 8 * s),
                child: SvgPicture.asset(
                  'assets/images/icon_settings.svg',
                  width: 23 * s,
                  height: 23 * s,
                  colorFilter: ColorFilter.mode(
                    AppColors.textMuted,
                    BlendMode.srcIn,
                  ),
                ),
              ),
            ),
          ],
        ),
        SizedBox(height: 18 * s),
        GestureDetector(
          onTap: () => openCompanyDetail(
            context,
            profile: _profile ?? OnboardingData(),
          ),
          behavior: HitTestBehavior.opaque,
          child: _CompanyCard(profile: _profile),
        ),
        SizedBox(height: 15 * s),
        Padding(
          padding: EdgeInsets.only(left: (34 - AppColors.screenPadding) * s),
          child: Text(
            l10n.yourContext,
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
                    onTap: tile.onTap == null && tile.section == null
                        ? null
                        : () => _onTileTap(tile),
                  ),
              ],
            );
          },
        ),
        SizedBox(height: gap),
        _TelegramConnectCard(
          username: _telegramUsername,
          onTap: _onTelegramTap,
        ),
        SizedBox(height: gap),
        SizedBox(
          height: 52 * s,
          width: double.infinity,
          child: OutlinedButton(
            onPressed: _logout,
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.brandRed,
              side: BorderSide(color: AppColors.brandRed, width: 1.5 * s),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16 * s),
              ),
              splashFactory: NoSplash.splashFactory,
              overlayColor: Colors.transparent,
              surfaceTintColor: Colors.transparent,
            ),
            child: Text(
              l10n.logoutFromAccount,
              style: AppTypography.bold(
                14.06 * s,
                color: AppColors.brandRed,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _TelegramConnectCard extends StatelessWidget {
  const _TelegramConnectCard({
    required this.onTap,
    this.username,
  });

  final VoidCallback onTap;
  final String? username;

  static const _telegramBlue = Color(0xFF2AABEE);

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final connected = username != null && username!.isNotEmpty;

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.fromLTRB(14 * s, 14 * s, 14 * s, 14 * s),
        decoration: BoxDecoration(
          color: AppColors.surfaceRaised,
          borderRadius: BorderRadius.circular(16 * s),
          border: Border.all(
            color: connected
                ? _telegramBlue.withValues(alpha: 0.35)
                : AppColors.border,
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: AppColors.isDark ? 0.35 : 0.1),
              offset: Offset(0, 4 * s),
              blurRadius: 12 * s,
            ),
          ],
        ),
        child: Row(
          children: [
            SvgPicture.asset(
              'assets/images/icon_telegram.svg',
              width: 56 * s,
              height: 56 * s,
            ),
            SizedBox(width: 10 * s),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    connected ? l10n.telegramConnected : l10n.telegramConnect,
                    style: AppTypography.bold(
                      15.13 * s,
                      color: AppColors.textInk,
                    ),
                  ),
                  SizedBox(height: 2 * s),
                  Text(
                    connected ? '@$username' : l10n.telegramEventsSub,
                    style: AppTypography.regular(
                      12 * s,
                      color: connected ? _telegramBlue : AppColors.textMuted,
                    ),
                  ),
                ],
              ),
            ),
            if (connected)
              Container(
                width: 22 * s,
                height: 22 * s,
                decoration: const BoxDecoration(
                  color: _telegramBlue,
                  shape: BoxShape.circle,
                ),
                alignment: Alignment.center,
                child: Icon(
                  Icons.check,
                  size: 14 * s,
                  color: AppColors.surface,
                ),
              )
            else
              Icon(
                Icons.north_east_rounded,
                size: 20 * s,
                color: _telegramBlue,
              ),
          ],
        ),
      ),
    );
  }
}

enum _TileAction { edit, finance, counterparties }

class _TileSpec {
  const _TileSpec({
    required this.title,
    required this.subtitle,
    required this.background,
    required this.foreground,
    required this.decor,
    this.section,
    this.onTap = _TileAction.edit,
    this.centerTitle = false,
    this.bordered = false,
  });

  final String title;
  final String subtitle;
  final Color background;
  final Color foreground;
  final Color decor;
  final ContextSection? section;
  final _TileAction? onTap;
  final bool centerTitle;
  final bool bordered;
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
        border: spec.bordered
            ? Border.all(color: AppColors.border, width: 1)
            : null,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: AppColors.isDark ? 0.35 : 0.25),
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
    final l10n = context.l10n;
    final name = profile?.companyName.trim().isNotEmpty == true
        ? profile!.companyName.trim()
        : l10n.companyNameMissing;
    final industry = () {
      final industry = profile?.companyIndustry.trim() ?? '';
      if (industry.isNotEmpty) return industry;
      final type = profile?.businessType.trim() ?? '';
      if (type.isNotEmpty) return type;
      return l10n.industryNotSpecified;
    }();
    final size = profile?.companySize.trim().isNotEmpty == true
        ? profile!.companySize.trim()
        : l10n.companySizeMissing;

    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceRaised,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(
          color: AppColors.border,
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: AppColors.isDark ? 0.35 : 0.13),
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
