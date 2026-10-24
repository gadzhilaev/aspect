import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../l10n/app_localizations.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../widgets/main_widgets.dart';
import 'company_tab.dart';
import 'events_tab.dart';
import 'overview_tab.dart';
import 'scenarios_tab.dart';
import 'settings_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({
    super.key,
    this.userName = 'Пользователь',
    this.openSettingsOnStart = false,
    /// 0 Обзор · 1 События · 2 Сценарии · 3 Компания
    this.initialTabIndex = 0,
  });

  final String userName;
  final bool openSettingsOnStart;
  final int initialTabIndex;

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  late int _index;
  late String _userName;
  bool _headerScrolled = false;
  final Map<int, double> _scrollOffsets = {};
  int _scenariosUnread = 0;

  @override
  void initState() {
    super.initState();
    // Настройки открываются из Компании — после splash возвращаем туда же.
    _index = widget.openSettingsOnStart
        ? 3
        : widget.initialTabIndex.clamp(0, 3);
    _userName = widget.userName;
    _refreshUserName();
    _loadScenariosUnread();
    SystemChrome.setSystemUIOverlayStyle(AppColors.systemOverlay);
    if (widget.openSettingsOnStart) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        openSettingsScreen(context, animated: false);
      });
    }
  }

  Future<void> _refreshUserName() async {
    final name = await SessionStore.userName();
    if (!mounted || name.isEmpty) return;
    if (name != _userName) {
      setState(() => _userName = name);
    }
  }

  Future<void> _loadScenariosUnread() async {
    final viewed = await SessionStore.viewedScenarioIds();
    if (!mounted) return;
    final count =
        kNewScenarioIds.where((id) => !viewed.contains(id)).length;
    if (count != _scenariosUnread) {
      setState(() => _scenariosUnread = count);
    }
  }

  void _onScenariosUnreadChanged(int count) {
    if (!mounted || count == _scenariosUnread) return;
    setState(() => _scenariosUnread = count);
  }

  void _onTabScroll(ScrollNotification notification) {
    if (notification.metrics.axis != Axis.vertical) return;
    // Only the tab's primary ListView (depth 0 inside the listener child).
    if (notification.depth > 0) return;
    final pixels = notification.metrics.pixels;
    _scrollOffsets[_index] = pixels;
    final show = pixels > 0.5;
    if (show != _headerScrolled) {
      setState(() => _headerScrolled = show);
    }
  }

  void _selectTab(int index) {
    setState(() {
      _index = index;
      _headerScrolled = (_scrollOffsets[index] ?? 0) > 0.5;
    });
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final pages = [
      OverviewTab(userName: _userName),
      const EventsTab(),
      ScenariosTab(onUnreadChanged: _onScenariosUnreadChanged),
      const CompanyTab(),
    ];

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 120),
              decoration: BoxDecoration(
                color: AppColors.surface,
                border: Border(
                  bottom: BorderSide(
                    color: _headerScrolled
                        ? AppColors.scrollEdge
                        : Colors.transparent,
                  ),
                ),
              ),
              padding: EdgeInsets.fromLTRB(
                AppColors.screenPadding * s,
                8 * s,
                AppColors.screenPadding * s,
                0,
              ),
              child: AspectBrandHeader(
                dateText: formatOverviewDate(null, context.l10n),
              ),
            ),
            Expanded(
              child: NotificationListener<ScrollNotification>(
                onNotification: (notification) {
                  _onTabScroll(notification);
                  return false;
                },
                child: IndexedStack(
                  index: _index,
                  children: pages,
                ),
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
          border: Border(
            top: BorderSide(color: AppColors.scrollEdge),
          ),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 64 * s,
            child: Row(
              children: [
                _NavItem(
                  asset: 'assets/images/nav/home.svg',
                  label: l10n.navOverview,
                  selected: _index == 0,
                  onTap: () => _selectTab(0),
                ),
                _NavItem(
                  asset: 'assets/images/nav/events.svg',
                  label: l10n.navEvents,
                  selected: _index == 1,
                  onTap: () => _selectTab(1),
                ),
                _NavItem(
                  asset: 'assets/images/nav/scenarios.svg',
                  label: l10n.navScenarios,
                  selected: _index == 2,
                  onTap: () => _selectTab(2),
                  keepWhiteFills: true,
                  showBadge: _scenariosUnread > 0,
                ),
                _NavItem(
                  asset: 'assets/images/nav/company.svg',
                  label: l10n.navCompany,
                  selected: _index == 3,
                  onTap: () => _selectTab(3),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.asset,
    required this.label,
    required this.selected,
    required this.onTap,
    this.keepWhiteFills = false,
    this.showBadge = false,
  });

  final String asset;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  /// When true, only recolor strokes — keep white circle fills (scenarios).
  final bool keepWhiteFills;
  final bool showBadge;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final color = selected ? AppColors.brandRed : AppColors.navInactive;

    final icon = keepWhiteFills
        ? _TintedStrokeSvg(
            asset: asset,
            color: color,
            width: 18 * s,
            height: 20 * s,
          )
        : SvgPicture.asset(
            asset,
            width: 18 * s,
            height: 20 * s,
            colorFilter: ColorFilter.mode(color, BlendMode.srcIn),
          );

    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                icon,
                if (showBadge)
                  Positioned(
                    right: -4 * s,
                    top: -2 * s,
                    child: Container(
                      width: 8 * s,
                      height: 8 * s,
                      decoration: BoxDecoration(
                        color: AppColors.brandRed,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
              ],
            ),
            SizedBox(height: 4 * s),
            Text(
              label,
              style: TextStyle(
                fontSize: 11 * s,
                fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TintedStrokeSvg extends StatelessWidget {
  const _TintedStrokeSvg({
    required this.asset,
    required this.color,
    required this.width,
    required this.height,
  });

  final String asset;
  final Color color;
  final double width;
  final double height;

  static String _hex(Color c) {
    final v = c.toARGB32();
    return '#${(v & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    // Кружки fill=white должны совпадать с фоном навбара.
    final hole = Theme.of(context).scaffoldBackgroundColor;
    final holeHex = _hex(hole == Colors.transparent ? AppColors.surface : hole);
    return FutureBuilder<String>(
      future: DefaultAssetBundle.of(context).loadString(asset),
      builder: (context, snap) {
        if (!snap.hasData) {
          return SizedBox(width: width, height: height);
        }
        final hex = _hex(color);
        final svg = snap.data!
            .replaceAll(RegExp(r'stroke="#757575"'), 'stroke="$hex"')
            .replaceAll(RegExp(r'stroke="#EF3124"'), 'stroke="$hex"')
            .replaceAll(RegExp(r'fill="white"'), 'fill="$holeHex"')
            .replaceAll(RegExp(r'fill="#FFFFFF"', caseSensitive: false),
                'fill="$holeHex"')
            .replaceAll(RegExp(r"fill='white'"), 'fill="$holeHex"');
        return SvgPicture.string(
          svg,
          width: width,
          height: height,
          fit: BoxFit.contain,
        );
      },
    );
  }
}
