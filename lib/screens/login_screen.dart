import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/onboarding_data.dart';
import '../services/session_store.dart';
import '../theme/app_colors.dart';
import '../theme/design_scale.dart';
import '../widgets/auth_widgets.dart';
import 'main/main_shell.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _nameController = TextEditingController();
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
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  void _openRegister() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const RegisterScreen()),
    );
  }

  Future<void> _login() async {
    final raw = _nameController.text.trim();
    final existing = await SessionStore.loadProfile();
    final data = existing ?? OnboardingData();
    data.fullName = raw;
    data.email = _emailController.text.trim();
    data.password = _passwordController.text;
    await SessionStore.finishRegistration(data);
    final name = firstNameFromFullName(raw);
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(
        builder: (_) => MainShell(userName: name),
      ),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(16 * s, 8 * s, 16 * s, 24 * s),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: AuthBackButton(),
                    ),
                    SizedBox(height: 12 * s),
                    const Center(child: AuthLogo()),
                    SizedBox(height: 28 * s),
                    Text(
                      'Войти',
                      style: TextStyle(
                        fontSize: 28 * s,
                        height: 1.15,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                        letterSpacing: -0.4,
                      ),
                    ),
                    SizedBox(height: 28 * s),
                    AuthTextField(
                      label: 'ФИО',
                      controller: _nameController,
                      hint: 'Иванов Иван Иванович',
                      textInputAction: TextInputAction.next,
                      keyboardType: TextInputType.name,
                    ),
                    SizedBox(height: 22 * s),
                    AuthTextField(
                      label: 'Рабочая почта',
                      controller: _emailController,
                      hint: 'name@company.ru',
                      textInputAction: TextInputAction.next,
                      keyboardType: TextInputType.emailAddress,
                    ),
                    SizedBox(height: 22 * s),
                    AuthTextField(
                      label: 'Пароль',
                      controller: _passwordController,
                      obscureText: true,
                      textInputAction: TextInputAction.done,
                    ),
                    SizedBox(height: 16 * s),
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
                          style: TextStyle(
                            fontSize: 14 * s,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(16 * s, 8 * s, 16 * s, 8 * s),
              child: Column(
                children: [
                  AuthPrimaryButton(
                    label: 'Войти',
                    onPressed: _login,
                  ),
                  SizedBox(height: 12 * s),
                  AuthFooterLink(
                    prefix: 'Нет аккаунта? ',
                    action: 'Зарегистрируйтесь',
                    onTap: _openRegister,
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
