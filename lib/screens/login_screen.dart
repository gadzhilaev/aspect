import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/onboarding_data.dart';
import '../navigation/app_page_route.dart';
import '../services/session_store.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';
import '../widgets/alfa_business_mark.dart';
import '../widgets/auth_widgets.dart';
import 'alfa_business_demo_screen.dart';
import 'main/main_shell.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    this.showBackButton = false,
  });

  /// Только если экран открыт поверх другого (например, Welcome).
  final bool showBackButton;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

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
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  void _openRegister() {
    Navigator.of(context).push(
      AppPageRoute<void>(builder: (_) => const RegisterScreen()),
    );
  }

  void _dismissKeyboard() {
    FocusManager.instance.primaryFocus?.unfocus();
  }

  Future<void> _login() async {
    _dismissKeyboard();
    final existing = await SessionStore.loadProfile();
    final data = existing ?? OnboardingData();
    data.email = _emailController.text.trim();
    data.password = _passwordController.text;
    if (data.fullName.trim().isEmpty) {
      final local = data.email.split('@').first.trim();
      data.fullName = local.isEmpty ? 'Пользователь Аспект' : local;
    }
    await SessionStore.finishRegistration(data);
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(
        builder: (_) => MainShell(
          userName: firstNameFromFullName(data.fullName),
        ),
      ),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final showBack = widget.showBackButton;

    return Scaffold(
      backgroundColor: AppColors.surface,
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        bottom: false,
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(
                parent: BouncingScrollPhysics(),
              ),
              padding: EdgeInsets.fromLTRB(
                16 * s,
                8 * s,
                16 * s,
                12 * s + bottom,
              ),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: GestureDetector(
                  onTap: _dismissKeyboard,
                  behavior: HitTestBehavior.opaque,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (showBack) ...[
                        const Align(
                          alignment: Alignment.centerLeft,
                          child: AuthBackButton(),
                        ),
                        SizedBox(height: 16 * s),
                      ] else
                        SizedBox(height: 10 * s),
                      const Center(child: AuthLogo()),
                      SizedBox(height: 10 * s),
                      Text(
                        'Войти в Аспект',
                        style: AppTypography.medium(
                          22.5 * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 4 * s),
                      Text(
                        'Продолжите работу с вашей компанией. '
                        'Введите свои данные с приложения Альфа-Бизнес',
                        style: AppTypography.regular(
                          12.7 * s,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      SizedBox(height: 20 * s),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(24 * s),
                        child: SizedBox(
                          height: 188 * s,
                          width: double.infinity,
                          child: Image.asset(
                            'assets/images/welcome_hero.png',
                            fit: BoxFit.cover,
                            alignment: const Alignment(0, -0.18),
                          ),
                        ),
                      ),
                      SizedBox(height: 22 * s),
                      AuthTextField(
                        label: 'Рабочая почта',
                        controller: _emailController,
                        autoScrollOnFocus: false,
                        hint: 'name@company.ru',
                        textInputAction: TextInputAction.next,
                        keyboardType: TextInputType.emailAddress,
                      ),
                      SizedBox(height: 16 * s),
                      AuthTextField(
                        label: 'Пароль',
                        controller: _passwordController,
                        autoScrollOnFocus: false,
                        obscureText: true,
                        textInputAction: TextInputAction.done,
                        onSubmitted: (_) => _login(),
                      ),
                      SizedBox(height: 12 * s),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton(
                          onPressed: () {},
                          style: TextButton.styleFrom(
                            foregroundColor: AppColors.brandRed,
                            padding: EdgeInsets.zero,
                            minimumSize: Size.zero,
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                          child: Text(
                            'Забыли пароль?',
                            style: AppTypography.bold(
                              13 * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                        ),
                      ),
                      SizedBox(height: 12 * s),
                      AuthPrimaryButton(
                        label: 'Войти',
                        onPressed: _login,
                      ),
                      SizedBox(height: 12 * s),
                      SizedBox(
                        height: 52 * s,
                        width: double.infinity,
                        child: OutlinedButton(
                          onPressed: () => openAlfaBusinessDemo(context),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppColors.brandRed,
                            side: BorderSide(
                              color: AppColors.brandRed,
                              width: 1.5 * s,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(16 * s),
                            ),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                'Демо вход через',
                                style: AppTypography.bold(
                                  13 * s,
                                  color: AppColors.brandRed,
                                ),
                              ),
                              SizedBox(width: 8 * s),
                              AlfaBusinessMark(height: 13 * s),
                            ],
                          ),
                        ),
                      ),
                      SizedBox(height: 14 * s),
                      AuthFooterLink(
                        prefix: 'Нет аккаунта? ',
                        action: 'Зарегистрируйтесь',
                        onTap: _openRegister,
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
