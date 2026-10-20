import 'package:flutter/material.dart';

import '../../models/onboarding_data.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/onboarding_widgets.dart';

class CountriesScreen extends StatefulWidget {
  const CountriesScreen({
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
  State<CountriesScreen> createState() => _CountriesScreenState();
}

class _CountriesScreenState extends State<CountriesScreen>
    with AutomaticKeepAliveClientMixin {
  static const _borderColor = AppColors.border;
  static const _addBorder = AppColors.brandRed;

  static const _allCountries = [
    'Россия',
    'Китай',
    'Беларусь',
    'Казахстан',
    'Узбекистан',
    'Армения',
    'Азербайджан',
    'Кыргызстан',
    'Таджикистан',
    'Турция',
    'Германия',
    'Индия',
    'ОАЭ',
    'США',
  ];

  late List<String> _countries;

  @override
  bool get wantKeepAlive => true;

  List<String> get _available => [
        for (final c in _allCountries)
          if (!_countries.contains(c)) c,
      ];

  @override
  void initState() {
    super.initState();
    _countries = List.of(widget.data.countries);
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncFooter());
  }

  @override
  void didUpdateWidget(covariant CountriesScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _syncFooter();
      });
    }
  }

  void _syncFooter() {
    widget.bindFooter?.call(
      label: 'Продолжить',
      hint:
          'Можно добавить детали позже. Начните с двух-трёх ключевых стран.',
      onPressed: _continue,
    );
  }

  void _addCountry(String country) {
    if (_countries.contains(country)) return;
    setState(() => _countries.add(country));
  }

  void _removeCountry(int index) {
    setState(() => _countries.removeAt(index));
  }

  void _continue() {
    widget.data.countries = List.of(_countries);
    widget.onNext?.call();
  }

  Widget _countryField(int index) {
    final s = context.scale;
    return Container(
      height: 50 * s,
      margin: EdgeInsets.only(top: index == 0 ? 8 * s : 12 * s),
      padding: EdgeInsets.only(left: 16 * s, right: 4 * s),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(color: _borderColor),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              _countries[index],
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.bold(14 * s, color: AppColors.textInput),
            ),
          ),
          IconButton(
            onPressed: () => _removeCountry(index),
            icon: Icon(
              Icons.close,
              size: 18 * s,
              color: AppColors.textSecondary,
            ),
            padding: EdgeInsets.zero,
            constraints: BoxConstraints(minWidth: 40 * s, minHeight: 40 * s),
          ),
        ],
      ),
    );
  }

  Widget _addCountryDropdown() {
    final s = context.scale;
    final available = _available;
    return Padding(
      padding: EdgeInsets.only(top: 12 * s),
      child: Container(
        height: 50 * s,
        padding: EdgeInsets.symmetric(horizontal: 16 * s),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16 * s),
          border: Border.all(color: _addBorder),
        ),
        child: available.isEmpty
            ? Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Все страны добавлены',
                  style: AppTypography.regular(15 * s, color: AppColors.textHint),
                ),
              )
            : DropdownButtonHideUnderline(
                child: DropdownButton<String>(
                  isExpanded: true,
                  hint: Text(
                    '+ Добавить страну',
                    style: AppTypography.regular(15 * s, color: _addBorder),
                  ),
                  icon: const Icon(
                    Icons.keyboard_arrow_down_rounded,
                    color: _addBorder,
                  ),
                  style: AppTypography.bold(14 * s, color: AppColors.textInput),
                  dropdownColor: AppColors.surface,
                  borderRadius: BorderRadius.circular(16 * s),
                  items: [
                    for (final country in available)
                      DropdownMenuItem<String>(
                        value: country,
                        child: Text(
                          country,
                          style: AppTypography.regular(15 * s, color: AppColors.textPrimary,
                          ),
                        ),
                      ),
                  ],
                  onChanged: (value) {
                    if (value != null) _addCountry(value);
                  },
                ),
              ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final s = context.scale;
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 4,
          showChrome: !widget.embedded,
          title: 'С какими странами работаете?',
          subtitle:
              'Выберите страны, где вы работаете или планируете развиваться. Мы учтём рынки, валюты и события, важные для вашего бизнеса.',
        ),
        SizedBox(height: 28 * s),
        Text(
          'СТРАНЫ',
          style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
        ),
        for (var i = 0; i < _countries.length; i++) _countryField(i),
        _addCountryDropdown(),
      ],
    );

    if (widget.embedded) {
      return SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(30 * s, 16 * s, 30 * s, 16 * s),
        child: body,
      );
    }

    return OnboardingScaffold(
      buttonLabel: 'Продолжить',
      footerHint:
          'Можно добавить детали позже. Начните с двух-трёх ключевых стран.',
      onContinue: _continue,
      body: body,
    );
  }
}
