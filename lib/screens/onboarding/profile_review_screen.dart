import 'package:flutter/material.dart';

import '../../models/onboarding_data.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/onboarding_widgets.dart';
import '../main/main_shell.dart';

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
      label: 'Готово',
      onPressed: _finish,
    );
  }

  String get _userName {
    final parts = widget.data.fullName.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return 'Пользователь';
    return parts.first;
  }

  Future<void> _finish() async {
    if (widget.onNext != null) {
      widget.onNext!();
      return;
    }
    await SessionStore.saveLogin(userName: _userName);
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(
        builder: (_) => MainShell(userName: _userName),
      ),
      (route) => false,
    );
  }

  void _edit(int step) => widget.onEditStep?.call(step);

  String _orDash(String value) => value.trim().isEmpty ? '—' : value;

  String _join(List<String> items) =>
      items.isEmpty ? '—' : items.join(', ');

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final data = widget.data;

    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 6,
          showChrome: !widget.embedded,
          title: 'Проверьте профиль',
        ),
        const SizedBox(height: 24),
        Text(
          'ВАША КОМПАНИЯ',
          style: AppTypography.bold(12, color: AppColors.textSecondary),
        ),
        const SizedBox(height: 10),
        GestureDetector(
          onTap: () => _edit(0),
          behavior: HitTestBehavior.opaque,
          child: CompanyCard(
            name: data.companyName,
            inn: data.companyInn,
            city: data.companyCity,
            industry: data.companyIndustry,
          ),
        ),
        const SizedBox(height: 28),
        _ProfileField(
          label: 'Ваша роль',
          value: _orDash(data.role),
          onEdit: () => _edit(1),
        ),
        _ProfileField(
          label: 'Размер компании',
          value: _orDash(data.companySize),
          onEdit: () => _edit(1),
        ),
        _ProfileField(
          label: 'Чем занимается?',
          value: _orDash(data.businessType),
          onEdit: () => _edit(2),
        ),
        _ProfileField(
          label: 'Направление',
          value: _orDash(data.businessTypeSubtitle),
          onEdit: () => _edit(2),
        ),
        _ProfileField(
          label: 'Что вы производите?',
          value: _join(data.products),
          onEdit: () => _edit(3),
        ),
        _ProfileField(
          label: 'Основной рынок',
          value: _orDash(data.mainMarket),
          onEdit: () => _edit(3),
        ),
        _ProfileField(
          label: 'С какими странами работаете?',
          value: _join(data.countries),
          onEdit: () => _edit(4),
        ),
        _ProfileField(
          label: 'Регионы продаж',
          value: _join(data.salesRegions),
          onEdit: () => _edit(5),
        ),
        _ProfileField(
          label: 'Города',
          value: _join(data.cities),
          onEdit: () => _edit(5),
        ),
      ],
    );

    if (widget.embedded) {
      return SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(30, 16, 30, 16),
        child: body,
      );
    }

    return OnboardingScaffold(
      buttonLabel: 'Готово',
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

  static const _borderColor = Color(0xFFE3E5E3);

  final String label;
  final String value;
  final VoidCallback? onEdit;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 18),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: _borderColor),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: AppTypography.bold(12, color: AppColors.textSecondary),
            ),
            const SizedBox(height: 10),
            Text(
              value,
              style: AppTypography.regular(15, color: AppColors.textPrimary),
            ),
            if (onEdit != null) ...[
              const SizedBox(height: 10),
              Align(
                alignment: Alignment.centerRight,
                child: GestureDetector(
                  onTap: onEdit,
                  behavior: HitTestBehavior.opaque,
                  child: Text(
                    'Изменить',
                    style: AppTypography.bold(
                      12,
                      color: const Color(0xFFD92F37),
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
