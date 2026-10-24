import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/onboarding_data.dart';
import '../../navigation/app_page_route.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../code_confirm_screen.dart';
import '../login_screen.dart';

Future<void> openSettingsScreen(BuildContext context) {
  return Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => const SettingsScreen(),
    ),
  );
}

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  static const _supportEmail = 'help@aspect.app';
  static const _timeOptions = [
    '06:00',
    '07:00',
    '08:00',
    '09:00',
    '21:00',
    '22:00',
    '23:00',
    '00:00',
  ];

  AppSettings _settings = const AppSettings();
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final settings = await SessionStore.loadSettings();
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _loading = false;
    });
  }

  Future<void> _update(AppSettings next) async {
    setState(() => _settings = next);
    await SessionStore.saveSettings(next);
  }

  Future<void> _openUrl(String url) async {
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  Future<void> _deleteAccount() async {
    final s = context.scale;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16 * s),
          ),
          title: Text(
            'Удалить аккаунт?',
            style: AppTypography.bold(18 * s, color: AppColors.textInk),
          ),
          content: Text(
            'Вы уверены? После подтверждения кода на почте аккаунт будет удалён.',
            style: AppTypography.regular(14 * s, color: AppColors.textMuted),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(
                'Отмена',
                style: AppTypography.regular(
                  14 * s,
                  color: AppColors.textMuted,
                ),
              ),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: Text(
                'Удалить',
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

    final profile = await SessionStore.loadProfile();
    final email = profile?.email.trim() ?? '';
    if (email.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Не удалось отправить код: почта не указана',
            style: AppTypography.regular(13, color: AppColors.surface),
          ),
          behavior: SnackBarBehavior.floating,
          backgroundColor: AppColors.textInk,
        ),
      );
      return;
    }

    if (!mounted) return;
    final ok = await Navigator.of(context).push<bool>(
      AppPageRoute(
        builder: (_) => CodeConfirmScreen(
          data: OnboardingData(email: email),
          verifyOnly: true,
          verifyHint: 'на почту $email',
        ),
      ),
    );
    if (ok != true || !mounted) return;

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
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final languageLabel =
        _settings.language == 'ru' ? 'Русский' : _settings.language;
    final themeLabel =
        _settings.themeMode == 'system' ? 'Системная' : 'Светлая';

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
                child: _loading
                    ? const Center(
                        child: CircularProgressIndicator(
                          color: AppColors.brandRed,
                        ),
                      )
                    : ListView(
                        padding: EdgeInsets.fromLTRB(
                          hPad,
                          8 * s,
                          hPad,
                          24 * s + bottom,
                        ),
                        children: [
                          Text(
                            'Настройки',
                            style: AppTypography.bold(
                              24.83 * s,
                              color: AppColors.textInput,
                            ),
                          ),
                          SizedBox(height: 24 * s),
                          const _SectionLabel(label: 'Уведомления'),
                          SizedBox(height: 10 * s),
                          _SettingsCard(
                            children: [
                              _SwitchRow(
                                title: 'Push-уведомления',
                                subtitle: 'События и важные изменения',
                                value: _settings.pushNotifications,
                                onChanged: (v) => _update(
                                  _settings.copyWith(pushNotifications: v),
                                ),
                              ),
                              const _Divider(),
                              _SwitchRow(
                                title: 'Telegram-алерты',
                                subtitle: 'Дублировать уведомления в Telegram',
                                value: _settings.telegramAlerts,
                                onChanged: (v) => _update(
                                  _settings.copyWith(telegramAlerts: v),
                                ),
                              ),
                              const _Divider(),
                              _SwitchRow(
                                title: 'Тихие часы',
                                subtitle: _settings.quietHours
                                    ? '${_settings.quietStart} – ${_settings.quietEnd}'
                                    : 'Не беспокоить ночью',
                                value: _settings.quietHours,
                                onChanged: (v) => _update(
                                  _settings.copyWith(quietHours: v),
                                ),
                              ),
                              if (_settings.quietHours) ...[
                                const _Divider(),
                                _DropdownRow(
                                  title: 'Начало',
                                  value: _settings.quietStart,
                                  options: {
                                    for (final t in _timeOptions) t: t,
                                  },
                                  onChanged: (v) => _update(
                                    _settings.copyWith(quietStart: v),
                                  ),
                                ),
                                const _Divider(),
                                _DropdownRow(
                                  title: 'Конец',
                                  value: _settings.quietEnd,
                                  options: {
                                    for (final t in _timeOptions) t: t,
                                  },
                                  onChanged: (v) => _update(
                                    _settings.copyWith(quietEnd: v),
                                  ),
                                ),
                              ],
                            ],
                          ),
                          SizedBox(height: 24 * s),
                          const _SectionLabel(label: 'Приложение'),
                          SizedBox(height: 10 * s),
                          _SettingsCard(
                            children: [
                              _DropdownRow(
                                title: 'Язык',
                                value: _settings.language,
                                options: const {'ru': 'Русский'},
                                displayValue: languageLabel,
                                onChanged: (v) => _update(
                                  _settings.copyWith(language: v),
                                ),
                              ),
                              const _Divider(),
                              _DropdownRow(
                                title: 'Тема',
                                value: _settings.themeMode,
                                options: const {
                                  'light': 'Светлая',
                                  'system': 'Системная',
                                },
                                displayValue: themeLabel,
                                onChanged: (v) => _update(
                                  _settings.copyWith(themeMode: v),
                                ),
                              ),
                            ],
                          ),
                          SizedBox(height: 24 * s),
                          const _SectionLabel(label: 'О приложении'),
                          SizedBox(height: 10 * s),
                          _SettingsCard(
                            children: [
                              const _ValueRow(
                                title: 'Версия',
                                value: '1.0.0',
                              ),
                              const _Divider(),
                              _ActionRow(
                                title: 'Политика',
                                value: 'Открыть',
                                onTap: () => _openUrl(
                                  'https://alfabank.ru/privacy/',
                                ),
                              ),
                              const _Divider(),
                              _ActionRow(
                                title: 'Поддержка',
                                value: _supportEmail,
                                onTap: () => _openUrl(
                                  'mailto:$_supportEmail',
                                ),
                              ),
                            ],
                          ),
                          SizedBox(height: 28 * s),
                          SizedBox(
                            height: 52 * s,
                            width: double.infinity,
                            child: OutlinedButton(
                              onPressed: _deleteAccount,
                              style: OutlinedButton.styleFrom(
                                foregroundColor: AppColors.brandRed,
                                side: BorderSide(
                                  color: AppColors.brandRed,
                                  width: 1.5 * s,
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(16 * s),
                                ),
                                splashFactory: NoSplash.splashFactory,
                                overlayColor: Colors.transparent,
                                surfaceTintColor: Colors.transparent,
                              ),
                              child: Text(
                                'Удалить аккаунт',
                                style: AppTypography.bold(
                                  14.06 * s,
                                  color: AppColors.brandRed,
                                ),
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

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Text(
      label,
      style: AppTypography.bold(12 * s, color: AppColors.textMuted),
    );
  }
}

class _SettingsCard extends StatelessWidget {
  const _SettingsCard({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(color: AppColors.border, width: 1),
      ),
      child: Column(children: children),
    );
  }
}

class _Divider extends StatelessWidget {
  const _Divider();

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Divider(
      height: 1 * s,
      thickness: 1 * s,
      indent: 16 * s,
      endIndent: 16 * s,
      color: AppColors.divider,
    );
  }
}

class _AppSwitch extends StatelessWidget {
  const _AppSwitch({
    required this.value,
    required this.onChanged,
  });

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final width = 46 * s;
    final height = 28 * s;
    final thumb = 22 * s;

    return GestureDetector(
      onTap: () => onChanged(!value),
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        width: width,
        height: height,
        padding: EdgeInsets.all(3 * s),
        decoration: BoxDecoration(
          color: value ? AppColors.brandRed : const Color(0xFFE3E6EB),
          borderRadius: BorderRadius.circular(height / 2),
        ),
        child: AnimatedAlign(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          alignment: value ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            width: thumb,
            height: thumb,
            decoration: BoxDecoration(
              color: AppColors.surface,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.12),
                  blurRadius: 4 * s,
                  offset: Offset(0, 1 * s),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SwitchRow extends StatelessWidget {
  const _SwitchRow({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Padding(
      padding: EdgeInsets.fromLTRB(16 * s, 12 * s, 14 * s, 12 * s),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: AppTypography.bold(
                    14 * s,
                    color: AppColors.textInput,
                  ),
                ),
                SizedBox(height: 4 * s),
                Text(
                  subtitle,
                  style: AppTypography.regular(
                    12 * s,
                    color: AppColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
          SizedBox(width: 12 * s),
          _AppSwitch(value: value, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _DropdownRow extends StatelessWidget {
  const _DropdownRow({
    required this.title,
    required this.value,
    required this.options,
    required this.onChanged,
    this.displayValue,
  });

  final String title;
  final String value;
  final Map<String, String> options;
  final ValueChanged<String> onChanged;
  final String? displayValue;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final label = displayValue ?? options[value] ?? value;

    return Padding(
      padding: EdgeInsets.fromLTRB(16 * s, 10 * s, 10 * s, 10 * s),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: AppTypography.bold(14 * s, color: AppColors.textInput),
            ),
          ),
          PopupMenuButton<String>(
            initialValue: value,
            onSelected: onChanged,
            offset: Offset(0, 36 * s),
            color: AppColors.surface,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12 * s),
              side: const BorderSide(color: AppColors.border),
            ),
            itemBuilder: (context) => [
              for (final entry in options.entries)
                PopupMenuItem<String>(
                  value: entry.key,
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          entry.value,
                          style: AppTypography.regular(
                            14 * s,
                            color: AppColors.textPrimary,
                          ),
                        ),
                      ),
                      if (entry.key == value)
                        Icon(
                          Icons.check,
                          size: 16 * s,
                          color: AppColors.brandRed,
                        ),
                    ],
                  ),
                ),
            ],
            child: Container(
              padding: EdgeInsets.symmetric(horizontal: 10 * s, vertical: 8 * s),
              decoration: BoxDecoration(
                color: AppColors.filterChipBg,
                borderRadius: BorderRadius.circular(10 * s),
                border: Border.all(color: AppColors.border),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    label,
                    softWrap: false,
                    style: AppTypography.regular(
                      13 * s,
                      color: AppColors.textMuted,
                    ),
                  ),
                  SizedBox(width: 4 * s),
                  Icon(
                    Icons.keyboard_arrow_down_rounded,
                    size: 18 * s,
                    color: AppColors.textMuted,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ValueRow extends StatelessWidget {
  const _ValueRow({required this.title, required this.value});

  final String title;
  final String value;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Padding(
      padding: EdgeInsets.fromLTRB(16 * s, 14 * s, 16 * s, 14 * s),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: AppTypography.bold(14 * s, color: AppColors.textInput),
            ),
          ),
          Text(
            value,
            softWrap: false,
            textAlign: TextAlign.right,
            style: AppTypography.regular(13 * s, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.title,
    required this.value,
    required this.onTap,
  });

  final String title;
  final String value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.fromLTRB(16 * s, 14 * s, 12 * s, 14 * s),
        child: Row(
          children: [
            Text(
              title,
              style: AppTypography.bold(14 * s, color: AppColors.textInput),
            ),
            SizedBox(width: 12 * s),
            Expanded(
              child: Text(
                value,
                softWrap: false,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.right,
                style: AppTypography.regular(
                  13 * s,
                  color: AppColors.textMuted,
                ),
              ),
            ),
            SizedBox(width: 4 * s),
            Icon(
              Icons.north_east_rounded,
              size: 16 * s,
              color: AppColors.textMuted,
            ),
          ],
        ),
      ),
    );
  }
}
