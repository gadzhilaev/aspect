import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/onboarding_data.dart';
import '../navigation/app_page_route.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';
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
      password: _passwordController.text,
    );
    Navigator.of(context).push(
      AppPageRoute<void>(
        builder: (_) => CodeConfirmScreen(data: data),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    final keyboardOpen = keyboardInset > 0;

    return Scaffold(
      backgroundColor: AppColors.surface,
      // Shrink body above keyboard so focused fields can scroll into view.
      resizeToAvoidBottomInset: true,
      body: GestureDetector(
        onTap: () => FocusManager.instance.primaryFocus?.unfocus(),
        behavior: HitTestBehavior.translucent,
        child: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) {
              return SingleChildScrollView(
                physics: keyboardOpen
                    ? const ClampingScrollPhysics()
                    : const NeverScrollableScrollPhysics(),
                padding: EdgeInsets.fromLTRB(16 * s, 12 * s, 16 * s, 8 * s),
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.manual,
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: keyboardOpen
                        ? 0
                        : (constraints.maxHeight - 32 * s)
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
                          SizedBox(height: 14 * s),
                          Center(child: AuthLogo(height: 28 * s)),
                          SizedBox(height: 12 * s),
                          Text(
                            'Создайте аккаунт',
                            style: AppTypography.medium(
                              24 * s,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          SizedBox(height: 4 * s),
                          Text(
                            'Рабочая почта подойдёт лучше всего',
                            style: AppTypography.regular(
                              12 * s,
                              color: AppColors.textSecondary,
                            ),
                          ),
                          SizedBox(height: 22 * s),
                          AuthTextField(
                            label: 'ФИО',
                            controller: _nameController,
                            hint: 'Иванов Иван Иванович',
                            textInputAction: TextInputAction.next,
                            keyboardType: TextInputType.text,
                          ),
                          SizedBox(height: 14 * s),
                          AuthTextField(
                            label: 'Рабочая почта',
                            controller: _emailController,
                            hint: 'name@company.ru',
                            textInputAction: TextInputAction.next,
                            keyboardType: TextInputType.emailAddress,
                          ),
                          SizedBox(height: 14 * s),
                          AuthTextField(
                            label: 'Пароль',
                            controller: _passwordController,
                            hint: 'Не менее 8 символов',
                            obscureText: true,
                            textInputAction: TextInputAction.next,
                          ),
                          SizedBox(height: 14 * s),
                          AuthTextField(
                            label: 'Повторите пароль',
                            controller: _confirmPasswordController,
                            hint: 'Повторите пароль',
                            obscureText: true,
                            textInputAction: TextInputAction.done,
                          ),
                          SizedBox(height: 14 * s),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.center,
                            children: [
                              SizedBox(
                                width: 18 * s,
                                height: 18 * s,
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
                              SizedBox(width: 10 * s),
                              Expanded(
                                child: Text(
                                  'Принимаю условия использования и политику данных',
                                  style: AppTypography.regular(
                                    10 * s,
                                    color: AppColors.textSecondary,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                      SizedBox(height: 16 * s),
                      Column(
                        children: [
                          AuthPrimaryButton(
                            label: 'Продолжить',
                            onPressed: _canContinue ? _continue : null,
                          ),
                          SizedBox(height: 12 * s),
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
