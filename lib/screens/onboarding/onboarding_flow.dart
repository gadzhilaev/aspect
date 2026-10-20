import 'package:flutter/material.dart';

import '../../models/onboarding_data.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/auth_widgets.dart';
import '../../widgets/onboarding_widgets.dart';
import '../main/main_shell.dart';
import 'business_type_screen.dart';
import 'company_search_screen.dart';
import 'company_verify_screen.dart';
import 'countries_screen.dart';
import 'locations_screen.dart';
import 'products_screen.dart';
import 'profile_review_screen.dart';

/// Shared chrome (back, progress, logo, bottom CTA) with sliding step content.
class OnboardingFlow extends StatefulWidget {
  const OnboardingFlow({super.key, required this.data});

  final OnboardingData data;

  @override
  State<OnboardingFlow> createState() => _OnboardingFlowState();
}

class _OnboardingFlowState extends State<OnboardingFlow> {
  static const _pageCount = 7;

  final _pageController = PageController();
  int _step = 0;

  /// When set, Continue/Back returns here instead of adjacent step (edit from review).
  int? _returnStep;

  String _buttonLabel = 'Продолжить';
  String? _footerHint;
  VoidCallback? _onContinue;

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _bindFooter({
    required String label,
    String? hint,
    VoidCallback? onPressed,
  }) {
    if (!mounted) return;
    setState(() {
      _buttonLabel = label;
      _footerHint = hint;
      _onContinue = onPressed;
    });
  }

  Future<void> _goTo(int step) async {
    if (step < 0 || step >= _pageCount) return;
    setState(() => _step = step);
    await _pageController.animateToPage(
      step,
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeOutCubic,
    );
  }

  void _next() {
    if (_returnStep != null) {
      final target = _returnStep!;
      _returnStep = null;
      _goTo(target);
      return;
    }
    _goTo(_step + 1);
  }

  void _back() {
    if (_returnStep != null) {
      final target = _returnStep!;
      _returnStep = null;
      _goTo(target);
      return;
    }
    if (_step == 0) {
      Navigator.of(context).maybePop();
      return;
    }
    _goTo(_step - 1);
  }

  void _editStep(int step) {
    _returnStep = 6;
    _goTo(step);
  }

  Future<void> _finish() async {
    final fullName = widget.data.fullName.trim();
    await SessionStore.saveLogin(userName: fullName);
    final name = firstNameFromFullName(fullName);
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
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(30 * s, 8 * s, 30 * s, 0),
              child: OnboardingChrome(
                step: _step,
                onBack: _back,
              ),
            ),
            Expanded(
              child: PageView(
                controller: _pageController,
                physics: const NeverScrollableScrollPhysics(),
                children: [
                  CompanySearchScreen(
                    data: widget.data,
                    embedded: true,
                    isActive: _step == 0,
                    bindFooter: _bindFooter,
                    onNext: _next,
                  ),
                  CompanyVerifyScreen(
                    data: widget.data,
                    embedded: true,
                    isActive: _step == 1,
                    bindFooter: _bindFooter,
                    onNext: _next,
                  ),
                  BusinessTypeScreen(
                    data: widget.data,
                    embedded: true,
                    isActive: _step == 2,
                    bindFooter: _bindFooter,
                    onNext: _next,
                  ),
                  ProductsScreen(
                    data: widget.data,
                    embedded: true,
                    isActive: _step == 3,
                    bindFooter: _bindFooter,
                    onNext: _next,
                  ),
                  CountriesScreen(
                    data: widget.data,
                    embedded: true,
                    isActive: _step == 4,
                    bindFooter: _bindFooter,
                    onNext: _next,
                  ),
                  LocationsScreen(
                    data: widget.data,
                    embedded: true,
                    isActive: _step == 5,
                    bindFooter: _bindFooter,
                    onNext: _next,
                  ),
                  ProfileReviewScreen(
                    data: widget.data,
                    embedded: true,
                    isActive: _step == 6,
                    bindFooter: _bindFooter,
                    onNext: _finish,
                    onEditStep: _editStep,
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(30 * s, 8 * s, 30 * s, 24 * s),
              child: Column(
                children: [
                  AuthPrimaryButton(
                    label: _buttonLabel,
                    onPressed: _onContinue,
                  ),
                  if (_footerHint != null) ...[
                    SizedBox(height: 12 * s),
                    Text(
                      _footerHint!,
                      textAlign: TextAlign.center,
                      style: AppTypography.regular(
                        13 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
