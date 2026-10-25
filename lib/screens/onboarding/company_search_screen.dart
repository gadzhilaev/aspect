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
    if (widget.isActive &&
        (!oldWidget.isActive ||
            widget.bindFooter != oldWidget.bindFooter)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && widget.isActive) _syncFooter();
      });
    }
  }

  @override
  void dispose() {
    _queryController.dispose();
    _queryFocus.dispose();
    super.dispose();
  }

  bool get _canContinue =>
      !_loading &&
      _selectedCandidateId != null &&
      _selectedCandidateId != '__manual__';

  /// Одна кнопка в футере: сначала «Поиск», после выбора кандидата — «Продолжить».
  void _syncFooter() {
    final l10n = context.l10n;
    if (_canContinue) {
      widget.bindFooter?.call(
        label: l10n.continueAction,
        onPressed: _confirm,
      );
      return;
    }
    widget.bindFooter?.call(
      label: _loading ? '…' : l10n.search,
      onPressed: _loading ? null : _search,
    );
  }

  Future<void> _search() async {
    FocusManager.instance.primaryFocus?.unfocus();
    final q = _queryController.text.trim();
    if (_loading) return;
    final digits = q.replaceAll(RegExp(r'\D'), '');
    final onlyInn = digits.isNotEmpty &&
        digits == q.replaceAll(RegExp(r'\s'), '') &&
        (digits.length == 10 || digits.length == 12);
    if (q.length < 2 && !onlyInn) {
      setState(() {
        _error = 'Введите ИНН (10 или 12 цифр) или название компании';
        _candidates = [];
        _selectedCandidateId = null;
        _lookupId = null;
      });
      _syncFooter();
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _candidates = [];
      _selectedCandidateId = null;
      _lookupId = null;
    });
    _syncFooter();
    try {
      final res = await CompaniesApi.instance.lookupCompany(q);
      final status = res['status']?.toString() ?? '';
      if (status == 'not_configured') {
        setState(() {
          _error =
              'Поиск компаний не настроен: на сервере нет DADATA_API_KEY. Ключ — в кабинете dadata.ru → API.';
          _candidates = [];
          _selectedCandidateId = null;
        });
        _syncFooter();
        return;
      }
      if (status == 'not_found') {
        setState(() {
          _error = onlyInn
              ? 'Компания с таким ИНН не найдена'
              : 'Компания по запросу не найдена';
          _candidates = [];
          _selectedCandidateId = null;
        });
        _syncFooter();
        return;
      }
      final list = (res['candidates'] as List?) ?? const [];
      setState(() {
        _lookupId = res['lookup_id']?.toString();
        _candidates = [
          for (final c in list) Map<String, dynamic>.from(c as Map),
        ];
        // Не выбираем автоматически — только по тапу.
        _selectedCandidateId = null;
        if (_candidates.isEmpty) {
          _error = onlyInn
              ? 'Компания с таким ИНН не найдена'
              : 'Компания по запросу не найдена';
        }
      });
      widget.data.companyQuery = q;
      _syncFooter();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
      _syncFooter();
    } catch (e) {
      setState(() => _error = e.toString());
      _syncFooter();
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
      if (_lookupId == null || _selectedCandidateId == null) return;
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
      Map<String, dynamic>? selected;
      for (final c in _candidates) {
        if ((c['candidate_id']?.toString() ?? '') == _selectedCandidateId) {
          selected = c;
          break;
        }
      }
      final okvedName = selected?['okved_name']?.toString().trim() ?? '';
      final address = selected?['address']?.toString().trim() ?? '';
      final city = (selected?['city']?.toString().trim().isNotEmpty == true)
          ? selected!['city'].toString().trim()
          : (selected?['region']?.toString().trim() ??
              company['hq_region']?.toString().trim() ??
              '');
      // В профиле храним полный юр. адрес, иначе город.
      final location = address.isNotEmpty
          ? address
          : (city.isNotEmpty ? city : widget.data.companyCity);
      widget.data
        ..companyName = name
        ..companyInn = inn
        ..companyCity = location
        ..companyIndustry = okvedName.isNotEmpty
            ? okvedName
            : (res['suggested_industry']?.toString() ??
                widget.data.companyIndustry);
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

    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppColors.screenPadding * s),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Как на остальных шагах OnboardingHeader: логотип под прогрессом.
          if (widget.embedded) ...[
            SizedBox(height: 24 * s),
            const Center(child: AuthLogo()),
            SizedBox(height: 24 * s),
          ],
          Text(
            'Ваша компания',
            style: AppTypography.medium(28 * s, color: AppColors.textPrimary),
          ),
          SizedBox(height: 8 * s),
          Text(
            'Найдите компанию по названию или ИНН. Мы подставим открытые данные для проверки.',
            style: AppTypography.regular(14 * s, color: AppColors.textMuted),
          ),
          SizedBox(height: 16 * s),
          AuthTextField(
            label: 'Название компании или ИНН',
            controller: _queryController,
            focusNode: _queryFocus,
            // Полная клавиатура: и название, и ИНН (не number/phone).
            keyboardType: TextInputType.text,
            textCapitalization: TextCapitalization.sentences,
            textInputAction: TextInputAction.search,
            autocorrect: false,
            enableSuggestions: false,
            onSubmitted: (_) => _search(),
            onChanged: (_) {
              // Смена запроса сбрасывает выбор — снова только «Поиск».
              if (_selectedCandidateId != null || _candidates.isNotEmpty) {
                setState(() {
                  _candidates = [];
                  _selectedCandidateId = null;
                  _lookupId = null;
                  _error = null;
                });
                _syncFooter();
              }
            },
          ),
          if (_error != null) ...[
            SizedBox(height: 12 * s),
            Text(
              _error!,
              style: AppTypography.regular(13 * s, color: AppColors.brandRed),
            ),
          ],
          SizedBox(height: 16 * s),
          // Список только между полем и кнопкой «Поиск» (footer снаружи).
          Expanded(
            child: ClipRect(
              child: ListView.separated(
                padding: EdgeInsets.fromLTRB(4 * s, 2 * s, 4 * s, 12 * s),
                itemCount: _candidates.length,
                separatorBuilder: (_, _) => SizedBox(height: 14 * s),
                itemBuilder: (context, i) {
                final c = _candidates[i];
                final id = c['candidate_id']?.toString() ?? '$i';
                final selected = _selectedCandidateId == id;
                final title =
                    c['name_short']?.toString() ?? c['name_full']?.toString() ?? '—';
                final inn = c['inn']?.toString() ?? '';
                final addressRaw = c['address']?.toString().trim() ?? '';
                final cityRaw = c['city']?.toString().trim() ?? '';
                final regionRaw = c['region']?.toString().trim() ?? '';
                final address = addressRaw.isNotEmpty
                    ? addressRaw
                    : (cityRaw.isNotEmpty ? cityRaw : regionRaw);
                final industry = c['okved_name']?.toString().trim() ?? '';
                return CompanyCard(
                  name: title,
                  inn: inn,
                  address: address,
                  industry: industry,
                  selected: selected,
                  onTap: () {
                    setState(() => _selectedCandidateId = id);
                    _syncFooter();
                  },
                );
              },
              ),
            ),
          ),
        ],
      ),
    );
  }
}
