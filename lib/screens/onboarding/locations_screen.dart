import 'package:flutter/material.dart';

import '../../data/cities_catalog.dart';
import '../../models/onboarding_data.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
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
  static const _borderColor = Color(0xFFE3E5E3);
  static const _addBorder = Color(0xFFD92F37);

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
  }

  @override
  void didUpdateWidget(covariant LocationsScreen oldWidget) {
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
      onPressed: _continue,
    );
  }

  void _addRegion(String region) {
    if (_regions.contains(region)) return;
    setState(() => _regions.add(region));
  }

  void _removeRegion(int index) {
    setState(() {
      _regions.removeAt(index);
      final known = _knownCitiesForRegions;
      _cities.removeWhere((city) => !known.contains(city));
    });
  }

  void _addCity(String city) {
    if (_cities.contains(city)) return;
    setState(() => _cities.add(city));
  }

  void _removeCity(int index) {
    setState(() => _cities.removeAt(index));
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
    widget.data.salesRegions = List.of(_regions);
    widget.data.cities = List.of(_cities);
    widget.onNext?.call();
  }

  Widget _selectedField({
    required String label,
    required int index,
    required VoidCallback onRemove,
  }) {
    return Container(
      height: 50,
      margin: EdgeInsets.only(top: index == 0 ? 8 : 12),
      padding: const EdgeInsets.only(left: 16, right: 4),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: _borderColor),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.bold(14, color: AppColors.textInput),
            ),
          ),
          IconButton(
            onPressed: onRemove,
            icon: const Icon(
              Icons.close,
              size: 18,
              color: AppColors.textSecondary,
            ),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
          ),
        ],
      ),
    );
  }

  Widget _addRegionDropdown() {
    final available = _availableRegions;
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Container(
        height: 50,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: _addBorder),
        ),
        child: available.isEmpty
            ? Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Все регионы добавлены',
                  style: AppTypography.regular(15, color: AppColors.textHint),
                ),
              )
            : DropdownButtonHideUnderline(
                child: DropdownButton<String>(
                  isExpanded: true,
                  hint: Text(
                    '+ Добавить регион',
                    style: AppTypography.regular(15, color: _addBorder),
                  ),
                  icon: const Icon(
                    Icons.keyboard_arrow_down_rounded,
                    color: _addBorder,
                  ),
                  style: AppTypography.bold(14, color: AppColors.textInput),
                  dropdownColor: AppColors.surface,
                  borderRadius: BorderRadius.circular(16),
                  items: [
                    for (final country in available)
                      DropdownMenuItem<String>(
                        value: country,
                        child: Text(
                          country,
                          style: AppTypography.regular(
                            15,
                            color: AppColors.textPrimary,
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
    final enabled = _regions.isNotEmpty && _citiesReady;
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: GestureDetector(
        onTap: enabled ? _openCityPicker : null,
        behavior: HitTestBehavior.opaque,
        child: Container(
          height: 50,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: enabled ? _addBorder : _borderColor,
            ),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  !_citiesReady
                      ? 'Загрузка городов…'
                      : _regions.isEmpty
                          ? 'Сначала выберите регион'
                          : '+ Добавить город',
                  style: AppTypography.regular(
                    15,
                    color: enabled ? _addBorder : AppColors.textHint,
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
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 5,
          showChrome: !widget.embedded,
          title: 'Где работает бизнес?',
          subtitle:
              'Сначала выберите регионы продаж, затем укажите города в этих странах.',
        ),
        const SizedBox(height: 28),
        Text(
          'РЕГИОНЫ ПРОДАЖ',
          style: AppTypography.bold(12, color: AppColors.textSecondary),
        ),
        for (var i = 0; i < _regions.length; i++)
          _selectedField(
            label: _regions[i],
            index: i,
            onRemove: () => _removeRegion(i),
          ),
        _addRegionDropdown(),
        const SizedBox(height: 28),
        Text(
          'ГОРОДА',
          style: AppTypography.bold(12, color: AppColors.textSecondary),
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
        padding: const EdgeInsets.fromLTRB(30, 16, 30, 16),
        child: body,
      );
    }

    return OnboardingScaffold(
      buttonLabel: 'Продолжить',
      onContinue: _continue,
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
  static const _addBorder = Color(0xFFD92F37);

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
              const SizedBox(height: 10),
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                    color: const Color(0xFFE3E5E3),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                child: Text(
                  'Выберите город',
                  style: AppTypography.bold(18, color: AppColors.textPrimary),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
                child: Container(
                  height: 50,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: const Color(0xFFE3E5E3)),
                  ),
                  alignment: Alignment.centerLeft,
                  child: TextField(
                    controller: _controller,
                    autofocus: true,
                    onChanged: _onQuery,
                    cursorColor: _addBorder,
                    textInputAction: TextInputAction.search,
                    style: AppTypography.bold(14, color: AppColors.textInput),
                    decoration: InputDecoration(
                      isCollapsed: true,
                      border: InputBorder.none,
                      hintText: 'Поиск города',
                      hintStyle: AppTypography.regular(
                        14,
                        color: AppColors.textHint,
                      ),
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Text(
                  '${_filtered.length} из ${_all.length}',
                  style: AppTypography.regular(
                    12,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
              Expanded(
                child: _filtered.isEmpty
                    ? Center(
                        child: Text(
                          'Ничего не найдено',
                          style: AppTypography.regular(
                            15,
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
                                14,
                                color: AppColors.textInput,
                              ),
                            ),
                            subtitle: country == null
                                ? null
                                : Text(
                                    country,
                                    style: AppTypography.regular(
                                      12,
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
