import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../models/onboarding_data.dart';
import '../../navigation/enter_main.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/onboarding_widgets.dart';

class ProfileReviewScreen extends StatefulWidget {
  const ProfileReviewScreen({
    super.key,
    required this.data,
    this.embedded = false,
    this.isActive = true,
    this.bindFooter,
    this.onNext,
    this.onEditStep,
  });

  final OnboardingData data;
  final bool embedded;
  final bool isActive;
  final OnboardingFooterBinder? bindFooter;
  final VoidCallback? onNext;

  /// Opens onboarding step for editing (0…5). Continues back to this screen.
  final ValueChanged<int>? onEditStep;

  @override
  State<ProfileReviewScreen> createState() => _ProfileReviewScreenState();
}

class _ProfileReviewScreenState extends State<ProfileReviewScreen>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncFooter());
  }

  @override
  void didUpdateWidget(covariant ProfileReviewScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {});
          _syncFooter();
        }
      });
    }
  }

  void _syncFooter() {
    widget.bindFooter?.call(
      label: context.l10n.done,
      onPressed: _finish,
    );
  }

  String get _userName => firstNameFromFullName(widget.data.fullName);

  Future<void> _finish() async {
    if (widget.onNext != null) {
      widget.onNext!();
      return;
    }
    await SessionStore.finishRegistration(widget.data);
    if (!mounted) return;
    await enterMainApp(context, userName: _userName);
  }

  void _edit(int step) => widget.onEditStep?.call(step);

  String _orDash(String value, AppLocalizations l10n) =>
      value.trim().isEmpty ? l10n.emptyValueDash : value;

  String _join(List<String> items, AppLocalizations l10n) =>
      items.isEmpty ? l10n.emptyValueDash : items.join(', ');

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final s = context.scale;
    final l10n = context.l10n;
    final data = widget.data;

    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 6,
          showChrome: !widget.embedded,
          title: l10n.onboardingReviewTitle,
        ),
        SizedBox(height: 24 * s),
        Text(
          l10n.onboardingYourCompanySection,
          style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
        ),
        SizedBox(height: 10 * s),
        GestureDetector(
          onTap: () => _edit(0),
          behavior: HitTestBehavior.opaque,
          child: CompanyCard(
            name: data.companyName,
            inn: data.companyInn,
            address: data.companyCity,
            industry: data.companyIndustry,
          ),
        ),
        SizedBox(height: 28 * s),
        _ProfileField(
          label: l10n.onboardingYourRole,
          value: _orDash(data.role, l10n),
          onEdit: () => _edit(1),
        ),
        _ProfileField(
          label: l10n.onboardingCompanySize,
          value: _orDash(data.companySize, l10n),
          onEdit: () => _edit(1),
        ),
        _ProfileField(
          label: l10n.onboardingReviewWhatBusiness,
          value: _orDash(data.businessType, l10n),
          onEdit: () => _edit(2),
        ),
        _ProfileField(
          label: l10n.onboardingReviewDirection,
          value: _orDash(data.businessTypeSubtitle, l10n),
          onEdit: () => _edit(2),
        ),
        _ProfileField(
          label: l10n.onboardingProductsTitle,
          value: _join(data.products, l10n),
          onEdit: () => _edit(3),
        ),
        _ProfileField(
          label: l10n.onboardingMainMarket,
          value: _orDash(data.mainMarket, l10n),
          onEdit: () => _edit(3),
        ),
        _ProfileField(
          label: l10n.onboardingCountriesTitle,
          value: _join(data.countries, l10n),
          onEdit: () => _edit(4),
        ),
        _ProfileField(
          label: l10n.onboardingReviewSalesRegions,
          value: _join(data.salesRegions, l10n),
          onEdit: () => _edit(5),
        ),
        _ProfileField(
          label: l10n.onboardingReviewCities,
          value: _join(data.cities, l10n),
          onEdit: () => _edit(5),
        ),
      ],
    );

    if (widget.embedded) {
      return SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 16 * s, 16 * s),
        child: body,
      );
    }

    return OnboardingScaffold(
      buttonLabel: l10n.done,
      onContinue: _finish,
      body: body,
    );
  }
}

class _ProfileField extends StatelessWidget {
  const _ProfileField({
    required this.label,
    required this.value,
    this.onEdit,
  });

  static Color get _borderColor => AppColors.border;

  final String label;
  final String value;
  final VoidCallback? onEdit;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    return Padding(
      padding: EdgeInsets.only(bottom: 12 * s),
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 16 * s, 18 * s),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16 * s),
          border: Border.all(color: _borderColor),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
            ),
            SizedBox(height: 10 * s),
            Text(
              value,
              style: AppTypography.regular(15 * s, color: AppColors.textPrimary),
            ),
            if (onEdit != null) ...[
              SizedBox(height: 10 * s),
              Align(
                alignment: Alignment.centerRight,
                child: GestureDetector(
                  onTap: onEdit,
                  behavior: HitTestBehavior.opaque,
                  child: Text(
                    l10n.onboardingChange,
                    style: AppTypography.bold(
                      12 * s,
                      color: AppColors.brandRed,
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
