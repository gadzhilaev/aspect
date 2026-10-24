import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../l10n/app_localizations.dart';
import '../models/onboarding_data.dart';
import '../navigation/app_page_route.dart';
import '../navigation/enter_main.dart';
import '../services/session_store.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';
import '../widgets/alfa_business_mark.dart';
import '../widgets/auth_widgets.dart';
import 'alfa_business_demo_screen.dart';
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
  final _scrollController = ScrollController();
  bool _keyboardWasOpen = false;

  @override
  void initState() {
    super.initState();
    SystemChrome.setSystemUIOverlayStyle(AppColors.systemOverlay);
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _scrollController.dispose();
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
    final defaultUserName = context.l10n.defaultUserName;
    final existing = await SessionStore.loadProfile();
    final data = existing ?? OnboardingData();
    data.email = _emailController.text.trim();
    data.password = _passwordController.text;
    if (data.fullName.trim().isEmpty) {
      final local = data.email.split('@').first.trim();
      data.fullName = local.isEmpty ? defaultUserName : local;
    }
    await SessionStore.finishRegistration(data);
    if (!mounted) return;
    await enterMainApp(
      context,
      userName: firstNameFromFullName(data.fullName),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final keyboardOpen = MediaQuery.viewInsetsOf(context).bottom > 0;
    final showBack = widget.showBackButton;

    if (_keyboardWasOpen && !keyboardOpen) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !_scrollController.hasClients) return;
        _scrollController.jumpTo(0);
      });
    }
    _keyboardWasOpen = keyboardOpen;

    return Scaffold(
      backgroundColor: AppColors.surface,
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        bottom: false,
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              controller: _scrollController,
              physics: keyboardOpen
                  ? const AlwaysScrollableScrollPhysics(
                      parent: BouncingScrollPhysics(),
                    )
                  : const NeverScrollableScrollPhysics(),
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
                        l10n.loginTitle,
                        style: AppTypography.medium(
                          22.5 * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: 4 * s),
                      Text(
                        l10n.loginSubtitle,
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
                        label: l10n.workEmail,
                        controller: _emailController,
                        autoScrollOnFocus: false,
                        hint: l10n.emailHint,
                        textInputAction: TextInputAction.next,
                        keyboardType: TextInputType.emailAddress,
                      ),
                      SizedBox(height: 16 * s),
                      AuthTextField(
                        label: l10n.password,
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
                            l10n.forgotPassword,
                            style: AppTypography.bold(
                              13 * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                        ),
                      ),
                      SizedBox(height: 12 * s),
                      AuthPrimaryButton(
                        label: l10n.signIn,
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
                                l10n.demoLoginVia,
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
                        prefix: l10n.noAccount,
                        action: l10n.registerAction,
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
