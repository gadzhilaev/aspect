import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/onboarding_data.dart';
import '../navigation/app_page_route.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../widgets/auth_widgets.dart';
import 'code_confirm_screen.dart';
import 'login_screen.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  bool _acceptedTerms = false;

  bool get _canContinue =>
      _nameController.text.trim().isNotEmpty &&
      _emailController.text.trim().isNotEmpty &&
      _passwordController.text.isNotEmpty &&
      _confirmPasswordController.text.isNotEmpty &&
      _acceptedTerms;

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
    for (final c in [
      _nameController,
      _emailController,
      _passwordController,
      _confirmPasswordController,
    ]) {
      c.addListener(_onFormChanged);
    }
  }

  void _onFormChanged() => setState(() {});

  @override
  void dispose() {
    for (final c in [
      _nameController,
      _emailController,
      _passwordController,
      _confirmPasswordController,
    ]) {
      c.removeListener(_onFormChanged);
      c.dispose();
    }
    super.dispose();
  }

  void _openLogin() {
    Navigator.of(context).pushReplacement(
      AppPageRoute<void>(builder: (_) => const LoginScreen()),
    );
  }

  void _continue() {
    final data = OnboardingData(
      email: _emailController.text.trim(),
      fullName: _nameController.text.trim(),
    );
    Navigator.of(context).push(
      AppPageRoute<void>(
        builder: (_) => CodeConfirmScreen(data: data),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    final keyboardOpen = keyboardInset > 0;

    return Scaffold(
      backgroundColor: AppColors.surface,
      resizeToAvoidBottomInset: true,
      body: GestureDetector(
        onTap: () => FocusManager.instance.primaryFocus?.unfocus(),
        behavior: HitTestBehavior.translucent,
        child: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) {
              return SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(30, 20, 30, 24),
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.manual,
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: keyboardOpen
                        ? 0
                        : (constraints.maxHeight - 44)
                            .clamp(0.0, double.infinity),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    mainAxisAlignment: keyboardOpen
                        ? MainAxisAlignment.start
                        : MainAxisAlignment.spaceBetween,
                    children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Align(
                          alignment: Alignment.centerLeft,
                          child: AuthBackButton(),
                        ),
                        const SizedBox(height: 20),
                        const Center(child: AuthLogo()),
                        const SizedBox(height: 16),
                        Text(
                          'Создайте аккаунт',
                          style: AppTypography.medium(
                            28,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Рабочая почта подойдёт лучше всего',
                          style: AppTypography.regular(
                            13,
                            color: AppColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 32),
                        AuthTextField(
                          label: 'ФИО',
                          controller: _nameController,
                          hint: 'Иванов Иван Иванович',
                          textInputAction: TextInputAction.next,
                          keyboardType: TextInputType.text,
                          textCapitalization: TextCapitalization.words,
                        ),
                        const SizedBox(height: 20),
                        AuthTextField(
                          label: 'Рабочая почта',
                          controller: _emailController,
                          hint: 'name@company.ru',
                          textInputAction: TextInputAction.next,
                          keyboardType: TextInputType.emailAddress,
                        ),
                        const SizedBox(height: 20),
                        AuthTextField(
                          label: 'Пароль',
                          controller: _passwordController,
                          hint: 'Не менее 8 символов',
                          obscureText: true,
                          textInputAction: TextInputAction.next,
                        ),
                        const SizedBox(height: 20),
                        AuthTextField(
                          label: 'Повторите пароль',
                          controller: _confirmPasswordController,
                          hint: 'Повторите пароль',
                          obscureText: true,
                          textInputAction: TextInputAction.done,
                        ),
                        const SizedBox(height: 30),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            SizedBox(
                              width: 20,
                              height: 20,
                              child: Checkbox(
                                value: _acceptedTerms,
                                onChanged: (value) {
                                  setState(
                                    () => _acceptedTerms = value ?? false,
                                  );
                                },
                                activeColor: AppColors.brandRed,
                                side: const BorderSide(
                                  color: AppColors.textSecondary,
                                  width: 1,
                                ),
                                materialTapTargetSize:
                                    MaterialTapTargetSize.shrinkWrap,
                                visualDensity: VisualDensity.compact,
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                'Принимаю условия использования и политику данных',
                                style: AppTypography.regular(
                                  11,
                                  color: AppColors.textSecondary,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                    SizedBox(height: keyboardOpen ? 20 : 16),
                    Column(
                      children: [
                        AuthPrimaryButton(
                          label: 'Продолжить',
                          onPressed: _canContinue ? _continue : null,
                        ),
                        const SizedBox(height: 14),
                        AuthFooterLink(
                          prefix: 'Уже есть аккаунт? ',
                          action: 'Войти',
                          onTap: _openLogin,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
            },
          ),
        ),
      ),
    );
  }
}
