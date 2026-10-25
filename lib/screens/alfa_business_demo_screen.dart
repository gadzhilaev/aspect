import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../demo/alfa_demo_data.dart';
import '../l10n/app_localizations.dart';
import '../models/onboarding_data.dart';
import '../navigation/app_page_route.dart';
import '../navigation/enter_main.dart';
import '../services/auth_store.dart';
import '../services/session_store.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';
import '../widgets/auth_widgets.dart';

const _alfaBg = Color(0xFFF2F3F5);
const _alfaCard = Color(0xFFFFFFFF);
const _alfaMuted = Color(0xFF6B737C);
const _alfaInk = Color(0xFF0B1F33);
const _promoBlue = Color(0xFFD6E8F7);
const _alfaChip = Color(0xFFE8EAED);

class _DemoCompany {
  const _DemoCompany({
    required this.name,
    required this.industry,
  });

  final String name;
  final String industry;
}

const _demoCompanies = [
  _DemoCompany(
    name: 'ООО «Млечный путь»',
    industry: 'Производство продуктов питания',
  ),
  _DemoCompany(
    name: 'ООО «СеверПром»',
    industry: 'Промышленное производство',
  ),
  _DemoCompany(
    name: 'ООО «ВолгПром»',
    industry: 'Промышленное производство',
  ),
  _DemoCompany(
    name: 'ООО «Альфа Логистик»',
    industry: 'Транспорт и логистика',
  ),
];

Future<void> openAlfaBusinessDemo(BuildContext context) {
  return Navigator.of(context).push(
    AppPageRoute<void>(
      builder: (_) => const AlfaBusinessGateScreen(),
    ),
  );
}

Future<_DemoCompany?> _openCompanyPicker(
  BuildContext context, {
  _DemoCompany? current,
  required String title,
  bool requireSelection = false,
}) {
  return Navigator.of(context).push<_DemoCompany>(
    AppPageRoute(
      builder: (_) => _AlfaCompanyPickerPage(
        title: title,
        companies: _demoCompanies,
        initial: current,
        requireSelection: requireSelection,
      ),
    ),
  );
}

class AlfaBusinessGateScreen extends StatefulWidget {
  const AlfaBusinessGateScreen({super.key});

  @override
  State<AlfaBusinessGateScreen> createState() => _AlfaBusinessGateScreenState();
}

class _AlfaBusinessGateScreenState extends State<AlfaBusinessGateScreen> {
  _DemoCompany _company = _demoCompanies.first;

  void _openAspect() {
    Navigator.of(context).push(
      AppPageRoute<void>(
        builder: (_) => const AlfaCompanyPickScreen(),
      ),
    );
  }

  Future<void> _switchCompany() async {
    final picked = await _openCompanyPicker(
      context,
      current: _company,
      title: context.l10n.companyPickerTitle,
    );
    if (picked != null && mounted) {
      setState(() => _company = picked);
    }
  }

  void _openProfile() {
    Navigator.of(context).push(
      AppPageRoute<void>(
        builder: (_) => AlfaBusinessProfileScreen(
          onEnterAspect: _openAspect,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final bottom = MediaQuery.paddingOf(context).bottom;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: _alfaBg,
        body: Column(
          children: [
            Expanded(
              child: CustomScrollView(
                slivers: [
                  SliverToBoxAdapter(
                    child: SafeArea(
                      bottom: false,
                      child: Padding(
                        padding: EdgeInsets.fromLTRB(16 * s, 4 * s, 16 * s, 0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Align(
                              alignment: Alignment.centerLeft,
                              child: TextButton(
                                onPressed: () =>
                                    Navigator.of(context).maybePop(),
                                style: TextButton.styleFrom(
                                  foregroundColor: _alfaMuted,
                                  padding: EdgeInsets.symmetric(
                                    horizontal: 0,
                                    vertical: 8 * s,
                                  ),
                                  minimumSize: Size.zero,
                                  tapTargetSize:
                                      MaterialTapTargetSize.shrinkWrap,
                                ),
                                child: Text(
                                  l10n.back,
                                  style: AppTypography.regular(
                                    15 * s,
                                    color: _alfaMuted,
                                  ),
                                ),
                              ),
                            ),
                            SizedBox(height: 4 * s),
                            _AlfaHomeHeader(
                              companyName: _company.name,
                              onCompanyTap: _switchCompany,
                              onProfile: _openProfile,
                            ),
                            SizedBox(height: 14 * s),
                            _BalanceCard(s: s),
                            SizedBox(height: 10 * s),
                            _AccountRow(s: s),
                            SizedBox(height: 10 * s),
                            Row(
                              children: [
                                Expanded(
                                  child: _MiniLinkCard(
                                    s: s,
                                    title: l10n.allAccountsCards,
                                  ),
                                ),
                                SizedBox(width: 10 * s),
                                Expanded(
                                  child: _MiniLinkCard(
                                    s: s,
                                    title: l10n.myProducts,
                                  ),
                                ),
                              ],
                            ),
                            SizedBox(height: 12 * s),
                            _PromoBanner(s: s),
                            SizedBox(height: 14 * s),
                            _AspectEntryCard(s: s, onEnter: _openAspect),
                            SizedBox(height: 18 * s),
                            Text(
                              l10n.tasksInProgress,
                              style: AppTypography.bold(
                                17 * s,
                                color: _alfaInk,
                              ),
                            ),
                            SizedBox(height: 10 * s),
                            SizedBox(
                              height: 88 * s,
                              child: ListView(
                                scrollDirection: Axis.horizontal,
                                children: [
                                  _TaskTile(
                                    s: s,
                                    icon: Icons.mail_outline_rounded,
                                    badge: '1',
                                    title: null,
                                  ),
                                  SizedBox(width: 8 * s),
                                  _TaskTile(
                                    s: s,
                                    icon: null,
                                    badge: '4',
                                    title: 'Подписать\nи отправить',
                                    subtitle: 'Платежи и ещё 2',
                                    wide: true,
                                  ),
                                  SizedBox(width: 8 * s),
                                  _TaskTile(
                                    s: s,
                                    icon: null,
                                    badge: null,
                                    title: 'Черновики',
                                    subtitle: '3 документа',
                                    wide: true,
                                  ),
                                ],
                              ),
                            ),
                            SizedBox(height: 20 * s),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            _AlfaBottomNav(s: s, bottomInset: bottom),
          ],
        ),
      ),
    );
  }
}

class AlfaBusinessProfileScreen extends StatelessWidget {
  const AlfaBusinessProfileScreen({
    super.key,
    required this.onEnterAspect,
  });

  final VoidCallback onEnterAspect;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final bottom = MediaQuery.paddingOf(context).bottom;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: _alfaBg,
        body: SafeArea(
          bottom: false,
          child: Column(
            children: [
              Padding(
                padding: EdgeInsets.fromLTRB(8 * s, 4 * s, 8 * s, 0),
                child: Row(
                  children: [
                    IconButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      icon: Icon(
                        Icons.arrow_back_ios_new_rounded,
                        size: 18 * s,
                        color: _alfaInk,
                      ),
                    ),
                    Expanded(
                      child: Text(
                        l10n.profile,
                        textAlign: TextAlign.center,
                        style: AppTypography.bold(17 * s, color: _alfaInk),
                      ),
                    ),
                    IconButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      icon: Icon(
                        Icons.logout_rounded,
                        size: 22 * s,
                        color: _alfaInk,
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(16 * s, 8 * s, 16 * s, 24 * s),
                  children: [
                    Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: 14 * s,
                        vertical: 12 * s,
                      ),
                      decoration: BoxDecoration(
                        color: _alfaChip,
                        borderRadius: BorderRadius.circular(14 * s),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              'Финансовый эксперт',
                              style: AppTypography.regular(
                                15 * s,
                                color: _alfaInk,
                              ),
                            ),
                          ),
                          Icon(
                            Icons.keyboard_arrow_down_rounded,
                            color: _alfaMuted,
                            size: 22 * s,
                          ),
                        ],
                      ),
                    ),
                    SizedBox(height: 12 * s),
                    Container(
                      padding:
                          EdgeInsets.fromLTRB(16 * s, 20 * s, 16 * s, 16 * s),
                      decoration: BoxDecoration(
                        color: _alfaCard,
                        borderRadius: BorderRadius.circular(20 * s),
                      ),
                      child: Column(
                        children: [
                          Container(
                            width: 64 * s,
                            height: 64 * s,
                            decoration: const BoxDecoration(
                              color: _alfaChip,
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              Icons.person_rounded,
                              size: 36 * s,
                              color: _alfaMuted,
                            ),
                          ),
                          SizedBox(height: 12 * s),
                          Text(
                            'Владимир Бородин',
                            style: AppTypography.bold(18 * s, color: _alfaInk),
                          ),
                          SizedBox(height: 4 * s),
                          Text(
                            'Руководитель',
                            style: AppTypography.regular(
                              14 * s,
                              color: _alfaMuted,
                            ),
                          ),
                          SizedBox(height: 14 * s),
                          Container(
                            width: double.infinity,
                            padding: EdgeInsets.symmetric(vertical: 12 * s),
                            decoration: BoxDecoration(
                              color: _alfaChip,
                              borderRadius: BorderRadius.circular(24 * s),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  Icons.edit_outlined,
                                  size: 16 * s,
                                  color: _alfaInk,
                                ),
                                SizedBox(width: 6 * s),
                                Text(
                                  l10n.edit,
                                  style: AppTypography.regular(
                                    14 * s,
                                    color: _alfaInk,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    SizedBox(height: 12 * s),
                    Container(
                      padding: EdgeInsets.all(14 * s),
                      decoration: BoxDecoration(
                        color: _alfaChip,
                        borderRadius: BorderRadius.circular(16 * s),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 40 * s,
                            height: 40 * s,
                            decoration: BoxDecoration(
                              color: _alfaInk,
                              borderRadius: BorderRadius.circular(10 * s),
                            ),
                            child: Icon(
                              Icons.pie_chart_rounded,
                              color: Colors.white,
                              size: 20 * s,
                            ),
                          ),
                          SizedBox(width: 12 * s),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Тариф «Активные расчеты»',
                                  style: AppTypography.bold(
                                    14 * s,
                                    color: _alfaInk,
                                  ),
                                ),
                                SizedBox(height: 2 * s),
                                Text(
                                  'Дата оплаты — 14 июня 2025',
                                  style: AppTypography.regular(
                                    12 * s,
                                    color: _alfaMuted,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    SizedBox(height: 16 * s),
                    _AspectEntryCard(s: s, onEnter: onEnterAspect),
                    SizedBox(height: 20 * s),
                    Text(
                      l10n.companyData,
                      style: AppTypography.bold(17 * s, color: _alfaInk),
                    ),
                    SizedBox(height: 10 * s),
                    _ProfileMenuItem(
                      s: s,
                      icon: Icons.apartment_rounded,
                      title: l10n.companyCard,
                      subtitle:
                          'Реквизиты, контакты, виды деятельности, руководители',
                    ),
                    _ProfileMenuItem(
                      s: s,
                      icon: Icons.groups_outlined,
                      title: 'Пользователи и роли',
                      subtitle: 'Создание и настройка пользователей и ролей',
                    ),
                    _ProfileMenuItem(
                      s: s,
                      icon: Icons.local_fire_department_outlined,
                      title: 'Платим за рекомендации',
                      subtitle:
                          'Получайте баллы и меняйте их на деньги и услуги банка',
                    ),
                    SizedBox(height: bottom),
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

class _AspectEntryCard extends StatelessWidget {
  const _AspectEntryCard({
    required this.s,
    required this.onEnter,
  });

  final double s;
  final VoidCallback onEnter;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Container(
      padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 16 * s, 14 * s),
      decoration: BoxDecoration(
        color: _alfaCard,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              AuthLogo(height: 28 * s),
              SizedBox(width: 10 * s),
              Expanded(
                child: Text(
                  l10n.aspectCardTitle,
                  style: AppTypography.bold(16 * s, color: AppColors.textInput),
                ),
              ),
            ],
          ),
          SizedBox(height: 10 * s),
          Text(
            l10n.aspectCardBody,
            style: AppTypography.regular(
              13 * s,
              color: AppColors.textSecondary,
            ),
          ),
          SizedBox(height: 14 * s),
          AuthPrimaryButton(
            label: l10n.enterAspect,
            onPressed: onEnter,
          ),
        ],
      ),
    );
  }
}

class _AlfaHomeHeader extends StatelessWidget {
  const _AlfaHomeHeader({
    required this.companyName,
    required this.onCompanyTap,
    required this.onProfile,
  });

  final String companyName;
  final VoidCallback onCompanyTap;
  final VoidCallback onProfile;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Row(
      children: [
        Expanded(
          child: GestureDetector(
            onTap: onCompanyTap,
            behavior: HitTestBehavior.opaque,
            child: Row(
              children: [
                Container(
                  width: 36 * s,
                  height: 36 * s,
                  decoration: BoxDecoration(
                    color: AppColors.brandRed,
                    shape: BoxShape.circle,
                  ),
                  alignment: Alignment.center,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'А',
                        style: TextStyle(
                          fontFamily: AppTypography.family,
                          fontWeight: FontWeight.w700,
                          fontSize: 16 * s,
                          height: 1,
                          color: Colors.white,
                        ),
                      ),
                      Container(
                        width: 10 * s,
                        height: 1.5 * s,
                        color: Colors.white,
                      ),
                    ],
                  ),
                ),
                SizedBox(width: 10 * s),
                Flexible(
                  child: Text(
                    companyName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.bold(15 * s, color: _alfaInk),
                  ),
                ),
                SizedBox(width: 2 * s),
                Icon(
                  Icons.keyboard_arrow_down_rounded,
                  size: 20 * s,
                  color: _alfaInk,
                ),
              ],
            ),
          ),
        ),
        SizedBox(width: 8 * s),
        GestureDetector(
          onTap: onProfile,
          child: Icon(
            Icons.person_outline_rounded,
            size: 26 * s,
            color: _alfaInk,
          ),
        ),
        SizedBox(width: 14 * s),
        Stack(
          clipBehavior: Clip.none,
          children: [
            Icon(
              Icons.notifications_none_rounded,
              size: 26 * s,
              color: _alfaInk,
            ),
            Positioned(
              right: -4 * s,
              top: -4 * s,
              child: Container(
                width: 16 * s,
                height: 16 * s,
                decoration: BoxDecoration(
                  color: AppColors.brandRed,
                  shape: BoxShape.circle,
                ),
                alignment: Alignment.center,
                child: Text(
                  '2',
                  style: TextStyle(
                    fontSize: 9 * s,
                    fontWeight: FontWeight.w700,
                    color: Colors.white,
                    height: 1,
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.s});

  final double s;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Container(
      padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 12 * s, 16 * s),
      decoration: BoxDecoration(
        color: _alfaCard,
        borderRadius: BorderRadius.circular(20 * s),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  l10n.availableBalance,
                  style: AppTypography.regular(13 * s, color: _alfaMuted),
                ),
                SizedBox(height: 6 * s),
                Text(
                  '30 623 060,02 ₽',
                  style: AppTypography.bold(26 * s, color: _alfaInk),
                ),
                SizedBox(height: 4 * s),
                Text(
                  l10n.onRubleAccounts(3),
                  style: AppTypography.regular(12 * s, color: _alfaMuted),
                ),
              ],
            ),
          ),
          Icon(
            Icons.chevron_right_rounded,
            color: _alfaMuted,
            size: 24 * s,
          ),
        ],
      ),
    );
  }
}

class _AccountRow extends StatelessWidget {
  const _AccountRow({required this.s});

  final double s;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(14 * s, 12 * s, 12 * s, 12 * s),
      decoration: BoxDecoration(
        color: _alfaCard,
        borderRadius: BorderRadius.circular(18 * s),
      ),
      child: Row(
        children: [
          Container(
            width: 36 * s,
            height: 36 * s,
            decoration: BoxDecoration(
              color: _alfaChip,
              borderRadius: BorderRadius.circular(10 * s),
            ),
            alignment: Alignment.center,
            child: Text(
              '₽',
              style: AppTypography.bold(16 * s, color: _alfaInk),
            ),
          ),
          SizedBox(width: 10 * s),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '23 984 236,45 ₽',
                  style: AppTypography.bold(15 * s, color: _alfaInk),
                ),
                SizedBox(height: 2 * s),
                Text(
                  'Расчётный счёт ••8245',
                  style: AppTypography.regular(12 * s, color: _alfaMuted),
                ),
                Text(
                  'Фиксированный остаток 150 000 ₽',
                  style: AppTypography.regular(11 * s, color: _alfaMuted),
                ),
              ],
            ),
          ),
          Container(
            width: 44 * s,
            height: 28 * s,
            decoration: BoxDecoration(
              color: _alfaInk,
              borderRadius: BorderRadius.circular(6 * s),
            ),
            alignment: Alignment.center,
            child: Text(
              'МИР',
              style: TextStyle(
                fontSize: 8 * s,
                fontWeight: FontWeight.w700,
                color: Colors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _MiniLinkCard extends StatelessWidget {
  const _MiniLinkCard({required this.s, required this.title});

  final double s;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(14 * s, 14 * s, 10 * s, 14 * s),
      decoration: BoxDecoration(
        color: _alfaCard,
        borderRadius: BorderRadius.circular(16 * s),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: AppTypography.bold(13 * s, color: _alfaInk),
            ),
          ),
          Icon(Icons.chevron_right_rounded, color: _alfaMuted, size: 20 * s),
        ],
      ),
    );
  }
}

class _PromoBanner extends StatelessWidget {
  const _PromoBanner({required this.s});

  final double s;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(14 * s),
      decoration: BoxDecoration(
        color: _promoBlue,
        borderRadius: BorderRadius.circular(18 * s),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              'Не дожидайтесь оплаты покупателя — ваша КС + 4,5%',
              style: AppTypography.bold(13 * s, color: _alfaInk),
            ),
          ),
          SizedBox(width: 8 * s),
          Icon(Icons.percent_rounded, size: 36 * s, color: _alfaMuted),
        ],
      ),
    );
  }
}

class _TaskTile extends StatelessWidget {
  const _TaskTile({
    required this.s,
    required this.icon,
    required this.badge,
    required this.title,
    this.subtitle,
    this.wide = false,
  });

  final double s;
  final IconData? icon;
  final String? badge;
  final String? title;
  final String? subtitle;
  final bool wide;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: wide ? 148 * s : 72 * s,
      padding: EdgeInsets.all(12 * s),
      decoration: BoxDecoration(
        color: _alfaCard,
        borderRadius: BorderRadius.circular(16 * s),
      ),
      child: Stack(
        children: [
          if (icon != null)
            Align(
              alignment: Alignment.center,
              child: Icon(icon, size: 28 * s, color: _alfaInk),
            ),
          if (title != null)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title!,
                  style: AppTypography.bold(13 * s, color: _alfaInk),
                ),
                if (subtitle != null) ...[
                  const Spacer(),
                  Text(
                    subtitle!,
                    style: AppTypography.regular(11 * s, color: _alfaMuted),
                  ),
                ],
              ],
            ),
          if (badge != null)
            Positioned(
              right: 0,
              top: 0,
              child: Container(
                constraints: BoxConstraints(minWidth: 18 * s),
                height: 18 * s,
                padding: EdgeInsets.symmetric(horizontal: 4 * s),
                decoration: BoxDecoration(
                  color: AppColors.brandRed,
                  borderRadius: BorderRadius.circular(9 * s),
                ),
                alignment: Alignment.center,
                child: Text(
                  badge!,
                  style: TextStyle(
                    fontSize: 10 * s,
                    fontWeight: FontWeight.w700,
                    color: Colors.white,
                    height: 1,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ProfileMenuItem extends StatelessWidget {
  const _ProfileMenuItem({
    required this.s,
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final double s;
  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: 14 * s),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 44 * s,
            height: 44 * s,
            decoration: BoxDecoration(
              color: _alfaChip,
              borderRadius: BorderRadius.circular(14 * s),
            ),
            child: Icon(icon, size: 22 * s, color: _alfaInk),
          ),
          SizedBox(width: 12 * s),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: AppTypography.bold(15 * s, color: _alfaInk),
                ),
                SizedBox(height: 2 * s),
                Text(
                  subtitle,
                  style: AppTypography.regular(12 * s, color: _alfaMuted),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AlfaBottomNav extends StatelessWidget {
  const _AlfaBottomNav({required this.s, required this.bottomInset});

  final double s;
  final double bottomInset;

  @override
  Widget build(BuildContext context) {
    Widget item({
      required IconData icon,
      required String label,
      bool active = false,
      String? badge,
    }) {
      final color = active ? AppColors.brandRed : _alfaMuted;
      return Expanded(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                Icon(icon, size: 24 * s, color: color),
                if (badge != null)
                  Positioned(
                    right: -8 * s,
                    top: -4 * s,
                    child: Container(
                      padding: EdgeInsets.symmetric(horizontal: 4 * s),
                      height: 14 * s,
                      decoration: BoxDecoration(
                        color: AppColors.brandRed,
                        borderRadius: BorderRadius.circular(7 * s),
                      ),
                      alignment: Alignment.center,
                      child: Text(
                        badge,
                        style: TextStyle(
                          fontSize: 9 * s,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                          height: 1,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
            SizedBox(height: 4 * s),
            Text(
              label,
              style: AppTypography.regular(10 * s, color: color),
            ),
          ],
        ),
      );
    }

    return Container(
      decoration: const BoxDecoration(
        color: _alfaCard,
        border: Border(top: BorderSide(color: Color(0xFFE5E7EB))),
      ),
      padding: EdgeInsets.fromLTRB(8 * s, 8 * s, 8 * s, 8 * s + bottomInset),
      child: Row(
        children: [
          item(icon: Icons.home_rounded, label: 'Главный', active: true),
          item(icon: Icons.schedule_rounded, label: 'История'),
          item(icon: Icons.payments_outlined, label: 'Платежи'),
          item(icon: Icons.apps_rounded, label: 'Сервисы'),
          item(
            icon: Icons.chat_bubble_outline_rounded,
            label: 'Связь',
            badge: '3',
          ),
        ],
      ),
    );
  }
}

/// Общий выбор компании в стиле Альфа-Бизнес.
class _AlfaCompanyPickerPage extends StatefulWidget {
  const _AlfaCompanyPickerPage({
    required this.title,
    required this.companies,
    this.initial,
    this.requireSelection = false,
  });

  final String title;
  final List<_DemoCompany> companies;
  final _DemoCompany? initial;
  final bool requireSelection;

  @override
  State<_AlfaCompanyPickerPage> createState() => _AlfaCompanyPickerPageState();
}

class _AlfaCompanyPickerPageState extends State<_AlfaCompanyPickerPage> {
  _DemoCompany? _selected;
  String _query = '';

  @override
  void initState() {
    super.initState();
    // Для переключения в шапке можно подсветить текущую;
    // для входа в Аспект — ничего не выбрано.
    if (!widget.requireSelection) {
      _selected = widget.initial;
    }
  }

  List<_DemoCompany> get _filtered {
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) return widget.companies;
    return [
      for (final c in widget.companies)
        if (c.name.toLowerCase().contains(q) ||
            c.industry.toLowerCase().contains(q))
          c,
    ];
  }

  void _confirm() {
    final company = _selected;
    if (company == null) return;
    Navigator.of(context).pop(company);
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final companies = _filtered;
    final canConfirm = _selected != null;

    final l10n = context.l10n;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: _alfaBg,
        body: SafeArea(
          bottom: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: EdgeInsets.fromLTRB(8 * s, 4 * s, 16 * s, 0),
                child: Row(
                  children: [
                    IconButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      icon: Icon(
                        Icons.arrow_back_ios_new_rounded,
                        size: 18 * s,
                        color: _alfaInk,
                      ),
                    ),
                    Expanded(
                      child: Text(
                        widget.title,
                        style: AppTypography.bold(17 * s, color: _alfaInk),
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(16 * s, 8 * s, 16 * s, 0),
                child: Container(
                  height: 48 * s,
                  padding: EdgeInsets.symmetric(horizontal: 14 * s),
                  decoration: BoxDecoration(
                    color: _alfaCard,
                    borderRadius: BorderRadius.circular(14 * s),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: TextField(
                          onChanged: (v) => setState(() => _query = v),
                          style: AppTypography.regular(
                            14 * s,
                            color: _alfaInk,
                          ),
                          cursorColor: AppColors.brandRed,
                          decoration: InputDecoration(
                            isDense: true,
                            border: InputBorder.none,
                            hintText: l10n.companySearchHint,
                            hintStyle: AppTypography.regular(
                              14 * s,
                              color: _alfaMuted,
                            ),
                          ),
                        ),
                      ),
                      Icon(
                        Icons.search,
                        size: 20 * s,
                        color: _alfaMuted,
                      ),
                    ],
                  ),
                ),
              ),
              Expanded(
                child: ListView.separated(
                  padding: EdgeInsets.fromLTRB(16 * s, 14 * s, 16 * s, 16 * s),
                  itemCount: companies.length,
                  separatorBuilder: (_, _) => SizedBox(height: 10 * s),
                  itemBuilder: (context, index) {
                    final company = companies[index];
                    final selected = identical(_selected, company) ||
                        (_selected != null &&
                            _selected!.name == company.name);
                    return _AlfaCompanyTile(
                      company: company,
                      selected: selected,
                      onTap: () => setState(() => _selected = company),
                    );
                  },
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(
                  16 * s,
                  8 * s,
                  16 * s,
                  12 * s + bottom,
                ),
                child: AuthPrimaryButton(
                  label: l10n.continueAction,
                  onPressed: canConfirm ? _confirm : null,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AlfaCompanyTile extends StatelessWidget {
  const _AlfaCompanyTile({
    required this.company,
    required this.selected,
    required this.onTap,
  });

  final _DemoCompany company;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 14 * s, 16 * s),
        decoration: BoxDecoration(
          color: _alfaCard,
          borderRadius: BorderRadius.circular(16 * s),
          border: Border.all(
            color: selected ? AppColors.brandRed : Colors.transparent,
            width: selected ? 1.5 : 1,
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    company.name,
                    style: AppTypography.bold(15 * s, color: _alfaInk),
                  ),
                  SizedBox(height: 4 * s),
                  Text(
                    company.industry,
                    style: AppTypography.regular(13 * s, color: _alfaMuted),
                  ),
                ],
              ),
            ),
            SizedBox(width: 10 * s),
            if (selected)
              Container(
                width: 28 * s,
                height: 28 * s,
                decoration: BoxDecoration(
                  color: AppColors.brandRed,
                  shape: BoxShape.circle,
                ),
                alignment: Alignment.center,
                child: Icon(
                  Icons.check_rounded,
                  size: 16 * s,
                  color: Colors.white,
                ),
              )
            else
              Icon(
                Icons.chevron_right_rounded,
                size: 22 * s,
                color: _alfaMuted,
              ),
          ],
        ),
      ),
    );
  }
}

/// Выбор компании перед входом в Аспект (ничего не выбрано по умолчанию).
class AlfaCompanyPickScreen extends StatefulWidget {
  const AlfaCompanyPickScreen({super.key});

  @override
  State<AlfaCompanyPickScreen> createState() => _AlfaCompanyPickScreenState();
}

class _AlfaCompanyPickScreenState extends State<AlfaCompanyPickScreen> {
  _DemoCompany? _selected;
  String _query = '';

  List<_DemoCompany> get _filtered {
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) return _demoCompanies;
    return [
      for (final c in _demoCompanies)
        if (c.name.toLowerCase().contains(q) ||
            c.industry.toLowerCase().contains(q))
          c,
    ];
  }

  Future<void> _continue() async {
    final company = _selected;
    if (company == null) return;
    final existing = await SessionStore.loadProfile();
    final data = existing ?? OnboardingData();
    data.companyName = company.name;
    data.companyIndustry = company.industry;
    AlfaDemoData.enrichProfile(data, industry: company.industry);
    // Локальный демо-вход: без JWT, с локальной лентой/профилем.
    await AuthStore.clearTokens();
    await AuthStore.saveProfile(
      userId: 'alfa-demo-user',
      email: data.email,
      displayName: data.fullName,
      companyId: '',
      companyName: company.name,
    );
    await SessionStore.markAlfaDemo(enabled: true);
    await SessionStore.finishRegistration(data);
    if (!mounted) return;
    await enterMainApp(
      context,
      userName: firstNameFromFullName(data.fullName),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final companies = _filtered;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: _alfaBg,
        body: SafeArea(
          bottom: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: EdgeInsets.fromLTRB(8 * s, 4 * s, 16 * s, 0),
                child: Row(
                  children: [
                    IconButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      icon: Icon(
                        Icons.arrow_back_ios_new_rounded,
                        size: 18 * s,
                        color: _alfaInk,
                      ),
                    ),
                    Expanded(
                      child: Text(
                        l10n.chooseCompany,
                        style: AppTypography.bold(17 * s, color: _alfaInk),
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(16 * s, 4 * s, 16 * s, 0),
                child: Text(
                  l10n.chooseCompanySub,
                  style: AppTypography.regular(13 * s, color: _alfaMuted),
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(16 * s, 12 * s, 16 * s, 0),
                child: Container(
                  height: 48 * s,
                  padding: EdgeInsets.symmetric(horizontal: 14 * s),
                  decoration: BoxDecoration(
                    color: _alfaCard,
                    borderRadius: BorderRadius.circular(14 * s),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: TextField(
                          onChanged: (v) => setState(() => _query = v),
                          style: AppTypography.regular(14 * s, color: _alfaInk),
                          cursorColor: AppColors.brandRed,
                          decoration: InputDecoration(
                            isDense: true,
                            border: InputBorder.none,
                            hintText: l10n.companySearchHint,
                            hintStyle: AppTypography.regular(
                              14 * s,
                              color: _alfaMuted,
                            ),
                          ),
                        ),
                      ),
                      Icon(Icons.search, size: 20 * s, color: _alfaMuted),
                    ],
                  ),
                ),
              ),
              Expanded(
                child: ListView.separated(
                  padding: EdgeInsets.fromLTRB(16 * s, 14 * s, 16 * s, 16 * s),
                  itemCount: companies.length,
                  separatorBuilder: (_, _) => SizedBox(height: 10 * s),
                  itemBuilder: (context, index) {
                    final company = companies[index];
                    final selected = _selected?.name == company.name;
                    return _AlfaCompanyTile(
                      company: company,
                      selected: selected,
                      onTap: () => setState(() => _selected = company),
                    );
                  },
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(
                  16 * s,
                  8 * s,
                  16 * s,
                  12 * s + bottom,
                ),
                child: AuthPrimaryButton(
                  label: l10n.continueAction,
                  onPressed: _selected == null ? null : _continue,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
