import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../models/onboarding_data.dart';
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
    MaterialPageRoute(
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
  static const _borderColor = AppColors.border;
  static const _addBorder = AppColors.brandRed;

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
  late String _role;
  late final TextEditingController _fullNameController;
  late final TextEditingController _emailController;
  final _addController = TextEditingController();
  final _addFocus = FocusNode();
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
    _role = _roles.contains(d.role) ? d.role : '';
    _fullNameController = TextEditingController(text: d.fullName);
    _emailController = TextEditingController(text: d.email);
    _confirmedEmail = d.email.trim();
  }

  @override
  void dispose() {
    _addController.dispose();
    _addFocus.dispose();
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
      }
    });
  }

  void _addCountry(String country) {
    if (_items.contains(country)) return;
    setState(() => _items.add(country));
  }

  void _removeAt(int index) {
    setState(() => _items.removeAt(index));
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() => _saving = true);
    final d = widget.profile;
    switch (widget.section) {
      case ContextSection.products:
        d.products = List.of(_items);
      case ContextSection.markets:
        d.countries = List.of(_items);
      case ContextSection.geography:
        d.cities = List.of(_items);
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
    if (!mounted) return;
    Navigator.of(context).pop(true);
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
                decoration: const BoxDecoration(
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
  });

  final String title;
  final String accent;
  final String listLabel;
  final String addLabel;
  final String addHint;
  final bool useCountryPicker;
}
