import 'package:flutter/material.dart';

import '../../models/onboarding_data.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/auth_widgets.dart';
import '../../widgets/onboarding_widgets.dart';

class ProductsScreen extends StatefulWidget {
  const ProductsScreen({
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
  State<ProductsScreen> createState() => _ProductsScreenState();
}

class _ProductsScreenState extends State<ProductsScreen>
    with AutomaticKeepAliveClientMixin {
  static const _borderColor = AppColors.border;
  static const _markets = [
    'Россия и СНГ',
    'Россия',
    'СНГ',
    'Европа',
    'Азия',
    'Мировой рынок',
    'Другое',
  ];

  late List<String> _products;
  late String _market;
  final _addController = TextEditingController();
  final _addFocus = FocusNode();
  bool _adding = false;

  static const _addBorder = AppColors.brandRed;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _products = List.of(widget.data.products);
    _market = _markets.contains(widget.data.mainMarket)
        ? widget.data.mainMarket
        : '';
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncFooter());
  }

  @override
  void didUpdateWidget(covariant ProductsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _syncFooter();
      });
    }
  }

  @override
  void dispose() {
    _addController.dispose();
    _addFocus.dispose();
    super.dispose();
  }

  void _syncFooter() {
    widget.bindFooter?.call(
      label: 'Продолжить',
      hint:
          'Можно добавить детали позже. Начните с двух-трёх ключевых продуктов.',
      onPressed: _continue,
    );
  }

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
      if (value.isNotEmpty) _products.add(value);
    });
  }

  void _removeProduct(int index) {
    setState(() => _products.removeAt(index));
  }

  void _continue() {
    widget.data.products = List.of(_products);
    widget.data.mainMarket = _market;
    widget.onNext?.call();
  }

  Widget _productField(int index) {
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
              _products[index],
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.bold(14 * s, color: AppColors.textInput),
            ),
          ),
          IconButton(
            onPressed: () => _removeProduct(index),
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

  Widget _addProductField() {
    final s = context.scale;
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
                onSubmitted: (_) => _commitAdd(),
                onEditingComplete: _commitAdd,
                style: AppTypography.bold(14 * s, color: AppColors.textInput),
                decoration: InputDecoration(
                  isCollapsed: true,
                  border: InputBorder.none,
                  hintText: 'Название продукта',
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
                alignment: Alignment.centerLeft,
                child: Text(
                  '+ Добавить продукт',
                  style: AppTypography.regular(15 * s, color: _addBorder),
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
          step: 3,
          showChrome: !widget.embedded,
          title: 'Что вы производите?',
          subtitle:
              'Добавьте ключевые продукты. Так мы поймём, какие изменения важны.',
        ),
        SizedBox(height: 28 * s),
        Text(
          'ПРОДУКТЫ',
          style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
        ),
        for (var i = 0; i < _products.length; i++) _productField(i),
        _addProductField(),
        SizedBox(height: 28 * s),
        AuthDropdown(
          label: 'Основной рынок',
          value: _market,
          items: _markets,
          onChanged: (value) => setState(() => _market = value),
        ),
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
          'Можно добавить детали позже. Начните с двух-трёх ключевых продуктов.',
      onContinue: _continue,
      body: body,
    );
  }
}
