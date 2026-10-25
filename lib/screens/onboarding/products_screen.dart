import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
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
  static Color get _borderColor => AppColors.border;
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
  final _customMarketController = TextEditingController();
  final _customMarketFocus = FocusNode();
  bool _adding = false;

  static const _addBorder = AppColors.brandRedLight;
  static const _otherMarket = 'Другое';

  bool get _isOtherMarket => _market == _otherMarket;

  bool get _marketReady {
    if (_market.trim().isEmpty) return false;
    if (_isOtherMarket) {
      return _customMarketController.text.trim().isNotEmpty;
    }
    return true;
  }

  bool get _canContinue => _products.isNotEmpty && _marketReady;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _products = List.of(widget.data.products);
    final stored = widget.data.mainMarket.trim();
    if (stored.isEmpty) {
      _market = '';
    } else if (_markets.contains(stored) && stored != _otherMarket) {
      _market = stored;
    } else {
      _market = _otherMarket;
      if (stored != _otherMarket) {
        _customMarketController.text = stored;
      }
    }
    _customMarketController.addListener(_onCustomMarketChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncFooter());
  }

  @override
  void didUpdateWidget(covariant ProductsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {}); // обновить заголовок по businessType
          _syncFooter();
        }
      });
    }
  }

  @override
  void dispose() {
    _customMarketController.removeListener(_onCustomMarketChanged);
    _addController.dispose();
    _addFocus.dispose();
    _customMarketController.dispose();
    _customMarketFocus.dispose();
    super.dispose();
  }

  void _onCustomMarketChanged() {
    if (mounted) _syncFooter();
  }

  void _syncFooter() {
    final l10n = context.l10n;
    widget.bindFooter?.call(
      label: l10n.continueAction,
      hint: l10n.onboardingProductsFooterHint,
      onPressed: _canContinue ? _continue : null,
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
    _syncFooter();
  }

  void _removeProduct(int index) {
    setState(() => _products.removeAt(index));
    _syncFooter();
  }

  void _onMarketChanged(String value) {
    setState(() => _market = value);
    if (value == _otherMarket) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _customMarketFocus.requestFocus();
      });
    } else {
      _customMarketController.clear();
    }
    _syncFooter();
  }

  void _continue() {
    if (!_canContinue) return;
    widget.data.products = List.of(_products);
    if (_isOtherMarket) {
      final custom = _customMarketController.text.trim();
      widget.data.mainMarket = custom.isEmpty ? _otherMarket : custom;
    } else {
      widget.data.mainMarket = _market;
    }
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

  Widget _addProductField({
    required String addLabel,
    required String hint,
  }) {
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
                textCapitalization: TextCapitalization.sentences,
                onSubmitted: (_) => _commitAdd(),
                onEditingComplete: _commitAdd,
                style: AppTypography.bold(14 * s, color: AppColors.textInput),
                decoration: InputDecoration(
                  isCollapsed: true,
                  border: InputBorder.none,
                  hintText: hint,
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
                  addLabel,
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
    final l10n = context.l10n;
    final copy = l10n.productsCopyForBusinessType(widget.data.businessType);
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 3,
          showChrome: !widget.embedded,
          title: copy.title,
          subtitle: copy.subtitle,
        ),
        SizedBox(height: 28 * s),
        Text(
          copy.section,
          style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
        ),
        for (var i = 0; i < _products.length; i++) _productField(i),
        _addProductField(addLabel: copy.add, hint: copy.hint),
        SizedBox(height: 28 * s),
        AuthDropdown(
          label: l10n.onboardingMainMarket,
          value: _market,
          items: _markets,
          onChanged: _onMarketChanged,
        ),
        if (_isOtherMarket) ...[
          SizedBox(height: 16 * s),
          AuthTextField(
            label: l10n.onboardingSpecifyMarket,
            controller: _customMarketController,
            focusNode: _customMarketFocus,
            hint: l10n.onboardingMarketHintExample,
            textInputAction: TextInputAction.done,
            keyboardType: TextInputType.text,
            textCapitalization: TextCapitalization.sentences,
          ),
        ],
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
      footerHint: l10n.onboardingProductsFooterHint,
      onContinue: _canContinue ? _continue : null,
      body: body,
    );
  }
}
