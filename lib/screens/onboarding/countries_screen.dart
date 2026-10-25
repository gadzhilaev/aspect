import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
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
  static Color get _borderColor => AppColors.border;
  static const _addBorder = AppColors.brandRedLight;

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
        if (mounted) {
          setState(() {}); // заголовок по businessType
          _syncFooter();
        }
      });
    }
  }

  bool get _canContinue => _countries.isNotEmpty;

  void _syncFooter() {
    final l10n = context.l10n;
    final copy = l10n.countriesCopyForBusinessType(widget.data.businessType);
    widget.bindFooter?.call(
      label: l10n.continueAction,
      hint: copy.footer,
      onPressed: _canContinue ? _continue : null,
    );
  }

  void _addCountry(String country) {
    if (_countries.contains(country)) return;
    setState(() => _countries.add(country));
    _syncFooter();
  }

  void _removeCountry(int index) {
    setState(() => _countries.removeAt(index));
    _syncFooter();
  }

  void _continue() {
    if (!_canContinue) return;
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

  Widget _addCountryDropdown({required String addLabel}) {
    final s = context.scale;
    final l10n = context.l10n;
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
                  l10n.onboardingAllCountriesAdded,
                  style: AppTypography.regular(15 * s, color: AppColors.textHint),
                ),
              )
            : DropdownButtonHideUnderline(
                child: DropdownButton<String>(
                  isExpanded: true,
                  hint: Text(
                    addLabel,
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
    final l10n = context.l10n;
    final copy = l10n.countriesCopyForBusinessType(widget.data.businessType);
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 4,
          showChrome: !widget.embedded,
          title: copy.title,
          subtitle: copy.subtitle,
        ),
        SizedBox(height: 28 * s),
        Text(
          copy.section,
          style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
        ),
        for (var i = 0; i < _countries.length; i++) _countryField(i),
        _addCountryDropdown(addLabel: copy.add),
      ],
    );

    if (widget.embedded) {
      return SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 16 * s, 16 * s),
        child: body,
      );
    }

    return OnboardingScaffold(
      buttonLabel: l10n.continueAction,
      footerHint: copy.footer,
      onContinue: _canContinue ? _continue : null,
      body: body,
    );
  }
}
