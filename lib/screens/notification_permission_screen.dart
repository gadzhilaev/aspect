import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../l10n/app_localizations.dart';
import '../services/notification_permission.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';
import '../widgets/auth_widgets.dart';
import 'main/main_shell.dart';

/// Экран «Разрешите уведомления» перед системным запросом / настройками ОС.
class NotificationPermissionScreen extends StatefulWidget {
  const NotificationPermissionScreen({
    super.key,
    required this.userName,
    this.allowSkip = false,
  });

  final String userName;

  /// Повторный показ (запуск приложения) — кнопка «Пропустить».
  /// При регистрации / первом входе — false.
  final bool allowSkip;

  @override
  State<NotificationPermissionScreen> createState() =>
      _NotificationPermissionScreenState();
}

class _NotificationPermissionScreenState
    extends State<NotificationPermissionScreen> with WidgetsBindingObserver {
  bool _busy = false;
  bool _openedSettings = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !_openedSettings) return;
    _openedSettings = false;
    _afterSettingsReturn();
  }

  Future<void> _afterSettingsReturn() async {
    if (await NotificationPermission.isGranted()) {
      if (!mounted) return;
      _goMain();
    } else if (mounted) {
      setState(() => _busy = false);
    }
  }

  void _goMain() {
    Navigator.of(context).pushAndRemoveUntil(
      PageRouteBuilder<void>(
        transitionDuration: Duration.zero,
        reverseTransitionDuration: Duration.zero,
        pageBuilder: (_, _, _) => MainShell(userName: widget.userName),
      ),
      (_) => false,
    );
  }

  Future<void> _continue() async {
    if (_busy) return;
    setState(() => _busy = true);

    if (await NotificationPermission.isGranted()) {
      if (!mounted) return;
      _goMain();
      return;
    }

    if (await NotificationPermission.canRequestSystemDialog()) {
      await NotificationPermission.request();
      if (!mounted) return;
      _goMain();
      return;
    }

    // Диалог ОС недоступен — открываем настройки уведомлений приложения.
    _openedSettings = true;
    await NotificationPermission.openSystemSettings();
    // Дальше ждём resume в didChangeAppLifecycleState.
  }

  void _skip() {
    if (_busy) return;
    _goMain();
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final top = MediaQuery.paddingOf(context).top;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: AppColors.surface,
        body: SafeArea(
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              AppColors.screenPadding * s,
              24 * s,
              AppColors.screenPadding * s,
              16 * s + bottom,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SizedBox(height: top > 0 ? 8 * s : 24 * s),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        width: 88 * s,
                        height: 88 * s,
                        decoration: BoxDecoration(
                          color: AppColors.brandRed.withValues(alpha: 0.12),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          Icons.notifications_active_rounded,
                          size: 44 * s,
                          color: AppColors.brandRed,
                        ),
                      ),
                      SizedBox(height: 28 * s),
                      Text(
                        l10n.notifPermissionTitle,
                        textAlign: TextAlign.center,
                        style: AppTypography.bold(
                          24 * s,
                          color: AppColors.textInput,
                        ),
                      ),
                      SizedBox(height: 12 * s),
                      Text(
                        l10n.notifPermissionBody,
                        textAlign: TextAlign.center,
                        style: AppTypography.regular(
                          15 * s,
                          color: AppColors.textSecondary,
                        ).copyWith(height: 1.35),
                      ),
                    ],
                  ),
                ),
                AuthPrimaryButton(
                  label: l10n.continueAction,
                  onPressed: _busy ? null : _continue,
                ),
                if (widget.allowSkip) ...[
                  SizedBox(height: 12 * s),
                  SizedBox(
                    height: 48 * s,
                    child: TextButton(
                      onPressed: _busy ? null : _skip,
                      style: TextButton.styleFrom(
                        foregroundColor: AppColors.textSecondary,
                        textStyle: AppTypography.medium(
                          15 * s,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      child: Text(l10n.skipAction),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
