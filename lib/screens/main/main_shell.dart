import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

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

  @override
  void initState() {
    super.initState();
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

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final pages = [
      OverviewTab(userName: widget.userName),
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
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppColors.screenPadding * s,
                8 * s,
                AppColors.screenPadding * s,
                0,
              ),
              child: AspectBrandHeader(dateText: formatOverviewDate()),
            ),
            Expanded(
              child: IndexedStack(
                index: _index,
                children: pages,
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
          border: Border(
            top: BorderSide(color: Colors.black.withValues(alpha: 0.06)),
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
                  onTap: () => setState(() => _index = 0),
                ),
                _NavItem(
                  asset: 'assets/images/nav/events.svg',
                  label: 'События',
                  selected: _index == 1,
                  onTap: () => setState(() => _index = 1),
                ),
                _NavItem(
                  asset: 'assets/images/nav/company.svg',
                  label: 'Компания',
                  selected: _index == 2,
                  onTap: () => setState(() => _index = 2),
                ),
                _NavItem(
                  asset: 'assets/images/nav/scenarios.svg',
                  label: 'Сценарии',
                  selected: _index == 3,
                  onTap: () => setState(() => _index = 3),
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
  });

  final String asset;
  final String label;
  final bool selected;
  final VoidCallback onTap;

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
