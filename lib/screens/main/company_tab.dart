import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/auth_api.dart';
import '../../api/companies_api.dart';
import '../../l10n/app_localizations.dart';
import '../../models/onboarding_data.dart';
import '../../services/auth_store.dart';
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

class _CompanyTabState extends State<CompanyTab> with WidgetsBindingObserver {
  OnboardingData? _profile;
  String? _telegramUsername;
  /// Case CSV facts when linked (okved / group / revenue); market share never invented.
  List<String> _caseFacts = const [];
  String? _caseStatus;
  /// Ждём возврат из Telegram после открытия deep link.
  bool _awaitingTelegramLink = false;

  static const _telegramBlue = Color(0xFF2AABEE);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !_awaitingTelegramLink) return;
    _onReturnedFromTelegram();
  }

  Future<void> _load() async {
    final profile = await SessionStore.loadProfile() ?? OnboardingData();
    final authEmail = (await AuthStore.email())?.trim() ?? '';
    if (profile.email.trim().isEmpty && authEmail.isNotEmpty) {
      profile.email = authEmail;
    }
    try {
      final me = await AuthApi.instance.me();
      final jobRole = AuthApi.jobRoleFromMe(me);
      if (jobRole != null) {
        profile.role = jobRole;
      } else if (profile.role.trim().isNotEmpty) {
        // Локальная роль есть, на сервере ещё нет — догоняем.
        try {
          await AuthApi.instance.patchPreferences(jobRole: profile.role.trim());
        } catch (_) {}
      }
      final display = me['display_name']?.toString().trim() ?? '';
      if (display.isNotEmpty && profile.fullName.trim().isEmpty) {
        profile.fullName = display;
      }
    } catch (_) {}
    final companyId = await AuthStore.companyId();
    String? telegram;
    var caseFacts = <String>[];
    String? caseStatus;
    if (companyId != null && companyId.isNotEmpty) {
      try {
        final apiProfile = await CompaniesApi.instance.getProfile(companyId);
        _mergeNodesIntoProfile(profile, apiProfile);
        final company = apiProfile['company'];
        if (company is Map) {
          final name = company['name']?.toString().trim() ?? '';
          if (name.isNotEmpty) profile.companyName = name;
          final industry = company['industry']?.toString().trim() ?? '';
          if (industry.isNotEmpty) profile.companyIndustry = industry;
          // hq_region с API (DaData / онбординг) → плитка «География»,
          // если локальные cities/companyCity ещё пустые.
          final hq = company['hq_region']?.toString().trim() ?? '';
          if (hq.isNotEmpty &&
              profile.companyCity.trim().isEmpty &&
              profile.cities.isEmpty) {
            profile.companyCity = _shortGeographyLabel(hq);
            if (profile.cities.isEmpty) {
              profile.cities = [profile.companyCity];
            }
          }
        }
      } catch (_) {}
      try {
        final ctx = await CompaniesApi.instance.getContext(companyId);
        final caseCtx = ctx['case_context'];
        if (caseCtx is Map) {
          caseStatus = caseCtx['status']?.toString();
          final facts = <String>[];
          final caseProfile = caseCtx['profile'];
          if (caseProfile is Map) {
            String fieldVal(dynamic f) {
              if (f is! Map) return '';
              final v = f['value']?.toString().trim() ?? '';
              if (v.isNotEmpty) return v;
              return f['detail']?.toString().trim() ?? '';
            }
            final okved = fieldVal(caseProfile['okved_name']);
            if (okved.isNotEmpty) facts.add('ОКВЭД: $okved');
            final group = caseProfile['group'];
            if (group is Map) {
              final gid = group['external_group_id']?.toString().trim() ?? '';
              if (gid.isNotEmpty) facts.add('Группа компаний: $gid');
            }
            final revenue = caseProfile['revenue'];
            if (revenue is Map) {
              final amount = revenue['amount']?.toString().trim() ?? '';
              final raw = revenue['revenue_raw']?.toString().trim() ?? '';
              if (amount.isNotEmpty) {
                facts.add('Выручка (справочник): $amount');
              } else if (raw.isNotEmpty) {
                facts.add('Выручка (справочник): $raw');
              }
            }
            final share = caseProfile['market_share'];
            if (share is Map) {
              final status = share['status']?.toString() ?? '';
              final detail = share['detail'];
              var note = '';
              if (detail is Map) {
                note = detail['note']?.toString().trim() ?? '';
              } else if (detail != null) {
                note = detail.toString().trim();
              }
              if (status == 'absent' || share['value'] == null) {
                facts.add(
                  note.isNotEmpty
                      ? note
                      : 'Доля рынка: в справочнике не указана',
                );
              }
            }
          }
          caseFacts = facts;
        }
      } catch (_) {}
      try {
        final industry =
            await CompaniesApi.instance.getIndustryProfile(companyId);
        List<String> listOf(dynamic v) => [
              if (v is List)
                for (final i in v)
                  if (i != null && i.toString().trim().isNotEmpty)
                    i.toString().trim(),
            ];
        final brands = listOf(industry['brands']);
        final cats = listOf(industry['product_categories']);
        final lines = listOf(industry['product_lines']);
        final proc = listOf(industry['procurement_countries']);
        if (brands.isNotEmpty) profile.brands = brands;
        if (cats.isNotEmpty) profile.productCategories = cats;
        if (lines.isNotEmpty) profile.productLines = lines;
        if (proc.isNotEmpty) profile.procurementCountries = proc;
        final role = industry['activity_role']?.toString() ?? '';
        if (role.isNotEmpty) profile.activityRole = role;
      } catch (_) {}
      try {
        final settings =
            await CompaniesApi.instance.notificationSettings(companyId);
        final private = settings['telegram_private'];
        if (private is Map && private['linked'] == true) {
          final title = private['chat_title']?.toString();
          telegram = (title != null && title.isNotEmpty) ? title : 'telegram';
          await SessionStore.saveTelegramUsername(telegram);
        } else {
          await SessionStore.saveTelegramUsername(null);
        }
      } catch (_) {
        telegram = null;
      }
    }
    await SessionStore.saveProfile(profile);
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _telegramUsername = telegram;
      _caseFacts = caseFacts;
      _caseStatus = caseStatus;
    });
  }

  String? _caseStatusCopy(AppLocalizations l10n) {
    switch (_caseStatus) {
      case 'profile_available':
        return l10n.caseSourceLinked;
      case 'not_linked':
        return l10n.caseSourceNotLinked;
      case 'integration_not_configured':
        return l10n.caseSourceNotConfigured;
      case 'no_active_snapshot':
        return l10n.caseSourceNoSnapshot;
      case 'uid_missing_in_snapshot':
        return l10n.caseSourceUidMissing;
      case 'profile_absent':
        return l10n.caseSourceProfileAbsent;
      default:
        return null;
    }
  }

  void _mergeNodesIntoProfile(
    OnboardingData profile,
    Map<String, dynamic> apiProfile,
  ) {
    final nodes = apiProfile['nodes'];
    if (nodes is! List) return;
    final products = <String>{...profile.products};
    final markets = <String>{...profile.countries};
    final cities = <String>{...profile.cities};
    final suppliers = <String>{...profile.counterparties};
    for (final n in nodes) {
      if (n is! Map) continue;
      final type = (n['node_type'] ?? '').toString();
      final name = (n['name'] ?? '').toString().trim();
      if (name.isEmpty) continue;
      switch (type) {
        case 'product':
          products.add(name);
        case 'market':
          markets.add(name);
        case 'facility' || 'region' || 'city':
          cities.add(name);
        case 'supplier' || 'counterparty':
          suppliers.add(name);
      }
    }
    if (products.isNotEmpty) profile.products = products.toList();
    if (markets.isNotEmpty) profile.countries = markets.toList();
    if (cities.isNotEmpty) profile.cities = cities.toList();
    if (suppliers.isNotEmpty) profile.counterparties = suppliers.toList();
  }

  /// Полный юр. адрес DaData → короткая метка для плитки (город).
  static String _shortGeographyLabel(String raw) {
    final t = raw.trim();
    if (t.isEmpty) return t;
    // «г Махачкала, ул …» / «Махачкала, …»
    final cityMatch = RegExp(
      r'(?:г\.?\s*|город\s+)?([А-ЯЁA-Z][а-яёa-z\-]+)',
      unicode: true,
    ).firstMatch(t);
    if (cityMatch != null) {
      final city = cityMatch.group(1)?.trim() ?? '';
      if (city.isNotEmpty && city.length < t.length) return city;
    }
    if (t.contains(',')) return t.split(',').first.trim();
    return t;
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
      [
        ...d.products,
        ...d.brands,
        ...d.productCategories,
        if (d.products.isEmpty &&
            d.brands.isEmpty &&
            d.productCategories.isEmpty) ...[
          if (d.businessTypeSubtitle.trim().isNotEmpty) d.businessTypeSubtitle,
          if (d.businessType.trim().isNotEmpty) d.businessType,
        ],
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

    final companyId = await AuthStore.companyId();
    if (companyId == null || companyId.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l10n.feedNoCompanyBody)),
      );
      return;
    }
    try {
      final res = await CompaniesApi.instance.telegramLinkToken(companyId);
      final deepLink = res['deep_link']?.toString();
      final uri =
          deepLink != null && deepLink.isNotEmpty ? Uri.tryParse(deepLink) : null;
      if (uri == null) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(l10n.telegramPending)),
        );
        return;
      }
      // Не показываем SnackBar до ухода в Telegram — при возврате он мигает
      // на секунду и пропадает. Подсказку даём уже после resume.
      _awaitingTelegramLink = true;
      final opened =
          await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!opened) {
        _awaitingTelegramLink = false;
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(l10n.telegramPending)),
        );
      }
    } catch (e) {
      _awaitingTelegramLink = false;
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString())),
      );
    }
  }

  Future<void> _onReturnedFromTelegram() async {
    final companyId = await AuthStore.companyId();
    if (companyId == null || companyId.isEmpty) {
      _awaitingTelegramLink = false;
      return;
    }
    final linked = await _refreshTelegramStatus(companyId);
    if (!mounted) return;
    if (linked) {
      _awaitingTelegramLink = false;
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.telegramConnected),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 3),
        ),
      );
      return;
    }
    // Ещё не подтвердили в боте — стабильное уведомление после возврата.
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(context.l10n.telegramPending),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 8),
        action: SnackBarAction(
          label: 'OK',
          onPressed: () {
            _awaitingTelegramLink = false;
          },
        ),
      ),
    );
  }

  /// Returns whether Telegram is linked after refresh.
  Future<bool> _refreshTelegramStatus(String companyId) async {
    try {
      final settings =
          await CompaniesApi.instance.notificationSettings(companyId);
      final private = settings['telegram_private'];
      final linked = private is Map && private['linked'] == true;
      final title = private is Map
          ? private['chat_title']?.toString()
          : null;
      if (!mounted) return linked;
      if (linked) {
        final name = (title != null && title.isNotEmpty)
            ? title
            : 'telegram';
        await SessionStore.saveTelegramUsername(name);
        setState(() => _telegramUsername = name);
      } else {
        await SessionStore.saveTelegramUsername(null);
        setState(() => _telegramUsername = null);
      }
      return linked;
    } catch (_) {
      // Keep previous UI state; do not invent a connected username.
      return false;
    }
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
        if (_caseStatus != null) ...[
          SizedBox(height: 12 * s),
          _CaseSourceCard(
            title: l10n.caseSourceTitle,
            body: _caseStatusCopy(l10n) ?? '',
            facts: _caseFacts,
            linked: _caseStatus == 'profile_available',
          ),
        ],
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

class _CaseSourceCard extends StatelessWidget {
  const _CaseSourceCard({
    required this.title,
    required this.body,
    required this.facts,
    required this.linked,
  });

  final String title;
  final String body;
  final List<String> facts;
  final bool linked;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(14 * s, 14 * s, 14 * s, 14 * s),
      decoration: BoxDecoration(
        color: AppColors.surfaceRaised,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(color: AppColors.border, width: 1),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: AppColors.isDark ? 0.35 : 0.1),
            offset: Offset(0, 4 * s),
            blurRadius: 12 * s,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: AppTypography.bold(
                    15.13 * s,
                    color: AppColors.textInk,
                  ),
                ),
              ),
              Container(
                width: 8 * s,
                height: 8 * s,
                decoration: BoxDecoration(
                  color: linked ? const Color(0xFF2E7D32) : AppColors.textMuted,
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ),
          if (body.isNotEmpty) ...[
            SizedBox(height: 6 * s),
            Text(
              body,
              style: AppTypography.regular(
                12 * s,
                color: AppColors.textMuted,
              ),
            ),
          ],
          if (facts.isNotEmpty) ...[
            SizedBox(height: 10 * s),
            for (var i = 0; i < facts.length; i++) ...[
              if (i > 0) SizedBox(height: 4 * s),
              Text(
                facts[i],
                style: AppTypography.regular(
                  12 * s,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ],
        ],
      ),
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
                padding: EdgeInsets.fromLTRB(12 * s, 10 * s, 28 * s, 8 * s),
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
                    SizedBox(height: 4 * s),
                    Expanded(
                      child: Align(
                        alignment: Alignment.bottomLeft,
                        child: Text(
                          spec.subtitle,
                          maxLines: spec.section == ContextSection.myData
                              ? 3
                              : 2,
                          overflow: TextOverflow.ellipsis,
                          style: AppTypography.regular(
                            10 * s,
                            color: spec.foreground.withValues(
                              alpha: onDark ? 0.92 : 0.75,
                            ),
                          ).copyWith(height: 1.15),
                        ),
                      ),
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

  /// Подбирает размер шрифта, чтобы текст влез в [maxLines] при ширине [maxWidth].
  static double _fitFontSize({
    required String text,
    required TextStyle style,
    required double maxWidth,
    required int maxLines,
    required double minSize,
    required double maxSize,
  }) {
    if (text.isEmpty || maxWidth <= 0) return maxSize;
    var lo = minSize;
    var hi = maxSize;
    var best = minSize;
    for (var i = 0; i < 12; i++) {
      final mid = (lo + hi) / 2;
      final painter = TextPainter(
        text: TextSpan(text: text, style: style.copyWith(fontSize: mid)),
        maxLines: maxLines,
        textDirection: TextDirection.ltr,
        ellipsis: '…',
      )..layout(maxWidth: maxWidth);
      final fits = !painter.didExceedMaxLines &&
          painter.width <= maxWidth + 0.5;
      if (fits) {
        best = mid;
        lo = mid;
      } else {
        hi = mid;
      }
    }
    return best;
  }

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

    // Боковые отступы карточки: 13×scale (слева и справа).
    // Логотип: 48×38 ×scale.
    const sidePad = 13.0;
    const logoW = 48.0;
    const logoH = 38.0;
    const logoGap = 15.0;

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
        padding: EdgeInsets.fromLTRB(
          sidePad * s,
          24 * s,
          sidePad * s,
          20 * s,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SvgPicture.asset(
                  'assets/images/welcome_logo.svg',
                  width: logoW * s,
                  height: logoH * s,
                  fit: BoxFit.contain,
                ),
                SizedBox(width: logoGap * s),
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      final nameStyle = AppTypography.bold(
                        20 * s,
                        color: AppColors.textInk,
                      );
                      final industryStyle = AppTypography.regular(
                        14 * s,
                        color: AppColors.textCaption,
                      );
                      final nameSize = _fitFontSize(
                        text: name,
                        style: nameStyle,
                        maxWidth: constraints.maxWidth,
                        maxLines: 1,
                        minSize: 12 * s,
                        maxSize: 20 * s,
                      );
                      final industrySize = _fitFontSize(
                        text: industry,
                        style: industryStyle,
                        maxWidth: constraints.maxWidth,
                        maxLines: 2,
                        minSize: 10 * s,
                        maxSize: 14 * s,
                      );
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            name,
                            maxLines: 1,
                            softWrap: false,
                            overflow: TextOverflow.ellipsis,
                            style: nameStyle.copyWith(fontSize: nameSize),
                          ),
                          SizedBox(height: 2 * s),
                          Text(
                            industry,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: industryStyle
                                .copyWith(fontSize: industrySize, height: 1.2),
                          ),
                        ],
                      );
                    },
                  ),
                ),
              ],
            ),
            SizedBox(height: 20 * s),
            Divider(height: 1 * s, thickness: 1 * s, color: AppColors.divider),
            SizedBox(height: 14 * s),
            // Иконка+штат: слева от края карточки 30 (card sidePad 13 + добор).
            Padding(
              padding: EdgeInsets.only(left: (30 - sidePad) * s),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  SvgPicture.asset(
                    'assets/images/icon_company_size.svg',
                    width: 16 * s,
                    height: 18 * s,
                    fit: BoxFit.contain,
                  ),
                  SizedBox(width: logoGap * s),
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
            ),
          ],
        ),
      ),
    );
  }
}
