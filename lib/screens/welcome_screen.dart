import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/app_colors.dart';

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

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: _WelcomeBody(),
      ),
    );
  }
}

class _WelcomeBody extends StatelessWidget {
  const _WelcomeBody();

  static const _designWidth = 393.0;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final scale = width / _designWidth;

    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(30 * scale, 24 * scale, 30 * scale, 24 * scale),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: SvgPicture.asset(
              'assets/images/welcome_logo.svg',
              width: 64 * scale,
              height: 32 * scale,
            ),
          ),
          SizedBox(height: 28 * scale),
          Text.rich(
            TextSpan(
              style: TextStyle(
                fontSize: 28 * scale,
                height: 1.15,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
                letterSpacing: -0.4,
              ),
              children: const [
                TextSpan(text: 'Перемены именно для\n'),
                TextSpan(
                  text: 'вашего бизнеса',
                  style: TextStyle(color: AppColors.brandRed),
                ),
              ],
            ),
          ),
          SizedBox(height: 12 * scale),
          Text(
            'События, которые влияют на вашу компанию. '
            'Последствия и варианты действий – в одном месте.',
            style: TextStyle(
              fontSize: 14 * scale,
              height: 1.35,
              fontWeight: FontWeight.w400,
              color: AppColors.textSecondary,
            ),
          ),
          SizedBox(height: 28 * scale),
          ClipRRect(
            borderRadius: BorderRadius.circular(24 * scale),
            child: AspectRatio(
              aspectRatio: 334 / 188,
              child: Image.asset(
                'assets/images/welcome_hero.png',
                fit: BoxFit.cover,
                alignment: const Alignment(0, -0.18),
              ),
            ),
          ),
          SizedBox(height: 14 * scale),
          Row(
            children: [
              Expanded(child: _InsightCard(scale: scale)),
              SizedBox(width: 16 * scale),
              Expanded(child: _RisksCard(scale: scale)),
            ],
          ),
          SizedBox(height: 36 * scale),
          SizedBox(
            height: 56 * scale,
            child: FilledButton(
              onPressed: () {},
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.brandRed,
                foregroundColor: AppColors.surface,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(28 * scale),
                ),
                textStyle: TextStyle(
                  fontSize: 16 * scale,
                  fontWeight: FontWeight.w600,
                ),
              ),
              child: const Text('Создать аккаунт'),
            ),
          ),
          SizedBox(height: 18 * scale),
          Center(
            child: Text.rich(
              TextSpan(
                style: TextStyle(
                  fontSize: 14 * scale,
                  color: AppColors.textSecondary,
                ),
                children: [
                  const TextSpan(text: 'Уже есть аккаунт? '),
                  WidgetSpan(
                    alignment: PlaceholderAlignment.baseline,
                    baseline: TextBaseline.alphabetic,
                    child: GestureDetector(
                      onTap: () {},
                      child: Text(
                        'Войти',
                        style: TextStyle(
                          fontSize: 14 * scale,
                          fontWeight: FontWeight.w600,
                          color: AppColors.brandRed,
                          decoration: TextDecoration.underline,
                          decorationColor: AppColors.brandRed,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _InsightCard extends StatelessWidget {
  const _InsightCard({required this.scale});

  final double scale;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 134 * scale,
      padding: EdgeInsets.fromLTRB(16 * scale, 16 * scale, 16 * scale, 14 * scale),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(24 * scale),
        border: Border.all(
          color: Colors.black.withValues(alpha: 0.12),
          width: 0.5,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 12 * scale,
            offset: Offset(-1 * scale, 6 * scale),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Персональные\nинсайты',
            style: TextStyle(
              fontSize: 15 * scale,
              height: 1.2,
              fontWeight: FontWeight.w700,
              color: AppColors.brandRed,
            ),
          ),
          const Spacer(),
          Row(
            children: [
              Icon(
                Icons.auto_awesome,
                color: AppColors.brandRed,
                size: 28 * scale,
              ),
              SizedBox(width: 6 * scale),
              Container(
                width: 10 * scale,
                height: 10 * scale,
                decoration: const BoxDecoration(
                  color: AppColors.brandRed,
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _RisksCard extends StatelessWidget {
  const _RisksCard({required this.scale});

  final double scale;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 134 * scale,
      padding: EdgeInsets.fromLTRB(16 * scale, 16 * scale, 16 * scale, 14 * scale),
      decoration: BoxDecoration(
        color: AppColors.brandRed,
        borderRadius: BorderRadius.circular(24 * scale),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Риски и\nвозможности',
            style: TextStyle(
              fontSize: 15 * scale,
              height: 1.2,
              fontWeight: FontWeight.w700,
              color: AppColors.surface,
            ),
          ),
          const Spacer(),
          Align(
            alignment: Alignment.bottomRight,
            child: Icon(
              Icons.insights_outlined,
              color: AppColors.surface.withValues(alpha: 0.9),
              size: 36 * scale,
            ),
          ),
        ],
      ),
    );
  }
}
