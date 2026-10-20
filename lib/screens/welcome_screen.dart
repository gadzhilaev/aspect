import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../navigation/app_page_route.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import 'login_screen.dart';
import 'register_screen.dart';

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key});

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
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

  void _openRegister() {
    Navigator.of(context).push(
      AppPageRoute<void>(builder: (_) => const RegisterScreen()),
    );
  }

  void _openLogin() {
    Navigator.of(context).push(
      AppPageRoute<void>(builder: (_) => const LoginScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(30, 52, 30, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Center(
                        child: SvgPicture.asset(
                          'assets/images/welcome_logo.svg',
                          height: 32,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Text.rich(
                        TextSpan(
                          style: AppTypography.medium(
                            24.83,
                            color: AppColors.textPrimary,
                          ),
                          children: [
                            const TextSpan(text: 'Перемены именно для\n'),
                            TextSpan(
                              text: 'вашего бизнеса',
                              style: AppTypography.medium(
                                24.83,
                                color: AppColors.brandRed,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'События, которые влияют на вашу компанию. '
                        'Последствия и варианты действий - в одном месте.',
                        style: AppTypography.regular(
                          12.7,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      const SizedBox(height: 20),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(24),
                        child: SizedBox(
                          height: 188,
                          width: double.infinity,
                          child: Image.asset(
                            'assets/images/welcome_hero.png',
                            fit: BoxFit.cover,
                            alignment: const Alignment(0, -0.18),
                          ),
                        ),
                      ),
                      const SizedBox(height: 14),
                      const Row(
                        children: [
                          Expanded(child: _InsightCard()),
                          SizedBox(width: 16),
                          Expanded(child: _RisksCard()),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                height: 52,
                child: FilledButton(
                  onPressed: _openRegister,
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.brandRed,
                    foregroundColor: AppColors.surface,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                    textStyle: AppTypography.bold(
                      16,
                      color: AppColors.surface,
                    ),
                  ),
                  child: const Text(
                    'Создать аккаунт',
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Center(
                child: Text.rich(
                  TextSpan(
                    style: AppTypography.regular(
                      13,
                      color: AppColors.textSecondary,
                    ),
                    children: [
                      const TextSpan(text: 'Уже есть аккаунт? '),
                      WidgetSpan(
                        alignment: PlaceholderAlignment.baseline,
                        baseline: TextBaseline.alphabetic,
                        child: GestureDetector(
                          onTap: _openLogin,
                          child: Text(
                            'Войти',
                            style: AppTypography.regular(
                              13,
                              color: AppColors.brandRed,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InsightCard extends StatelessWidget {
  const _InsightCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 134,
      clipBehavior: Clip.hardEdge,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: Colors.black.withValues(alpha: 0.12),
          width: 0.5,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 12,
            offset: const Offset(-1, 6),
          ),
        ],
      ),
      child: Stack(
        children: [
          Positioned(
            top: 16,
            left: 16,
            right: 16,
            child: Text(
              'Персональные\nинсайты',
              style: AppTypography.medium(
                14.85,
                color: AppColors.brandRed,
              ),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: Center(
              child: SvgPicture.asset(
                'assets/images/icon_key_insight.svg',
                width: 83,
                height: 83,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RisksCard extends StatelessWidget {
  const _RisksCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 134,
      clipBehavior: Clip.hardEdge,
      decoration: BoxDecoration(
        color: AppColors.brandRed,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Stack(
        children: [
          Positioned(
            top: 16,
            left: 16,
            right: 16,
            child: Text(
              'Риски и\nвозможности',
              style: AppTypography.medium(
                14.85,
                color: AppColors.surface,
              ),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 18,
            child: Center(
              child: SvgPicture.asset(
                'assets/images/icon_risks_opportunities.svg',
                width: 64,
                height: 64,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
