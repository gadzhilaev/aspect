import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../api/auth_api.dart';
import '../../api/companies_api.dart';
import '../../data/cities_catalog.dart';
import '../../models/onboarding_data.dart';
import '../../navigation/app_page_route.dart';
import '../../services/auth_store.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/auth_widgets.dart';
import 'change_password_screen.dart';
import 'profile_field_edit_screen.dart';

enum ContextSection {
  products,
  markets,
  geography,
  myData,
  finance,
  counterparties,
}

Future<bool> openContextEdit(
  BuildContext context, {
  required ContextSection section,
  required OnboardingData profile,
}) async {
  final result = await Navigator.of(context).push<bool>(
    AppPageRoute(
      builder: (_) => ContextEditScreen(
        section: section,
        profile: profile,
      ),
    ),
  );
  return result == true;
}

class ContextEditScreen extends StatefulWidget {
  const ContextEditScreen({
    super.key,
    required this.section,
    required this.profile,
  });

  final ContextSection section;
  final OnboardingData profile;

  @override
  State<ContextEditScreen> createState() => _ContextEditScreenState();
}

class _ContextEditScreenState extends State<ContextEditScreen> {
  static Color get _borderColor => AppColors.border;
  static const _addBorder = AppColors.brandRedLight;

  static const _roles = [
    'Операционный директор',
    'Генеральный директор',
    'Финансовый директор',
    'Коммерческий директор',
    'Руководитель подразделения',
    'Сотрудник',
  ];

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

  late List<String> _items;
  late List<String> _brands;
  late List<String> _categories;
  late List<String> _productLines;
  late List<String> _procurementCountries;
  late String _role;
  late final TextEditingController _fullNameController;
  late final TextEditingController _emailController;
  final _addController = TextEditingController();
  final _addFocus = FocusNode();
  final _brandController = TextEditingController();
  final _categoryController = TextEditingController();
  bool _adding = false;
  bool _saving = false;
  bool _dirty = false;
  late String _confirmedEmail;

  _SectionCopy get _copy {
    switch (widget.section) {
      case ContextSection.products:
        return const _SectionCopy(
          title: 'Продукты',
          accent: 'Что компания производит и продает',
          listLabel: 'Продукты',
          addLabel: '+ Добавить продукт',
          addHint: 'Название продукта',
        );
      case ContextSection.markets:
        return const _SectionCopy(
          title: 'Рынки',
          accent: 'Страны поставок и партнёров',
          listLabel: 'Страны',
          addLabel: '+ Добавить страну',
          addHint: 'Страна',
          useCountryPicker: true,
        );
      case ContextSection.geography:
        return const _SectionCopy(
          title: 'География',
          accent: 'Где работает бизнес',
          listLabel: 'Города',
          addLabel: '+ Добавить город',
          addHint: 'Название города',
          useCityPicker: true,
        );
      case ContextSection.myData:
        return const _SectionCopy(
          title: 'Мои данные',
          accent: 'Аккаунт и роль в компании',
          listLabel: '',
          addLabel: '',
          addHint: '',
        );
      case ContextSection.finance:
        return const _SectionCopy(
          title: 'Финансы',
          accent: 'Финансовые показатели',
          listLabel: 'Показатели',
          addLabel: '+ Добавить показатель',
          addHint: 'Название показателя',
        );
      case ContextSection.counterparties:
        return const _SectionCopy(
          title: 'Контрагенты и связи',
          accent: 'Партнёры и связи компании',
          listLabel: 'Контрагенты',
          addLabel: '+ Добавить контрагента',
          addHint: 'Название контрагента',
        );
    }
  }

  @override
  void initState() {
    super.initState();
    final d = widget.profile;
    _items = switch (widget.section) {
      ContextSection.products => List.of(d.products),
      ContextSection.markets => List.of(
          d.countries.isNotEmpty
              ? d.countries
              : d.salesRegions.isNotEmpty
                  ? d.salesRegions
                  : [
                      if (d.mainMarket.trim().isNotEmpty) d.mainMarket.trim(),
                    ],
        ),
      ContextSection.geography => List.of(
          d.cities.isNotEmpty
              ? d.cities
              : [
                  if (d.companyCity.trim().isNotEmpty) d.companyCity.trim(),
                ],
        ),
      ContextSection.finance => List.of(d.finances),
      ContextSection.counterparties => List.of(d.counterparties),
      ContextSection.myData => [],
    };
    _brands = List.of(d.brands);
    _categories = List.of(d.productCategories);
    _productLines = List.of(d.productLines);
    _procurementCountries = List.of(d.procurementCountries);
    _role = _roles.contains(d.role) ? d.role : '';
    _fullNameController = TextEditingController(text: d.fullName);
    _emailController = TextEditingController(text: d.email);
    _confirmedEmail = d.email.trim();
    _loadIndustryFromApi();
  }

  Future<void> _loadIndustryFromApi() async {
    if (widget.section != ContextSection.products &&
        widget.section != ContextSection.markets) {
      return;
    }
    final companyId = await AuthStore.companyId();
    if (companyId == null || companyId.isEmpty) return;
    try {
      final raw = await CompaniesApi.instance.getIndustryProfile(companyId);
      if (!mounted) return;
      setState(() {
        final brands = raw['brands'];
        final cats = raw['product_categories'];
        final lines = raw['product_lines'];
        final proc = raw['procurement_countries'];
        if (brands is List && brands.isNotEmpty) {
          _brands = [for (final b in brands) b.toString()];
        }
        if (cats is List && cats.isNotEmpty) {
          _categories = [for (final c in cats) c.toString()];
        }
        if (lines is List && lines.isNotEmpty) {
          _productLines = [for (final l in lines) l.toString()];
        }
        if (proc is List && proc.isNotEmpty) {
          _procurementCountries = [for (final p in proc) p.toString()];
        }
      });
    } catch (_) {}
  }

  @override
  void dispose() {
    _addController.dispose();
    _addFocus.dispose();
    _brandController.dispose();
    _categoryController.dispose();
    _fullNameController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  List<String> get _availableCountries => [
        for (final c in _allCountries)
          if (!_items.contains(c)) c,
      ];

  void _startAdding() {
    setState(() => _adding = true);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _addFocus.requestFocus();
    });
  }

  void _commitAdd() {
    final value = _addController.text.trim();
    _addController.clear();
    setState(() {
      _adding = false;
      if (value.isNotEmpty && !_items.contains(value)) {
        _items.add(value);
        _dirty = true;
      }
    });
  }

  void _addCountry(String country) {
    if (_items.contains(country)) return;
    setState(() {
      _items.add(country);
      _dirty = true;
    });
  }

  void _removeAt(int index) {
    setState(() {
      _items.removeAt(index);
      _dirty = true;
    });
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() => _saving = true);
    final d = widget.profile;
    switch (widget.section) {
      case ContextSection.products:
        d.products = List.of(_items);
        d.brands = List.of(_brands);
        d.productCategories = List.of(_categories);
        d.productLines = List.of(_productLines);
      case ContextSection.markets:
        d.countries = List.of(_items);
        d.procurementCountries = List.of(_procurementCountries);
        if (d.mainMarket.trim().isEmpty && _items.isNotEmpty) {
          d.mainMarket = _items.first;
        }
      case ContextSection.geography:
        d.cities = List.of(_items);
        if (d.companyCity.trim().isEmpty && _items.isNotEmpty) {
          d.companyCity = _items.first;
        }
      case ContextSection.finance:
        d.finances = List.of(_items);
      case ContextSection.counterparties:
        d.counterparties = List.of(_items);
      case ContextSection.myData:
        d.role = _role;
        d.fullName = _fullNameController.text.trim();
        d.email = _confirmedEmail;
    }
    await SessionStore.saveProfile(d);
    await _syncGraphNodes();
    await _syncIndustryProfile();
    if (widget.section == ContextSection.myData && _role.trim().isNotEmpty) {
      try {
        await AuthApi.instance.patchPreferences(jobRole: _role.trim());
      } catch (_) {}
    }
    if (!mounted) return;
    Navigator.of(context).pop(true);
  }

  Future<void> _syncIndustryProfile() async {
    if (widget.section != ContextSection.products &&
        widget.section != ContextSection.markets) {
      return;
    }
    final companyId = await AuthStore.companyId();
    if (companyId == null || companyId.isEmpty) return;
    try {
      await CompaniesApi.instance.patchIndustryProfile(companyId, {
        if (widget.section == ContextSection.products) ...{
          'brands': _brands,
          'product_categories': _categories,
          'product_lines': _productLines,
        },
        if (widget.section == ContextSection.markets) ...{
          'sales_markets': _items,
          'procurement_countries': _procurementCountries,
        },
      });
    } catch (_) {}
  }

  /// Дописываем новые узлы на бэк (как в онбординге). Удаление API не даёт.
  Future<void> _syncGraphNodes() async {
    final companyId = await AuthStore.companyId();
    if (companyId == null || companyId.isEmpty) return;
    try {
      final profile = await CompaniesApi.instance.getProfile(companyId);
      final existing = <String>{};
      final nodes = profile['nodes'];
      if (nodes is List) {
        for (final n in nodes) {
          if (n is! Map) continue;
          final type = (n['node_type'] ?? '').toString();
          final name = (n['name'] ?? '').toString().trim().toLowerCase();
          if (name.isEmpty) continue;
          existing.add('$type|$name');
        }
      }
      Future<void> ensure(String type, String name, {String? country}) async {
        final key = '$type|${name.trim().toLowerCase()}';
        if (name.trim().isEmpty || existing.contains(key)) return;
        await CompaniesApi.instance.addNode(
          companyId,
          nodeType: type,
          name: name.trim(),
          country: country,
        );
        existing.add(key);
      }

      switch (widget.section) {
        case ContextSection.products:
          for (final p in _items) {
            await ensure('product', p);
          }
        case ContextSection.markets:
          for (final m in _items) {
            await ensure('market', m, country: m);
          }
        case ContextSection.counterparties:
          for (final c in _items) {
            await ensure('supplier', c);
          }
        case ContextSection.geography:
          // Города хранятся локально + первый город → hq_region на сервере
          // (иначе после переустановки плитка снова «Пока пусто»).
          if (_items.isNotEmpty) {
            try {
              await CompaniesApi.instance.patchCompany(companyId, {
                'hq_region': _items.first.trim(),
              });
            } catch (_) {}
          }
          for (final city in _items) {
            await ensure('facility', city);
          }
        case ContextSection.finance:
        case ContextSection.myData:
          break;
      }
    } catch (_) {
      // Локальный профиль уже сохранён.
    }
  }

  Future<void> _openCityPicker() async {
    final regions = widget.profile.countries.isNotEmpty
        ? widget.profile.countries
        : [
            if (widget.profile.mainMarket.trim().isNotEmpty)
              widget.profile.mainMarket.trim(),
            'Россия',
          ];
    await CitiesCatalog.ensureLoaded();
    if (!mounted) return;
    final selected = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => _CitySearchSheet(
        regions: regions,
        alreadySelected: _items.toSet(),
      ),
    );
    if (selected == null) return;
    if (_items.contains(selected)) return;
    setState(() {
      _items.add(selected);
      _dirty = true;
    });
  }

  Widget _itemRow(int index) {
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
              _items[index],
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.bold(14 * s, color: AppColors.textInput),
            ),
          ),
          IconButton(
            onPressed: () => _removeAt(index),
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

  Widget _addField() {
    final s = context.scale;
    final copy = _copy;
    if (copy.useCountryPicker) {
      final available = _availableCountries;
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
                    style: AppTypography.regular(
                      15 * s,
                      color: AppColors.textHint,
                    ),
                  ),
                )
              : DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    isExpanded: true,
                    hint: Text(
                      copy.addLabel,
                      style: AppTypography.regular(15 * s, color: _addBorder),
                    ),
                    icon: const Icon(
                      Icons.keyboard_arrow_down_rounded,
                      color: _addBorder,
                    ),
                    style: AppTypography.bold(
                      14 * s,
                      color: AppColors.textInput,
                    ),
                    dropdownColor: AppColors.surface,
                    borderRadius: BorderRadius.circular(16 * s),
                    items: [
                      for (final country in available)
                        DropdownMenuItem(
                          value: country,
                          child: Text(
                            country,
                            style: AppTypography.regular(
                              15 * s,
                              color: AppColors.textPrimary,
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

    if (copy.useCityPicker) {
      return Padding(
        padding: EdgeInsets.only(top: 12 * s),
        child: GestureDetector(
          onTap: _openCityPicker,
          behavior: HitTestBehavior.opaque,
          child: Container(
            height: 50 * s,
            padding: EdgeInsets.symmetric(horizontal: 16 * s),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(16 * s),
              border: Border.all(color: _addBorder),
            ),
            alignment: Alignment.center,
            child: Text(
              copy.addLabel,
              style: AppTypography.regular(15 * s, color: _addBorder),
            ),
          ),
        ),
      );
    }

    return Padding(
      padding: EdgeInsets.only(top: 12 * s),
      child: _adding
          ? Container(
              height: 50 * s,
              padding: EdgeInsets.symmetric(horizontal: 16 * s),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(16 * s),
                border: Border.all(color: _addBorder),
              ),
              alignment: Alignment.centerLeft,
              child: TextField(
                controller: _addController,
                focusNode: _addFocus,
                cursorColor: _addBorder,
                textInputAction: TextInputAction.done,
                textCapitalization: TextCapitalization.sentences,
                onSubmitted: (_) => _commitAdd(),
                onEditingComplete: _commitAdd,
                style: AppTypography.bold(14 * s, color: AppColors.textInput),
                decoration: InputDecoration(
                  isCollapsed: true,
                  border: InputBorder.none,
                  hintText: copy.addHint,
                  hintStyle: AppTypography.regular(
                    14 * s,
                    color: AppColors.textHint,
                  ),
                  contentPadding: EdgeInsets.zero,
                ),
              ),
            )
          : GestureDetector(
              onTap: _startAdding,
              behavior: HitTestBehavior.opaque,
              child: Container(
                height: 50 * s,
                padding: EdgeInsets.symmetric(horizontal: 16 * s),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(16 * s),
                  border: Border.all(color: _addBorder),
                ),
                alignment: Alignment.center,
                child: Text(
                  copy.addLabel,
                  style: AppTypography.regular(15 * s, color: _addBorder),
                ),
              ),
            ),
    );
  }

  Widget _chipList({
    required String label,
    required List<String> items,
    required TextEditingController controller,
    required String hint,
    required void Function(String) onAdd,
    required void Function(int) onRemove,
  }) {
    final s = context.scale;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(height: 20 * s),
        Text(
          label,
          style: AppTypography.medium(13 * s, color: AppColors.textMuted),
        ),
        for (var i = 0; i < items.length; i++)
          Container(
            height: 50 * s,
            margin: EdgeInsets.only(top: i == 0 ? 8 * s : 12 * s),
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
                    items[i],
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.bold(
                      14 * s,
                      color: AppColors.textInput,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: () => onRemove(i),
                  icon: Icon(
                    Icons.close,
                    size: 18 * s,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        Padding(
          padding: EdgeInsets.only(top: 12 * s),
          child: Container(
            height: 50 * s,
            padding: EdgeInsets.symmetric(horizontal: 16 * s),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(16 * s),
              border: Border.all(color: _addBorder),
            ),
            alignment: Alignment.centerLeft,
            child: TextField(
              controller: controller,
              cursorColor: _addBorder,
              textInputAction: TextInputAction.done,
              textCapitalization: TextCapitalization.sentences,
              onSubmitted: (v) {
                final t = v.trim();
                if (t.isEmpty) return;
                onAdd(t);
                controller.clear();
              },
              style: AppTypography.bold(14 * s, color: AppColors.textInput),
              decoration: InputDecoration(
                isCollapsed: true,
                border: InputBorder.none,
                hintText: hint,
                hintStyle: AppTypography.regular(
                  14 * s,
                  color: AppColors.textHint,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _listBody() {
    final s = context.scale;
    final copy = _copy;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          copy.listLabel,
          style: AppTypography.medium(13 * s, color: AppColors.textMuted),
        ),
        for (var i = 0; i < _items.length; i++) _itemRow(i),
        _addField(),
        if (widget.section == ContextSection.products) ...[
          _chipList(
            label: 'Бренды',
            items: _brands,
            controller: _brandController,
            hint: '+ Добавить бренд (например Apple)',
            onAdd: (v) => setState(() {
              if (!_brands.contains(v)) {
                _brands.add(v);
                _dirty = true;
              }
            }),
            onRemove: (i) => setState(() {
              _brands.removeAt(i);
              _dirty = true;
            }),
          ),
          _chipList(
            label: 'Категории продукции',
            items: _categories,
            controller: _categoryController,
            hint: '+ Добавить категорию (смартфоны)',
            onAdd: (v) => setState(() {
              if (!_categories.contains(v)) {
                _categories.add(v);
                _dirty = true;
              }
            }),
            onRemove: (i) => setState(() {
              _categories.removeAt(i);
              _dirty = true;
            }),
          ),
        ],
        if (widget.section == ContextSection.markets)
          _chipList(
            label: 'География закупок',
            items: _procurementCountries,
            controller: _categoryController,
            hint: '+ Страна закупки (Китай, США…)',
            onAdd: (v) => setState(() {
              if (!_procurementCountries.contains(v)) {
                _procurementCountries.add(v);
                _dirty = true;
              }
            }),
            onRemove: (i) => setState(() {
              _procurementCountries.removeAt(i);
              _dirty = true;
            }),
          ),
      ],
    );
  }

  String get _displayName {
    final name = _fullNameController.text.trim();
    return name.isEmpty ? 'Имя не указано' : name;
  }

  String get _avatarInitials {
    final parts = _fullNameController.text.trim().split(RegExp(r'\s+'));
    final letters = [
      for (final part in parts.take(3))
        if (part.isNotEmpty) part[0].toUpperCase(),
    ];
    if (letters.isEmpty) return '?';
    return letters.join();
  }

  Future<void> _persistMyData() async {
    final d = widget.profile;
    d.role = _role;
    d.fullName = _fullNameController.text.trim();
    d.email = _confirmedEmail;
    await SessionStore.saveProfile(d);
    _dirty = true;
    try {
      if (_role.trim().isNotEmpty) {
        await AuthApi.instance.patchPreferences(jobRole: _role.trim());
      }
    } catch (_) {}
  }

  Future<void> _editField(ProfileEditField field) async {
    final initial = switch (field) {
      ProfileEditField.fullName => _fullNameController.text.trim(),
      ProfileEditField.email => _confirmedEmail,
      ProfileEditField.role => _role,
    };
    final result = await openProfileFieldEdit(
      context,
      field: field,
      initialValue: initial,
      currentEmail: _confirmedEmail,
      roleOptions: _roles,
    );
    if (!mounted || result == null) return;
    setState(() {
      switch (field) {
        case ProfileEditField.fullName:
          _fullNameController.text = result;
        case ProfileEditField.email:
          _confirmedEmail = result;
          _emailController.text = result;
        case ProfileEditField.role:
          _role = result;
      }
    });
    await _persistMyData();
  }

  Widget _myDataBody() {
    final s = context.scale;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: EdgeInsets.all(16 * s),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16 * s),
            border: Border.all(color: AppColors.border, width: 1),
          ),
          child: Row(
            children: [
              Container(
                width: 48 * s,
                height: 48 * s,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppColors.brandRed,
                  shape: BoxShape.circle,
                ),
                child: Text(
                  _avatarInitials,
                  style: AppTypography.bold(
                    _avatarInitials.length >= 3 ? 13 * s : 18 * s,
                    color: AppColors.surface,
                  ),
                ),
              ),
              SizedBox(width: 14 * s),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _displayName,
                      style: AppTypography.bold(
                        16 * s,
                        color: AppColors.textInk,
                      ),
                    ),
                    SizedBox(height: 4 * s),
                    Text(
                      'Рабочий аккаунт',
                      style: AppTypography.regular(
                        12 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        SizedBox(height: 24 * s),
        Text(
          'Контактные данные',
          style: AppTypography.bold(12 * s, color: AppColors.textMuted),
        ),
        SizedBox(height: 10 * s),
        _dataRow(
          title: 'ФИО',
          value: _displayName,
          onEdit: () => _editField(ProfileEditField.fullName),
        ),
        SizedBox(height: 12 * s),
        _dataRow(
          title: 'Рабочая почта',
          value: _confirmedEmail.isEmpty ? 'Не указана' : _confirmedEmail,
          onEdit: () => _editField(ProfileEditField.email),
        ),
        SizedBox(height: 24 * s),
        Text(
          'Роль и доступ',
          style: AppTypography.bold(12 * s, color: AppColors.textMuted),
        ),
        SizedBox(height: 10 * s),
        _dataRow(
          title: 'Должность',
          value: _role.isEmpty ? 'Не указана' : _role,
          onEdit: () => _editField(ProfileEditField.role),
        ),
        SizedBox(height: 12 * s),
        _dataRow(
          title: 'Пароль',
          value: '••••••••',
          onEdit: () async {
            final changed = await openChangePasswordScreen(context);
            if (!mounted || !changed) return;
            setState(() => _dirty = true);
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                  'Пароль обновлён',
                  style: AppTypography.regular(13, color: AppColors.surface),
                ),
                behavior: SnackBarBehavior.floating,
                backgroundColor: AppColors.textInk,
              ),
            );
          },
        ),
        SizedBox(height: 12 * s),
        Container(
          width: double.infinity,
          padding: EdgeInsets.fromLTRB(16 * s, 14 * s, 16 * s, 14 * s),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16 * s),
            border: Border.all(color: AppColors.border, width: 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Права доступа',
                style: AppTypography.bold(13 * s, color: AppColors.textInput),
              ),
              SizedBox(height: 6 * s),
              Text(
                'Участник компании. Должность не определяет права доступа.',
                style: AppTypography.regular(
                  12 * s,
                  color: AppColors.textMuted,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _dataRow({
    required String title,
    required String value,
    required VoidCallback onEdit,
  }) {
    final s = context.scale;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(16 * s, 14 * s, 16 * s, 14 * s),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(color: AppColors.border, width: 1),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: AppTypography.bold(13 * s, color: AppColors.textInput),
                ),
                SizedBox(height: 6 * s),
                Text(
                  value,
                  style: AppTypography.regular(
                    12 * s,
                    color: AppColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
          SizedBox(width: 12 * s),
          GestureDetector(
            onTap: onEdit,
            behavior: HitTestBehavior.opaque,
            child: Text(
              'Изменить',
              style: AppTypography.bold(13 * s, color: AppColors.brandRed),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final copy = _copy;
    final bottom = MediaQuery.paddingOf(context).bottom;
    const titleSize = 24.83;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        Navigator.of(context).pop(_dirty);
      },
      child: AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
      ),
      child: Scaffold(
        backgroundColor: AppColors.surface,
        body: SafeArea(
          bottom: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 8 * s),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: GestureDetector(
                    onTap: () => Navigator.of(context).pop(_dirty),
                    behavior: HitTestBehavior.opaque,
                    child: Text(
                      '‹ Компания',
                      style: AppTypography.regular(
                        15 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                  ),
                ),
              ),
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(hPad, 10 * s, hPad, 24 * s),
                  children: [
                    Text(
                      copy.title,
                      style: AppTypography.medium(
                        titleSize * s,
                        color: AppColors.textInput,
                      ),
                    ),
                    SizedBox(height: 4 * s),
                    Text(
                      copy.accent,
                      style: AppTypography.medium(
                        titleSize * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                    SizedBox(height: 28 * s),
                    if (widget.section == ContextSection.myData)
                      _myDataBody()
                    else
                      _listBody(),
                  ],
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(
                  hPad,
                  8 * s,
                  hPad,
                  12 * s + bottom,
                ),
                child: AuthPrimaryButton(
                  label: 'Сохранить изменения',
                  onPressed: _saving ? null : _save,
                ),
              ),
            ],
          ),
        ),
      ),
      ),
    );
  }
}

class _SectionCopy {
  const _SectionCopy({
    required this.title,
    required this.accent,
    required this.listLabel,
    required this.addLabel,
    required this.addHint,
    this.useCountryPicker = false,
    this.useCityPicker = false,
  });

  final String title;
  final String accent;
  final String listLabel;
  final String addLabel;
  final String addHint;
  final bool useCountryPicker;
  final bool useCityPicker;
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
                  'Выберите город',
                  style:
                      AppTypography.bold(18 * s, color: AppColors.textPrimary),
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
                    cursorColor: AppColors.brandRed,
                    textInputAction: TextInputAction.search,
                    textCapitalization: TextCapitalization.sentences,
                    style:
                        AppTypography.bold(14 * s, color: AppColors.textInput),
                    decoration: InputDecoration(
                      isCollapsed: true,
                      border: InputBorder.none,
                      hintText: 'Поиск города',
                      hintStyle: AppTypography.regular(
                        14 * s,
                        color: AppColors.textHint,
                      ),
                    ),
                  ),
                ),
              ),
              Expanded(
                child: ListView.builder(
                  padding: EdgeInsets.fromLTRB(8 * s, 0, 8 * s, 16 * s),
                  itemCount: _filtered.length,
                  itemBuilder: (context, index) {
                    final city = _filtered[index];
                    return ListTile(
                      title: Text(
                        city,
                        style: AppTypography.regular(
                          15 * s,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      onTap: () => Navigator.of(context).pop(city),
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
