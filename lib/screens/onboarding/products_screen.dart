import 'package:flutter/material.dart';

import '../../models/onboarding_data.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
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
  static const _borderColor = Color(0xFFE3E5E3);
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

  static const _addBorder = Color(0xFFD92F37);

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
              _products[index],
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.bold(14, color: AppColors.textInput),
            ),
          ),
          IconButton(
            onPressed: () => _removeProduct(index),
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

  Widget _addProductField() {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: _adding
          ? Container(
              height: 50,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(16),
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
                style: AppTypography.bold(14, color: AppColors.textInput),
                decoration: InputDecoration(
                  isCollapsed: true,
                  border: InputBorder.none,
                  hintText: 'Название продукта',
                  hintStyle: AppTypography.regular(
                    14,
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
                height: 50,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: _addBorder),
                ),
                alignment: Alignment.centerLeft,
                child: Text(
                  '+ Добавить продукт',
                  style: AppTypography.regular(15, color: _addBorder),
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
          step: 3,
          showChrome: !widget.embedded,
          title: 'Что вы производите?',
          subtitle:
              'Добавьте ключевые продукты. Так мы поймём, какие изменения важны.',
        ),
        const SizedBox(height: 28),
        Text(
          'ПРОДУКТЫ',
          style: AppTypography.bold(12, color: AppColors.textSecondary),
        ),
        for (var i = 0; i < _products.length; i++) _productField(i),
        _addProductField(),
        const SizedBox(height: 28),
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
        padding: const EdgeInsets.fromLTRB(30, 16, 30, 16),
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
