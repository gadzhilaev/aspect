import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../api/auth_api.dart';
import '../app/app_controller.dart';
import '../l10n/app_localizations.dart';
import '../services/auth_store.dart';
import '../services/notification_permission.dart';
import '../services/session_store.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';
import 'login_screen.dart';
import 'main/main_shell.dart';
import 'notification_permission_screen.dart';

/// Белое лого Аспект для красного splash (из assets/images/logo_splash.svg).
const _splashLogoSvg =
    '''<svg width="254" height="52" viewBox="0 0 254 52" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M0.0014203 51.7244C8.24056 37.7075 16.4811 23.692 24.7203 9.67506L45.2492 0C36.5954 14.6589 27.9429 29.3178 19.2891 43.9781C12.8594 46.5602 6.42968 49.1423 0 51.7244H0.0014203Z" fill="white"/><path d="M66.0553 44.6926L50.4107 44.7452C46.2649 35.5061 42.1205 26.2671 37.9746 17.0281C42.4627 17.7794 46.9509 18.5307 51.439 19.2821C56.3106 27.7513 61.1823 36.222 66.0539 44.6912L66.0553 44.6926Z" fill="white"/><path d="M104.053 40.6985L101.694 35.3987H88.6982L86.3387 40.6985H81.4383L93.0179 14.8167H97.628L109.244 40.6985H104.053ZM90.5495 31.1879H99.8423L95.1959 20.7699L90.5495 31.1879ZM124.028 41.1341C120.253 41.1341 117.143 39.8515 114.699 37.2863C112.255 34.7211 111.033 31.563 111.033 27.8121C111.033 24.0127 112.255 20.8425 114.699 18.3015C117.167 15.7605 120.277 14.49 124.028 14.49C126.835 14.49 129.376 15.2281 131.651 16.7043C133.95 18.1805 135.414 20.2254 136.043 22.839H131.034C130.332 21.5806 129.352 20.6247 128.093 19.9713C126.859 19.2937 125.504 18.9549 124.028 18.9549C121.632 18.9549 119.708 19.8261 118.256 21.5685C116.804 23.3109 116.078 25.3921 116.078 27.8121C116.078 30.232 116.816 32.3132 118.292 34.0556C119.769 35.798 121.68 36.6692 124.028 36.6692C127.295 36.6692 129.654 35.3624 131.106 32.7488H136.043C135.704 34.4186 134.918 35.9069 133.684 37.2137C132.449 38.4963 130.997 39.4885 129.328 40.1903C127.9 40.8195 126.133 41.1341 124.028 41.1341ZM141.551 40.6985V14.9256H165.073V40.6985H160.209V19.2816H146.415V40.6985H141.551ZM172.179 40.6985V14.9256H193.051V19.1364H177.043V25.017H186.59V29.264H177.043V36.3788H194.503V40.6985H172.179ZM199.475 40.6985V14.9256H204.339V26.5053L217.625 14.9256H224.159L209.748 27.4491L224.776 40.6985H217.988L204.339 28.901V40.6985H199.475ZM226.187 19.2816V14.9256H251.524V19.2816H241.288V40.6985H236.423V19.2816H226.187Z" fill="white"/></svg>''';

class SplashScreen extends StatefulWidget {
  const SplashScreen({
    super.key,
    this.openSettingsAfter = false,
  });

  /// После splash сразу открыть Настройки (без анимации).
  final bool openSettingsAfter;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  /// Цвет splash по выбранной теме в контроллере (не по устаревшему AppColors).
  Color get _splashRed => AppController.instance.isDark
      ? AppColors.brandRedDark
      : AppColors.brandRedLight;

  @override
  void initState() {
    super.initState();
    _applyOverlay();
    _openNext();
  }

  void _applyOverlay() {
    final red = _splashRed;
    SystemChrome.setSystemUIOverlayStyle(
      SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
        systemNavigationBarColor: red,
        systemNavigationBarIconBrightness: Brightness.light,
      ),
    );
  }

  Future<void> _openNext() async {
    final delayMs = widget.openSettingsAfter ? 1100 : 1600;
    final delay = Future<void>.delayed(Duration(milliseconds: delayMs));
    var loggedIn = await SessionStore.isLoggedIn();
    if (await AuthStore.hasSession()) {
      try {
        await AuthApi.instance.refreshMe();
        loggedIn = await SessionStore.isLoggedIn();
      } catch (_) {
        // Токен протух — остаёмся на логине.
        await AuthStore.clearAll();
        loggedIn = false;
      }
    }
    // Legacy sessions stored only the surname (first FIO token). Drop them so
    // the user signs in again with the full name and greeting uses given name.
    if (loggedIn) {
      final full = await SessionStore.fullName();
      final parts = full.split(RegExp(r'\s+'));
      if (parts.length < 2 && !(await AuthStore.hasSession())) {
        await SessionStore.clear();
        loggedIn = false;
      }
    }
    final userName = loggedIn
        ? firstNameFromFullName(
            (await AuthStore.displayName())?.trim().isNotEmpty == true
                ? (await AuthStore.displayName())!
                : await SessionStore.fullName(),
          )
        : null;
    final notifOk =
        loggedIn ? await NotificationPermission.isGranted() : true;
    await delay;
    if (!mounted) return;

    final name = userName ?? 'Пользователь';
    final Widget next;
    if (!loggedIn) {
      next = const LoginScreen();
    } else if (widget.openSettingsAfter) {
      next = MainShell(userName: name, openSettingsOnStart: true);
    } else if (!notifOk) {
      next = NotificationPermissionScreen(
        userName: name,
        allowSkip: true,
      );
    } else {
      next = MainShell(userName: name);
    }

    Navigator.of(context).pushReplacement(
      PageRouteBuilder<void>(
        transitionDuration: widget.openSettingsAfter
            ? Duration.zero
            : const Duration(milliseconds: 450),
        reverseTransitionDuration: Duration.zero,
        pageBuilder: (_, animation, _) {
          if (widget.openSettingsAfter) return next;
          return FadeTransition(opacity: animation, child: next);
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = designScale(context);
    final l10n = context.l10n;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final red = _splashRed;

    return Scaffold(
      backgroundColor: red,
      body: Stack(
        fit: StackFit.expand,
        children: [
          Center(
            child: SvgPicture.string(
              _splashLogoSvg,
              width: 253 * s,
              height: 52 * s,
              fit: BoxFit.contain,
            ),
          ),
          Positioned(
            left: 24 * s,
            right: 24 * s,
            bottom: bottom + 36 * s,
            child: Text(
              l10n.splashTagline,
              textAlign: TextAlign.center,
              style: AppTypography.medium(
                14.09 * s,
                color: Colors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Перезапуск через splash с возвратом в настройки (смена языка / темы).
Future<void> relaunchThroughSplashToSettings(BuildContext context) async {
  // Синхронизируем палитру с уже выбранной темой до показа splash.
  AppColors.applyBrightness(
    AppController.instance.isDark ? Brightness.dark : Brightness.light,
  );
  await WidgetsBinding.instance.endOfFrame;
  if (!context.mounted) return;
  await Navigator.of(context, rootNavigator: true).pushAndRemoveUntil(
    PageRouteBuilder<void>(
      transitionDuration: Duration.zero,
      reverseTransitionDuration: Duration.zero,
      pageBuilder: (_, _, _) => const SplashScreen(openSettingsAfter: true),
    ),
    (_) => false,
  );
}
