import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';
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
    final s = context.scale;
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(totalSteps, (index) {
        final isActive = index <= currentStep;
        final isCurrent = index == currentStep;
        return Container(
          margin: EdgeInsets.only(right: index == totalSteps - 1 ? 0 : 4 * s),
          width: (isCurrent ? 28 : 13) * s,
          height: 8 * s,
          decoration: BoxDecoration(
            color: isActive ? AppColors.brandRed : AppColors.progressTrack,
            borderRadius: BorderRadius.circular(4 * s),
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
          height: context.ds(24),
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
    final s = context.scale;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          title,
          style: AppTypography.medium(28 * s, color: AppColors.textPrimary),
        ),
        if (subtitle != null) ...[
          SizedBox(height: 4 * s),
          Text(
            subtitle!,
            style: AppTypography.regular(14 * s, color: AppColors.textMuted),
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
    final s = context.scale;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (showChrome) ...[
          OnboardingChrome(step: step, onBack: onBack),
          SizedBox(height: 16 * s),
        ],
        const Center(child: AuthLogo()),
        SizedBox(height: 16 * s),
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
    final s = context.scale;
    final l10n = context.l10n;
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16 * s),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 16 * s,
            offset: Offset(0, 4 * s),
          ),
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 6 * s,
            offset: Offset(0, 1 * s),
          ),
        ],
      ),
      child: Material(
        color: AppColors.surface,
        elevation: 0,
        shadowColor: Colors.transparent,
        borderRadius: BorderRadius.circular(16 * s),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(16 * s),
          child: Ink(
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(16 * s),
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
                    width: 3 * s,
                    margin: EdgeInsets.fromLTRB(14 * s, 14 * s, 0, 14 * s),
                    decoration: BoxDecoration(
                      color: AppColors.brandRed,
                      borderRadius: BorderRadius.circular(2 * s),
                    ),
                  ),
                  Expanded(
                    child: Padding(
                      padding: EdgeInsets.fromLTRB(12 * s, 14 * s, 16 * s, 14 * s),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            name,
                            style: AppTypography.bold(
                              16 * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                          SizedBox(height: 8 * s),
                          Text(
                            '${l10n.innLabel} $inn • $city',
                            style: AppTypography.regular(
                              13 * s,
                              color: AppColors.textMuted,
                            ),
                          ),
                          SizedBox(height: 8 * s),
                          Text(
                            industry,
                            style: AppTypography.regular(
                              13 * s,
                              color: AppColors.textMuted,
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
    final s = context.scale;
    return Material(
      color: selected
          ? AppColors.brandRed.withValues(alpha: 0.06)
          : AppColors.surface,
      borderRadius: BorderRadius.circular(14 * s),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14 * s),
        child: Container(
          padding: EdgeInsets.fromLTRB(16 * s, 14 * s, 14 * s, 14 * s),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14 * s),
            border: Border.all(
              color: selected
                  ? AppColors.brandRedBorderSoft
                  : AppColors.border,
              width: 1,
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
                      style: AppTypography.bold(
                        16 * s,
                        color: AppColors.textInput,
                      ),
                    ),
                    SizedBox(height: 6 * s),
                    Text(
                      subtitle,
                      style: AppTypography.regular(
                        13 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
              _OptionRadio(selected: selected, size: 22 * s),
            ],
          ),
        ),
      ),
    );
  }
}

class _OptionRadio extends StatelessWidget {
  const _OptionRadio({required this.selected, required this.size});

  final bool selected;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: selected ? AppColors.brandRed : AppColors.border,
          width: 1,
        ),
      ),
      child: selected
          ? Center(
              child: Container(
                width: size * 0.55,
                height: size * 0.55,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.brandRed,
                ),
              ),
            )
          : null,
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
    final s = context.scale;
    return Column(
      children: [
        for (var i = 0; i < items.length; i++) ...[
          if (i > 0) Divider(height: 1 * s, color: AppColors.divider),
          Padding(
            padding: EdgeInsets.symmetric(vertical: 12 * s),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    items[i],
                    style: AppTypography.bold(
                      16 * s,
                      color: AppColors.textInput,
                    ),
                  ),
                ),
                GestureDetector(
                  onTap: () => onRemove(i),
                  child: Icon(
                    Icons.close,
                    size: 18 * s,
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
    final s = context.scale;
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
          style: AppTypography.bold(15 * s, color: AppColors.brandRed),
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
    final s = context.scale;
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(16 * s, 8 * s, 16 * s, 16 * s),
                child: body,
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(16 * s, 8 * s, 16 * s, 8 * s),
              child: Column(
                children: [
                  AuthPrimaryButton(
                    label: buttonLabel,
                    onPressed: onContinue,
                  ),
                  if (footerHint != null) ...[
                    SizedBox(height: 8 * s),
                    Text(
                      footerHint!,
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
