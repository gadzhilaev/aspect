import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/session_store.dart';
import '../theme/app_colors.dart';
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
    final parts = raw.split(RegExp(r'\s+'));
    final name =
        parts.isEmpty || parts.first.isEmpty ? 'Пользователь' : parts.first;
    await SessionStore.saveLogin(userName: name);
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
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(30, 8, 30, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: AuthBackButton(),
                    ),
                    const SizedBox(height: 12),
                    const Center(child: AuthLogo()),
                    const SizedBox(height: 28),
                    const Text(
                      'Войти',
                      style: TextStyle(
                        fontSize: 28,
                        height: 1.15,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                        letterSpacing: -0.4,
                      ),
                    ),
                    const SizedBox(height: 28),
                    AuthTextField(
                      label: 'ФИО',
                      controller: _nameController,
                      hint: 'Иванов Иван Иванович',
                      textInputAction: TextInputAction.next,
                      keyboardType: TextInputType.name,
                    ),
                    const SizedBox(height: 22),
                    AuthTextField(
                      label: 'Рабочая почта',
                      controller: _emailController,
                      hint: 'name@company.ru',
                      textInputAction: TextInputAction.next,
                      keyboardType: TextInputType.emailAddress,
                    ),
                    const SizedBox(height: 22),
                    AuthTextField(
                      label: 'Пароль',
                      controller: _passwordController,
                      obscureText: true,
                      textInputAction: TextInputAction.done,
                    ),
                    const SizedBox(height: 16),
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
                        child: const Text(
                          'Забыли пароль?',
                          style: TextStyle(
                            fontSize: 14,
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
              padding: const EdgeInsets.fromLTRB(30, 8, 30, 24),
              child: Column(
                children: [
                  AuthPrimaryButton(
                    label: 'Войти',
                    onPressed: _login,
                  ),
                  const SizedBox(height: 18),
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
