import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_client.dart';
import '../api/api_exception.dart';
import '../api/auth_api.dart';
import '../l10n/app_localizations.dart';
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
  bool _busy = false;
  String? _error;
  bool _emailFieldError = false;

  bool get _canContinue =>
      !_busy &&
      _nameController.text.trim().isNotEmpty &&
      _emailController.text.trim().isNotEmpty &&
      _passwordController.text.length >= 8 &&
      _confirmPasswordController.text == _passwordController.text &&
      _acceptedTerms;

  @override
  void initState() {
    super.initState();
    SystemChrome.setSystemUIOverlayStyle(AppColors.systemOverlay);
    for (final c in [
      _nameController,
      _emailController,
      _passwordController,
      _confirmPasswordController,
    ]) {
      c.addListener(_onFormChanged);
    }
  }

  void _onFormChanged() {
    if (_error != null || _emailFieldError) {
      setState(() {
        _error = null;
        _emailFieldError = false;
      });
    } else {
      setState(() {});
    }
  }

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

  bool _isEmailConflict(ApiException e) {
    final code = e.code.toUpperCase();
    if (code == 'CONFLICT') return true;
    final msg = e.message.toLowerCase();
    return msg.contains('уже существует') ||
        msg.contains('already') ||
        msg.contains('занят');
  }

  Future<void> _continue() async {
    if (!_canContinue) return;
    setState(() {
      _busy = true;
      _error = null;
      _emailFieldError = false;
    });
    final data = OnboardingData(
      email: _emailController.text.trim(),
      fullName: _nameController.text.trim(),
      password: _passwordController.text,
    );
    try {
      final res = await AuthApi.instance.register(
        email: data.email,
        password: data.password,
        displayName: data.fullName,
      );
      final details = res['details'];
      String? demoCode;
      if (details is Map) {
        demoCode = details['demo_code']?.toString();
      }
      if (!mounted) return;
      Navigator.of(context).push(
        AppPageRoute<void>(
          builder: (_) => CodeConfirmScreen(
            data: data,
            demoCodeHint: demoCode,
          ),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _emailFieldError = _isEmailConflict(e);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = ApiClient.isNetworkFailure(e)
            ? ApiClient.networkUnavailable(e).message
            : context.l10n.loginFailedGeneric;
        _emailFieldError = false;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
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
                            l10n.createAccount,
                            style: AppTypography.medium(
                              24 * s,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          SizedBox(height: 4 * s),
                          Text(
                            l10n.registerSubtitle,
                            style: AppTypography.regular(
                              12 * s,
                              color: AppColors.textSecondary,
                            ),
                          ),
                          if (_error != null) ...[
                            SizedBox(height: 8 * s),
                            Text(
                              _error!,
                              textAlign: TextAlign.center,
                              style: AppTypography.regular(
                                12 * s,
                                color: AppColors.brandRed,
                              ),
                            ),
                          ],
                          SizedBox(height: 22 * s),
                          AuthTextField(
                            // Не TextInputType.name / AutofillHints.name:
                            // на iOS они часто держат клавиатуру в нижнем регистре.
                            key: const ValueKey('register_fio'),
                            label: l10n.fullName,
                            controller: _nameController,
                            hint: l10n.fullNameHint,
                            textInputAction: TextInputAction.next,
                            keyboardType: TextInputType.text,
                            textCapitalization: TextCapitalization.words,
                            autocorrect: true,
                            enableSuggestions: true,
                          ),
                          SizedBox(height: 14 * s),
                          AuthTextField(
                            label: l10n.workEmail,
                            controller: _emailController,
                            hint: l10n.emailHint,
                            textInputAction: TextInputAction.next,
                            keyboardType: TextInputType.emailAddress,
                            hasError: _emailFieldError,
                          ),
                          SizedBox(height: 14 * s),
                          AuthTextField(
                            label: l10n.password,
                            controller: _passwordController,
                            hint: l10n.passwordMin8Hint,
                            obscureText: true,
                            textInputAction: TextInputAction.next,
                          ),
                          SizedBox(height: 14 * s),
                          AuthTextField(
                            label: l10n.confirmPassword,
                            controller: _confirmPasswordController,
                            hint: l10n.confirmPassword,
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
                                  side: BorderSide(
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
                                  l10n.acceptTerms,
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
                            label: l10n.continueAction,
                            onPressed: _canContinue ? _continue : null,
                          ),
                          SizedBox(height: 12 * s),
                          AuthFooterLink(
                            prefix: l10n.alreadyHaveAccount,
                            action: l10n.signIn,
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
