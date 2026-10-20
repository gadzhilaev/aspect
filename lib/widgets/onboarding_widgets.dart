import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import 'auth_widgets.dart';

class OnboardingProgress extends StatelessWidget {
  const OnboardingProgress({
    super.key,
    required this.currentStep,
    this.totalSteps = 7,
  });

  final int currentStep;
  final int totalSteps;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(totalSteps, (index) {
        final isActive = index <= currentStep;
        final isCurrent = index == currentStep;
        return Container(
          margin: EdgeInsets.only(right: index == totalSteps - 1 ? 0 : 4),
          width: isCurrent ? 28 : 13,
          height: 8,
          decoration: BoxDecoration(
            color: isActive ? AppColors.brandRed : const Color(0xFFD9D9D9),
            borderRadius: BorderRadius.circular(4),
          ),
        );
      }),
    );
  }
}

class OnboardingChrome extends StatelessWidget {
  const OnboardingChrome({
    super.key,
    required this.step,
    this.onBack,
  });

  final int step;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        SizedBox(
          height: 24,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: AuthBackButton(onPressed: onBack),
              ),
              OnboardingProgress(currentStep: step),
            ],
          ),
        ),
      ],
    );
  }
}

class OnboardingTitle extends StatelessWidget {
  const OnboardingTitle({
    super.key,
    required this.title,
    this.subtitle,
  });

  final String title;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          title,
          style: AppTypography.medium(28, color: AppColors.textPrimary),
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 4),
          Text(
            subtitle!,
            style: AppTypography.regular(
              14,
              color: const Color(0xFF65717A),
            ),
          ),
        ],
      ],
    );
  }
}

class OnboardingHeader extends StatelessWidget {
  const OnboardingHeader({
    super.key,
    required this.step,
    required this.title,
    this.subtitle,
    this.showChrome = true,
    this.onBack,
  });

  final int step;
  final String title;
  final String? subtitle;
  final bool showChrome;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (showChrome) ...[
          OnboardingChrome(step: step, onBack: onBack),
          const SizedBox(height: 16),
        ],
        const Center(child: AuthLogo()),
        const SizedBox(height: 16),
        OnboardingTitle(title: title, subtitle: subtitle),
      ],
    );
  }
}

typedef OnboardingFooterBinder = void Function({
  required String label,
  String? hint,
  VoidCallback? onPressed,
});

class CompanyCard extends StatelessWidget {
  const CompanyCard({
    super.key,
    required this.name,
    required this.inn,
    required this.city,
    required this.industry,
    this.selected = false,
    this.onTap,
  });

  final String name;
  final String inn;
  final String city;
  final String industry;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 16,
            spreadRadius: 0,
            offset: const Offset(0, 4),
          ),
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 6,
            spreadRadius: 0,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: Material(
        color: AppColors.surface,
        elevation: 0,
        shadowColor: Colors.transparent,
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(16),
          child: Ink(
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: selected
                    ? AppColors.brandRed
                    : const Color(0x3D000000),
                width: selected ? 1 : 0.1,
              ),
            ),
            child: IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Container(
                    width: 3,
                    margin: const EdgeInsets.fromLTRB(14, 14, 0, 14),
                    decoration: BoxDecoration(
                      color: AppColors.brandRed,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(12, 14, 16, 14),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            name,
                            style: AppTypography.bold(
                              16,
                              color: AppColors.brandRed,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'ИНН $inn • $city',
                            style: AppTypography.regular(
                              13,
                              color: const Color(0xFF65717A),
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            industry,
                            style: AppTypography.regular(
                              13,
                              color: const Color(0xFF65717A),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class SelectableOptionTile extends StatelessWidget {
  const SelectableOptionTile({
    super.key,
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected
          ? AppColors.brandRed.withValues(alpha: 0.06)
          : AppColors.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 14, 14, 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: selected
                  ? AppColors.brandRed
                  : Colors.black.withValues(alpha: 0.08),
            ),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textInput,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: const TextStyle(
                        fontSize: 13,
                        color: Color(0xFF65717A),
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                selected
                    ? Icons.radio_button_checked
                    : Icons.radio_button_off,
                color: selected
                    ? AppColors.brandRed
                    : AppColors.textSecondary,
                size: 22,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class RemovableChipList extends StatelessWidget {
  const RemovableChipList({
    super.key,
    required this.items,
    required this.onRemove,
  });

  final List<String> items;
  final ValueChanged<int> onRemove;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (var i = 0; i < items.length; i++) ...[
          if (i > 0) const Divider(height: 1, color: AppColors.divider),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    items[i],
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textInput,
                    ),
                  ),
                ),
                GestureDetector(
                  onTap: () => onRemove(i),
                  child: const Icon(
                    Icons.close,
                    size: 18,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class AddLinkButton extends StatelessWidget {
  const AddLinkButton({
    super.key,
    required this.label,
    required this.onTap,
  });

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: TextButton(
        onPressed: onTap,
        style: TextButton.styleFrom(
          foregroundColor: AppColors.brandRed,
          padding: EdgeInsets.zero,
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        child: Text(
          label,
          style: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

class OnboardingScaffold extends StatelessWidget {
  const OnboardingScaffold({
    super.key,
    required this.body,
    required this.buttonLabel,
    required this.onContinue,
    this.footerHint,
  });

  final Widget body;
  final String buttonLabel;
  final VoidCallback? onContinue;
  final String? footerHint;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(30, 8, 30, 16),
                child: body,
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(30, 8, 30, 24),
              child: Column(
                children: [
                  AuthPrimaryButton(
                    label: buttonLabel,
                    onPressed: onContinue,
                  ),
                  if (footerHint != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      footerHint!,
                      textAlign: TextAlign.center,
                      style: AppTypography.regular(
                        13,
                        color: const Color(0xFF65717A),
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
