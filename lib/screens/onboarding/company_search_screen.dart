import 'package:flutter/material.dart';

import '../../api/api_exception.dart';
import '../../api/companies_api.dart';
import '../../l10n/app_localizations.dart';
import '../../models/onboarding_data.dart';
import '../../services/auth_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/auth_widgets.dart';
import '../../widgets/onboarding_widgets.dart';

class CompanySearchScreen extends StatefulWidget {
  const CompanySearchScreen({
    super.key,
    required this.data,
    this.embedded = false,
    this.isActive = true,
    this.bindFooter,
    this.onNext,
  });

  final OnboardingData data;
  final bool embedded;
  final bool isActive;
  final OnboardingFooterBinder? bindFooter;
  final VoidCallback? onNext;

  @override
  State<CompanySearchScreen> createState() => _CompanySearchScreenState();
}

class _CompanySearchScreenState extends State<CompanySearchScreen>
    with AutomaticKeepAliveClientMixin {
  late final TextEditingController _queryController;
  final _queryFocus = FocusNode();
  bool _loading = false;
  String? _error;
  String? _lookupId;
  List<Map<String, dynamic>> _candidates = [];
  String? _selectedCandidateId;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _queryController = TextEditingController(text: widget.data.companyQuery);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.isActive) _syncFooter();
    });
  }

  @override
  void didUpdateWidget(covariant CompanySearchScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive) _syncFooter();
  }

  @override
  void dispose() {
    _queryController.dispose();
    _queryFocus.dispose();
    super.dispose();
  }

  void _syncFooter() {
    widget.bindFooter?.call(
      label: context.l10n.continueAction,
      onPressed: _selectedCandidateId == null || _loading ? null : _confirm,
    );
  }

  Future<void> _search() async {
    final q = _queryController.text.trim();
    if (q.isEmpty || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _candidates = [];
      _selectedCandidateId = null;
      _lookupId = null;
    });
    _syncFooter();
    try {
      // ИНН: только цифры 10/12.
      final digits = q.replaceAll(RegExp(r'\D'), '');
      final inn = (digits.length == 10 || digits.length == 12) ? digits : q;
      final res = await CompaniesApi.instance.lookupByInn(inn);
      final status = res['status']?.toString() ?? '';
      if (status == 'not_configured') {
        // Fallback: ручное создание без реестра.
        setState(() {
          _error =
              'Справочник ИНН не настроен на сервере. Можно продолжить с введённым названием.';
          widget.data.companyQuery = q;
          widget.data.companyName = q;
          _selectedCandidateId = '__manual__';
        });
        _syncFooter();
        return;
      }
      if (status == 'not_found') {
        setState(() => _error = 'Компания не найдена');
        return;
      }
      final list = (res['candidates'] as List?) ?? const [];
      setState(() {
        _lookupId = res['lookup_id']?.toString();
        _candidates = [
          for (final c in list) Map<String, dynamic>.from(c as Map),
        ];
        if (_candidates.length == 1) {
          _selectedCandidateId = _candidates.first['candidate_id']?.toString();
        }
      });
      widget.data.companyQuery = q;
      _syncFooter();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) {
        setState(() => _loading = false);
        _syncFooter();
      }
    }
  }

  Future<void> _confirm() async {
    if (_selectedCandidateId == null) return;
    setState(() => _loading = true);
    try {
      if (_selectedCandidateId == '__manual__') {
        final created = await CompaniesApi.instance.createCompany(
          name: widget.data.companyName.trim().isEmpty
              ? _queryController.text.trim()
              : widget.data.companyName.trim(),
          industry: widget.data.companyIndustry,
          taxId: widget.data.companyInn,
        );
        final id = created['id']?.toString() ??
            created['company']?['id']?.toString() ??
            '';
        final name = created['name']?.toString() ??
            created['company']?['name']?.toString() ??
            widget.data.companyName;
        if (id.isNotEmpty) {
          await AuthStore.setCompany(companyId: id, companyName: name);
        }
        widget.data.companyName = name;
      } else {
        final res = await CompaniesApi.instance.confirmLookup(
          lookupId: _lookupId!,
          candidateId: _selectedCandidateId!,
        );
        final company = Map<String, dynamic>.from(
          (res['company'] as Map?) ?? const {},
        );
        final id = company['id']?.toString() ?? '';
        final name = company['name']?.toString() ?? '';
        final inn = company['tax_id']?.toString() ?? '';
        if (id.isNotEmpty) {
          await AuthStore.setCompany(companyId: id, companyName: name);
        }
        widget.data
          ..companyName = name
          ..companyInn = inn
          ..companyIndustry =
              res['suggested_industry']?.toString() ?? widget.data.companyIndustry;
      }
      widget.onNext?.call();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) {
        setState(() => _loading = false);
        _syncFooter();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final s = context.scale;
    final l10n = context.l10n;

    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppColors.screenPadding * s),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            l10n.search,
            style: AppTypography.bold(22 * s, color: AppColors.textInput),
          ),
          SizedBox(height: 8 * s),
          Text(
            'Введите ИНН (10 или 12 цифр)',
            style: AppTypography.regular(13 * s, color: AppColors.textMuted),
          ),
          SizedBox(height: 16 * s),
          AuthTextField(
            label: 'ИНН',
            controller: _queryController,
            focusNode: _queryFocus,
            keyboardType: TextInputType.number,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _search(),
          ),
          SizedBox(height: 12 * s),
          AuthPrimaryButton(
            label: _loading ? '…' : l10n.search,
            onPressed: _loading ? null : _search,
          ),
          if (_error != null) ...[
            SizedBox(height: 12 * s),
            Text(
              _error!,
              style: AppTypography.regular(13 * s, color: AppColors.brandRed),
            ),
          ],
          SizedBox(height: 16 * s),
          Expanded(
            child: ListView.separated(
              itemCount: _candidates.length,
              separatorBuilder: (_, _) => SizedBox(height: 8 * s),
              itemBuilder: (context, i) {
                final c = _candidates[i];
                final id = c['candidate_id']?.toString() ?? '$i';
                final selected = _selectedCandidateId == id;
                final title =
                    c['name_short']?.toString() ?? c['name_full']?.toString() ?? '—';
                final inn = c['inn']?.toString() ?? '';
                final region = c['region']?.toString() ?? '';
                return InkWell(
                  onTap: () {
                    setState(() => _selectedCandidateId = id);
                    _syncFooter();
                  },
                  borderRadius: BorderRadius.circular(14 * s),
                  child: Container(
                    padding: EdgeInsets.all(14 * s),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceRaised,
                      borderRadius: BorderRadius.circular(14 * s),
                      border: Border.all(
                        color: selected ? AppColors.brandRed : AppColors.border,
                        width: selected ? 1.5 : 1,
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: AppTypography.bold(
                            15 * s,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        SizedBox(height: 4 * s),
                        Text(
                          [if (inn.isNotEmpty) 'ИНН $inn', if (region.isNotEmpty) region]
                              .join(' · '),
                          style: AppTypography.regular(
                            12 * s,
                            color: AppColors.textMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
