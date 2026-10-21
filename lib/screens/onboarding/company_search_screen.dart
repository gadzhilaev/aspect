import 'package:flutter/material.dart';

import '../../models/onboarding_data.dart';
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
  bool _showResult = false;
  bool _selected = false;

  static const _mockName = 'ООО «СеверПром»';
  static const _mockInn = '7701234567';
  static const _mockCity = 'Москва';
  static const _mockIndustry = 'Производство оборудования';

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _queryController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _syncFooter();
      if (widget.embedded) _queryFocus.requestFocus();
    });
  }

  @override
  void didUpdateWidget(covariant CompanySearchScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _syncFooter();
      });
    }
  }

  @override
  void dispose() {
    _queryController.dispose();
    _queryFocus.dispose();
    super.dispose();
  }

  void _syncFooter() {
    widget.bindFooter?.call(
      label: 'Это моя компания',
      hint:
          'Данные компании можно будет исправить. И дополнить на следующем шаге.',
      onPressed: _selected ? _continue : null,
    );
  }

  void _runSearch([String? value]) {
    final query = (value ?? _queryController.text).trim();
    setState(() {
      _showResult = query.isNotEmpty;
      _selected = false;
    });
    _syncFooter();
  }

  void _onQueryChanged(String value) {
    if (_showResult || _selected) {
      setState(() {
        _showResult = false;
        _selected = false;
      });
      _syncFooter();
    }
  }

  void _continue() {
    if (!_selected) return;
    widget.data
      ..companyQuery = _queryController.text.trim()
      ..companyName = _mockName
      ..companyInn = _mockInn
      ..companyCity = _mockCity
      ..companyIndustry = _mockIndustry;
    widget.onNext?.call();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final s = context.scale;
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 0,
          showChrome: !widget.embedded,
          title: 'Ваша компания',
          subtitle:
              'Найдите компанию по названию или ИНН. Мы подставим открытые данные для проверки.',
        ),
        SizedBox(height: 32 * s),
        AuthTextField(
          label: 'Название или ИНН',
          controller: _queryController,
          focusNode: _queryFocus,
          autofocus: widget.embedded,
          hint: 'Введите название или ИНН',
          textInputAction: TextInputAction.search,
          onChanged: _onQueryChanged,
          onSubmitted: _runSearch,
          suffix: GestureDetector(
            onTap: () => _runSearch(),
            behavior: HitTestBehavior.opaque,
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 2 * s, vertical: 8 * s),
              child: Icon(
                Icons.search,
                color: AppColors.textSecondary,
                size: 20 * s,
              ),
            ),
          ),
        ),
        if (_showResult) ...[
          SizedBox(height: 20 * s),
          CompanyCard(
            name: _mockName,
            inn: _mockInn,
            city: _mockCity,
            industry: _mockIndustry,
            selected: _selected,
            onTap: () {
              setState(() => _selected = true);
              _syncFooter();
            },
          ),
        ],
        SizedBox(height: 16 * s),
        Align(
          alignment: Alignment.centerLeft,
          child: Text.rich(
            TextSpan(
              style: AppTypography.medium(
                12 * s,
                color: AppColors.textSecondary,
              ),
              children: [
                const TextSpan(text: 'Нет в списке? '),
                WidgetSpan(
                  alignment: PlaceholderAlignment.baseline,
                  baseline: TextBaseline.alphabetic,
                  child: GestureDetector(
                    onTap: () {},
                    child: Text(
                      'Добавить вручную',
                      style: AppTypography.medium(
                        12 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
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
      buttonLabel: 'Это моя компания',
      footerHint:
          'Данные компании можно будет исправить. И дополнить на следующем шаге.',
      onContinue: _selected ? _continue : null,
      body: body,
    );
  }
}
