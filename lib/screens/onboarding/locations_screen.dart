import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../data/cities_catalog.dart';
import '../../models/onboarding_data.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/onboarding_widgets.dart';

class LocationsScreen extends StatefulWidget {
  const LocationsScreen({
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
  State<LocationsScreen> createState() => _LocationsScreenState();
}

class _LocationsScreenState extends State<LocationsScreen>
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

  late List<String> _regions;
  late List<String> _cities;
  bool _citiesReady = false;

  @override
  bool get wantKeepAlive => true;

  List<String> get _availableRegions => [
        for (final c in _allCountries)
          if (!_regions.contains(c)) c,
      ];

  Set<String> get _knownCitiesForRegions {
    final set = <String>{};
    for (final region in _regions) {
      set.addAll(CitiesCatalog.citiesForCountryName(region));
    }
    return set;
  }

  @override
  void initState() {
    super.initState();
    _regions = List.of(widget.data.salesRegions);
    _cities = List.of(widget.data.cities);
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncFooter());
    _loadCities();
  }

  Future<void> _loadCities() async {
    await CitiesCatalog.ensureLoaded();
    if (!mounted) return;
    setState(() => _citiesReady = true);
    _syncFooter();
  }

  @override
  void didUpdateWidget(covariant LocationsScreen oldWidget) {
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

  bool get _canContinue =>
      _regions.isNotEmpty && _cities.isNotEmpty && _citiesReady;

  void _syncFooter() {
    widget.bindFooter?.call(
      label: context.l10n.continueAction,
      onPressed: _canContinue ? _continue : null,
    );
  }

  void _addRegion(String region) {
    if (_regions.contains(region)) return;
    setState(() => _regions.add(region));
    _syncFooter();
  }

  void _removeRegion(int index) {
    setState(() {
      _regions.removeAt(index);
      final known = _knownCitiesForRegions;
      _cities.removeWhere((city) => !known.contains(city));
    });
    _syncFooter();
  }

  void _addCity(String city) {
    if (_cities.contains(city)) return;
    setState(() => _cities.add(city));
    _syncFooter();
  }

  void _removeCity(int index) {
    setState(() => _cities.removeAt(index));
    _syncFooter();
  }

  Future<void> _openCityPicker() async {
    if (_regions.isEmpty || !_citiesReady) return;
    final selected = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => _CitySearchSheet(
        regions: List.of(_regions),
        alreadySelected: _cities.toSet(),
      ),
    );
    if (selected != null) _addCity(selected);
  }

  void _continue() {
    if (!_canContinue) return;
    widget.data.salesRegions = List.of(_regions);
    widget.data.cities = List.of(_cities);
    widget.onNext?.call();
  }

  Widget _selectedField({
    required String label,
    required int index,
    required VoidCallback onRemove,
  }) {
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
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.bold(14 * s, color: AppColors.textInput),
            ),
          ),
          IconButton(
            onPressed: onRemove,
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

  Widget _addRegionDropdown({required String addLabel}) {
    final s = context.scale;
    final l10n = context.l10n;
    final available = _availableRegions;
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
                  l10n.onboardingAllRegionsAdded,
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
                    if (value != null) _addRegion(value);
                  },
                ),
              ),
      ),
    );
  }

  Widget _addCityButton() {
    final s = context.scale;
    final l10n = context.l10n;
    final enabled = _regions.isNotEmpty && _citiesReady;
    return Padding(
      padding: EdgeInsets.only(top: 12 * s),
      child: GestureDetector(
        onTap: enabled ? _openCityPicker : null,
        behavior: HitTestBehavior.opaque,
        child: Container(
          height: 50 * s,
          padding: EdgeInsets.symmetric(horizontal: 16 * s),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16 * s),
            border: Border.all(
              color: enabled ? _addBorder : _borderColor,
            ),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  !_citiesReady
                      ? l10n.onboardingLoadingCities
                      : _regions.isEmpty
                          ? l10n.onboardingSelectRegionFirst
                          : l10n.onboardingAddCity,
                  style: AppTypography.regular(15 * s, color: enabled ? _addBorder : AppColors.textHint,
                  ),
                ),
              ),
              if (enabled)
                const Icon(
                  Icons.keyboard_arrow_down_rounded,
                  color: _addBorder,
                ),
            ],
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
    final copy = l10n.locationsCopyForBusinessType(widget.data.businessType);
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 5,
          showChrome: !widget.embedded,
          title: copy.title,
          subtitle: copy.subtitle,
        ),
        SizedBox(height: 28 * s),
        Text(
          copy.regionsSection,
          style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
        ),
        for (var i = 0; i < _regions.length; i++)
          _selectedField(
            label: _regions[i],
            index: i,
            onRemove: () => _removeRegion(i),
          ),
        _addRegionDropdown(addLabel: copy.addRegion),
        SizedBox(height: 28 * s),
        Text(
          copy.citiesSection,
          style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
        ),
        for (var i = 0; i < _cities.length; i++)
          _selectedField(
            label: _cities[i],
            index: i,
            onRemove: () => _removeCity(i),
          ),
        _addCityButton(),
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
      onContinue: _canContinue ? _continue : null,
      body: body,
    );
  }
}

class _CitySearchSheet extends StatefulWidget {
  const _CitySearchSheet({
    required this.regions,
    required this.alreadySelected,
  });

  final List<String> regions;
  final Set<String> alreadySelected;

  @override
  State<_CitySearchSheet> createState() => _CitySearchSheetState();
}

class _CitySearchSheetState extends State<_CitySearchSheet> {
  static const _addBorder = AppColors.brandRedLight;

  late final List<String> _all;
  late List<String> _filtered;
  final _controller = TextEditingController();

  @override
  void initState() {
    super.initState();
    _all = [
      for (final city in CitiesCatalog.citiesForCountries(widget.regions))
        if (!widget.alreadySelected.contains(city)) city,
    ];
    _filtered = _all;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onQuery(String query) {
    final q = query.trim().toLowerCase();
    setState(() {
      if (q.isEmpty) {
        _filtered = _all;
      } else {
        _filtered = [
          for (final city in _all)
            if (city.toLowerCase().contains(q)) city,
        ];
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final l10n = context.l10n;
    final media = MediaQuery.of(context);
    final bottom = media.viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottom),
      child: SizedBox(
        height: media.size.height * 0.78,
        child: SafeArea(
          top: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(height: 10 * s),
              Center(
                child: Container(
                  width: 36 * s,
                  height: 4 * s,
                  decoration: BoxDecoration(
                    color: AppColors.border,
                    borderRadius: BorderRadius.circular(2 * s),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(20 * s, 16 * s, 20 * s, 8 * s),
                child: Text(
                  l10n.onboardingPickCityTitle,
                  style: AppTypography.bold(18 * s, color: AppColors.textPrimary),
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(20 * s, 0, 20 * s, 12 * s),
                child: Container(
                  height: 50 * s,
                  padding: EdgeInsets.symmetric(horizontal: 16 * s),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(16 * s),
                    border: Border.all(color: AppColors.border),
                  ),
                  alignment: Alignment.centerLeft,
                  child: TextField(
                    controller: _controller,
                    autofocus: true,
                    onChanged: _onQuery,
                    cursorColor: _addBorder,
                    textInputAction: TextInputAction.search,
                    textCapitalization: TextCapitalization.sentences,
                    style: AppTypography.bold(14 * s, color: AppColors.textInput),
                    decoration: InputDecoration(
                      isCollapsed: true,
                      border: InputBorder.none,
                      hintText: l10n.onboardingSearchCityHint,
                      hintStyle: AppTypography.regular(
                        14 * s,
                        color: AppColors.textHint,
                      ),
                    ),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(20 * s, 0, 20 * s, 8 * s),
                child: Text(
                  l10n.onboardingCityCount(_filtered.length, _all.length),
                  style: AppTypography.regular(
                    12 * s,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
              Expanded(
                child: _filtered.isEmpty
                    ? Center(
                        child: Text(
                          l10n.onboardingNothingFound,
                          style: AppTypography.regular(
                            15 * s,
                            color: AppColors.textHint,
                          ),
                        ),
                      )
                    : ListView.builder(
                        keyboardDismissBehavior:
                            ScrollViewKeyboardDismissBehavior.onDrag,
                        itemCount: _filtered.length,
                        itemBuilder: (context, index) {
                          final city = _filtered[index];
                          final country = CitiesCatalog.countryForCity(
                            city,
                            widget.regions,
                          );
                          return ListTile(
                            title: Text(
                              city,
                              style: AppTypography.bold(
                                14 * s,
                                color: AppColors.textInput,
                              ),
                            ),
                            subtitle: country == null
                                ? null
                                : Text(
                                    country,
                                    style: AppTypography.regular(
                                      12 * s,
                                      color: AppColors.textSecondary,
                                    ),
                                  ),
                            onTap: () => Navigator.pop(context, city),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
