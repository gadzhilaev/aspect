import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../widgets/main_widgets.dart';
import 'company_tab.dart';
import 'events_tab.dart';
import 'overview_tab.dart';
import 'scenarios_tab.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key, this.userName = 'Пользователь'});

  final String userName;

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _index = 0;
  late String _userName;
  bool _headerScrolled = false;
  final Map<int, double> _scrollOffsets = {};

  @override
  void initState() {
    super.initState();
    _userName = widget.userName;
    _refreshUserName();
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: AppColors.surface,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
  }

  Future<void> _refreshUserName() async {
    final name = await SessionStore.userName();
    if (!mounted || name.isEmpty) return;
    if (name != _userName) {
      setState(() => _userName = name);
    }
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
    final pages = [
      OverviewTab(userName: _userName),
      const EventsTab(),
      const CompanyTab(),
      const ScenariosTab(),
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
              child: AspectBrandHeader(dateText: formatOverviewDate()),
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
                  label: 'Обзор',
                  selected: _index == 0,
                  onTap: () => _selectTab(0),
                ),
                _NavItem(
                  asset: 'assets/images/nav/events.svg',
                  label: 'События',
                  selected: _index == 1,
                  onTap: () => _selectTab(1),
                ),
                _NavItem(
                  asset: 'assets/images/nav/company.svg',
                  label: 'Компания',
                  selected: _index == 2,
                  onTap: () => _selectTab(2),
                ),
                _NavItem(
                  asset: 'assets/images/nav/scenarios.svg',
                  label: 'Сценарии',
                  selected: _index == 3,
                  onTap: () => _selectTab(3),
                  keepWhiteFills: true,
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
  });

  final String asset;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  /// When true, only recolor strokes — keep white circle fills (scenarios).
  final bool keepWhiteFills;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final color = selected ? AppColors.brandRed : AppColors.navInactive;

    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (keepWhiteFills)
              _TintedStrokeSvg(
                asset: asset,
                color: color,
                width: 18 * s,
                height: 20 * s,
              )
            else
              SvgPicture.asset(
                asset,
                width: 18 * s,
                height: 20 * s,
                colorFilter: ColorFilter.mode(color, BlendMode.srcIn),
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
    return FutureBuilder<String>(
      future: DefaultAssetBundle.of(context).loadString(asset),
      builder: (context, snap) {
        if (!snap.hasData) {
          return SizedBox(width: width, height: height);
        }
        final hex = _hex(color);
        final svg = snap.data!
            .replaceAll(RegExp(r'stroke="#757575"'), 'stroke="$hex"')
            .replaceAll(RegExp(r'stroke="#EF3124"'), 'stroke="$hex"');
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
