import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../models/onboarding_data.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

Future<void> openCounterpartiesScreen(BuildContext context) {
  return Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => const CounterpartiesScreen(),
    ),
  );
}

class CounterpartiesScreen extends StatefulWidget {
  const CounterpartiesScreen({super.key});

  @override
  State<CounterpartiesScreen> createState() => _CounterpartiesScreenState();
}

class _CounterpartiesScreenState extends State<CounterpartiesScreen> {
  static const _addBorder = Color.fromRGBO(217, 47, 55, 1);
  static const _titleSize = 24.83;

  OnboardingData? _profile;
  final List<_Supplier> _suppliers = [];
  final _addController = TextEditingController();
  final _addFocus = FocusNode();
  bool _adding = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final profile = await SessionStore.loadProfile() ?? OnboardingData();
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _suppliers
        ..clear()
        ..addAll([
          for (final name in profile.counterparties)
            if (name.trim().isNotEmpty)
              _Supplier(name: name.trim(), detail: 'Поставщик'),
        ]);
    });
  }

  Future<void> _persistSuppliers() async {
    final profile = _profile ?? OnboardingData();
    profile.counterparties = [
      for (final s in _suppliers) s.name,
    ];
    _profile = profile;
    await SessionStore.saveProfile(profile);
  }

  @override
  void dispose() {
    _addController.dispose();
    _addFocus.dispose();
    super.dispose();
  }

  void _startAdding() {
    setState(() => _adding = true);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _addFocus.requestFocus();
    });
  }

  Future<void> _commitAdd() async {
    final value = _addController.text.trim();
    _addController.clear();
    setState(() {
      _adding = false;
      if (value.isNotEmpty) {
        _suppliers.add(_Supplier(name: value, detail: 'Поставщик'));
      }
    });
    if (value.isNotEmpty) await _persistSuppliers();
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;

    return AnnotatedRegion<SystemUiOverlayStyle>(
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
                    onTap: () => Navigator.of(context).maybePop(),
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
                  padding: EdgeInsets.fromLTRB(
                    hPad,
                    10 * s,
                    hPad,
                    24 * s + bottom,
                  ),
                  children: [
                    Text(
                      'Контрагенты и связи',
                      style: AppTypography.medium(
                        _titleSize * s,
                        color: AppColors.textInput,
                      ),
                    ),
                    SizedBox(height: 4 * s),
                    Text(
                      'Разные типы связей — разные основания',
                      style: AppTypography.medium(
                        _titleSize * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                    SizedBox(height: 28 * s),
                    _sectionLabel(context, 'Платежные связи'),
                    SizedBox(height: 10 * s),
                    _InfoCard(
                      title: 'Организация U_1042',
                      body:
                          'Компания перечисляла средства.\nЧисло платежей: 12 · период неизвестен',
                      linkLabel: 'Пример платёжной записи',
                      onLinkTap: () {},
                    ),
                    SizedBox(height: 12 * s),
                    _InfoCard(
                      title: 'Организация U_1042',
                      body:
                          'Компания перечисляла средства.\nЧисло платежей: 12 · период неизвестен',
                      linkLabel: 'Пример платёжной записи',
                      onLinkTap: () {},
                    ),
                    SizedBox(height: 24 * s),
                    _sectionLabel(context, 'Группа компаний'),
                    SizedBox(height: 10 * s),
                    const _InfoCard(
                      title: 'Группа G_17',
                      body:
                          'Принадлежность по данным источника. Операционная зависимость не установлена.',
                    ),
                    SizedBox(height: 24 * s),
                    _sectionLabel(context, 'Указанные поставщики'),
                    SizedBox(height: 10 * s),
                    for (var i = 0; i < _suppliers.length; i++) ...[
                      if (i > 0) SizedBox(height: 12 * s),
                      _InfoCard(
                        title: _suppliers[i].name,
                        body: _suppliers[i].detail.isEmpty
                            ? 'Поставщик'
                            : _suppliers[i].detail,
                      ),
                    ],
                    SizedBox(height: 12 * s),
                    _adding
                        ? Container(
                            height: 50 * s,
                            padding: EdgeInsets.symmetric(horizontal: 16 * s),
                            decoration: BoxDecoration(
                              color: AppColors.surface,
                              borderRadius: BorderRadius.circular(16 * s),
                              border: Border.all(color: _addBorder, width: 1),
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
                              style: AppTypography.bold(
                                13 * s,
                                color: AppColors.textInput,
                              ),
                              decoration: InputDecoration(
                                isCollapsed: true,
                                border: InputBorder.none,
                                hintText: 'Название поставщика',
                                hintStyle: AppTypography.regular(
                                  13 * s,
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
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: AppColors.surface,
                                borderRadius: BorderRadius.circular(16 * s),
                                border: Border.all(color: _addBorder, width: 1),
                              ),
                              child: Text(
                                '+ Добавить поставщика',
                                style: AppTypography.bold(
                                  13 * s,
                                  color: _addBorder,
                                ),
                              ),
                            ),
                          ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sectionLabel(BuildContext context, String text) {
    final s = context.scale;
    return Text(
      text,
      style: AppTypography.bold(12 * s, color: AppColors.textMuted),
    );
  }
}

class _Supplier {
  const _Supplier({required this.name, required this.detail});

  final String name;
  final String detail;
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({
    required this.title,
    required this.body,
    this.linkLabel,
    this.onLinkTap,
  });

  final String title;
  final String body;
  final String? linkLabel;
  final VoidCallback? onLinkTap;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 16 * s, 14 * s),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(color: AppColors.border, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: AppTypography.medium(13 * s, color: AppColors.textInput),
          ),
          SizedBox(height: 6 * s),
          Text(
            body,
            style: AppTypography.regular(12 * s, color: AppColors.textMuted),
          ),
          if (linkLabel != null) ...[
            SizedBox(height: 10 * s),
            GestureDetector(
              onTap: onLinkTap,
              behavior: HitTestBehavior.opaque,
              child: Text(
                linkLabel!,
                style: AppTypography.bold(13 * s, color: AppColors.brandRed),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
