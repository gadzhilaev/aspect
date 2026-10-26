import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_client.dart';
import '../api/api_config.dart';
import '../api/api_exception.dart';
import '../api/auth_api.dart';
import '../l10n/app_localizations.dart';
import '../navigation/app_page_route.dart';
import '../navigation/enter_main.dart';
import '../services/session_store.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';
import '../widgets/alfa_business_mark.dart';
import '../widgets/auth_widgets.dart';
import 'alfa_business_demo_screen.dart';
import 'onboarding/onboarding_flow.dart';
import 'register_screen.dart';
import '../models/onboarding_data.dart';

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
  bool _busy = false;
  String? _error;
  bool _fieldsError = false;

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
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _fieldsError = false;
    });
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    try {
      await AuthApi.instance.login(email: email, password: password);
      final me = await AuthApi.instance.refreshMe();
      final display = me['display_name']?.toString() ?? email;
      final companies = (me['companies'] as List?) ?? const [];
      // Реальный API-вход сбрасывает локальный режим Альфа-демо.
      await SessionStore.markAlfaDemo(enabled: false);
      // Локальный профиль для экранов, ещё не переведённых на API.
      final data = (await SessionStore.loadProfile()) ?? OnboardingData();
      data.email = email;
      data.fullName = display;
      data.password = '';
      final jobRole = AuthApi.jobRoleFromMe(me);
      if (jobRole != null) data.role = jobRole;
      if (companies.isNotEmpty) {
        final c = Map<String, dynamic>.from(companies.first as Map);
        data.companyName = c['name']?.toString() ?? data.companyName;
        try {
          await AuthApi.instance.markRegistrationComplete();
        } catch (_) {}
        await SessionStore.finishRegistration(data);
        if (!mounted) return;
        await enterMainApp(
          context,
          userName: firstNameFromFullName(display),
        );
      } else {
        await SessionStore.saveProfile(data);
        await SessionStore.markAuthPendingOnboarding();
        if (!mounted) return;
        Navigator.of(context).pushAndRemoveUntil(
          AppPageRoute<void>(
            builder: (_) => OnboardingFlow(data: data),
          ),
          (_) => false,
        );
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      final display = e.userDisplayMessage;
      unawaited(_reportLoginFailure(
        email: email,
        display: display,
        exception: e,
        stack: StackTrace.current,
        loginUrl: '${ApiConfig.apiV1}/auth/login',
      ));
      setState(() {
        _error = display;
        _fieldsError = true;
        _busy = false;
      });
    } catch (e, st) {
      if (!mounted) return;
      final apiEx = ApiClient.isNetworkFailure(e)
          ? ApiClient.networkUnavailable(e)
          : ApiException(
              statusCode: 0,
              code: 'LOGIN_FAILED',
              message: e.toString(),
              underlyingCause: e.toString(),
            );
      final display = apiEx.userDisplayMessage;
      unawaited(_reportLoginFailure(
        email: email,
        display: display,
        exception: apiEx,
        stack: st,
        loginUrl: '${ApiConfig.apiV1}/auth/login',
      ));
      setState(() {
        _error = display;
        _fieldsError = true;
        _busy = false;
      });
    }
  }

  Future<void> _reportLoginFailure({
    required String email,
    required String display,
    required ApiException exception,
    required StackTrace stack,
    required String loginUrl,
  }) {
    return ApiClient.instance.reportClientError(
      source: ApiClient.clientSource(),
      screen: 'login',
      message: display,
      exceptionType: exception.runtimeType.toString(),
      stack: stack.toString(),
      httpStatus: exception.statusCode == 0 ? null : exception.statusCode,
      httpCode: exception.code,
      url: loginUrl,
      method: 'POST',
      details: {
        if (exception.details != null) 'api_details': exception.details,
        if (exception.underlyingCause != null)
          'underlying_cause': exception.underlyingCause,
      },
      appVersion: ApiConfig.appVersion,
      platform: ApiClient.clientPlatformLabel(),
      deviceInfo: ApiClient.clientDeviceInfo(),
      emailAttempted: email,
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
              physics: const AlwaysScrollableScrollPhysics(
                parent: BouncingScrollPhysics(),
              ),
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
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
                      if (_error != null) ...[
                        SizedBox(height: 16 * s),
                        Text(
                          _error!,
                          textAlign: TextAlign.center,
                          style: AppTypography.regular(
                            13 * s,
                            color: AppColors.brandRed,
                          ),
                        ),
                        SizedBox(height: 12 * s),
                      ] else
                        SizedBox(height: 22 * s),
                      AuthTextField(
                        label: l10n.workEmail,
                        controller: _emailController,
                        autoScrollOnFocus: false,
                        hint: l10n.emailHint,
                        textInputAction: TextInputAction.next,
                        keyboardType: TextInputType.emailAddress,
                        hasError: _fieldsError,
                        onChanged: (_) {
                          if (_error != null || _fieldsError) {
                            setState(() {
                              _error = null;
                              _fieldsError = false;
                            });
                          }
                        },
                      ),
                      SizedBox(height: 16 * s),
                      AuthTextField(
                        label: l10n.password,
                        controller: _passwordController,
                        autoScrollOnFocus: false,
                        obscureText: true,
                        hasError: _fieldsError,
                        onChanged: (_) {
                          if (_error != null || _fieldsError) {
                            setState(() {
                              _error = null;
                              _fieldsError = false;
                            });
                          }
                        },
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
                        onPressed: _busy ? null : _login,
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
