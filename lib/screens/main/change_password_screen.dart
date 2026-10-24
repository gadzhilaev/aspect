import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../models/onboarding_data.dart';
import '../../navigation/app_page_route.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/auth_widgets.dart';
import '../code_confirm_screen.dart';

Future<bool> openChangePasswordScreen(BuildContext context) async {
  final result = await Navigator.of(context).push<bool>(
    AppPageRoute(
      builder: (_) => const ChangePasswordScreen(),
    ),
  );
  return result == true;
}

class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _currentController = TextEditingController();
  final _newController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _currentController.dispose();
    _newController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  bool get _canSubmit {
    return !_submitting &&
        _currentController.text.isNotEmpty &&
        _newController.text.length >= 6 &&
        _newController.text == _confirmController.text;
  }

  Future<void> _submit() async {
    setState(() {
      _error = null;
      _submitting = true;
    });

    final profile = await SessionStore.loadProfile() ?? OnboardingData();
    final stored = profile.password;
    final current = _currentController.text;
    if (stored.isNotEmpty && stored != current) {
      if (!mounted) return;
      setState(() {
        _error = 'Текущий пароль неверный';
        _submitting = false;
      });
      return;
    }

    final email = profile.email.trim();
    if (email.isNotEmpty) {
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
      if (ok != true) {
        if (mounted) setState(() => _submitting = false);
        return;
      }
    }

    profile.password = _newController.text;
    await SessionStore.saveProfile(profile);
    if (!mounted) return;
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;

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
                    onTap: () => Navigator.of(context).maybePop(false),
                    behavior: HitTestBehavior.opaque,
                    child: Text(
                      '‹ Мои данные',
                      style: AppTypography.regular(
                        15 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                  ),
                ),
              ),
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 16 * s),
                  children: [
                    Text(
                      'Пароль',
                      style: AppTypography.bold(
                        24.83 * s,
                        color: AppColors.textInput,
                      ),
                    ),
                    SizedBox(height: 4 * s),
                    Text(
                      'Смена пароля',
                      style: AppTypography.bold(
                        24.83 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                    SizedBox(height: 24 * s),
                    AuthTextField(
                      label: 'Текущий пароль',
                      hint: 'Введите текущий пароль',
                      controller: _currentController,
                      obscureText: true,
                      onChanged: (_) => setState(() {}),
                    ),
                    SizedBox(height: 14 * s),
                    AuthTextField(
                      label: 'Новый пароль',
                      hint: 'Не меньше 6 символов',
                      controller: _newController,
                      obscureText: true,
                      onChanged: (_) => setState(() {}),
                    ),
                    SizedBox(height: 14 * s),
                    AuthTextField(
                      label: 'Повторите пароль',
                      hint: 'Повторите новый пароль',
                      controller: _confirmController,
                      obscureText: true,
                      onChanged: (_) => setState(() {}),
                    ),
                    if (_error != null) ...[
                      SizedBox(height: 12 * s),
                      Text(
                        _error!,
                        style: AppTypography.regular(
                          13 * s,
                          color: AppColors.brandRed,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(
                  hPad,
                  8 * s,
                  hPad,
                  12 * s + bottom,
                ),
                child: AuthPrimaryButton(
                  label: 'Сохранить пароль',
                  onPressed: _canSubmit ? _submit : null,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
