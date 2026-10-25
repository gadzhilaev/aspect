import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../models/onboarding_data.dart';
import '../../theme/design_scale.dart';
import '../../widgets/onboarding_widgets.dart';

class BusinessTypeScreen extends StatefulWidget {
  const BusinessTypeScreen({
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
  State<BusinessTypeScreen> createState() => _BusinessTypeScreenState();
}

class _BusinessTypeScreenState extends State<BusinessTypeScreen>
    with AutomaticKeepAliveClientMixin {
  static const _options = [
    ('Производство', 'Оборудование и комплектующие'),
    ('Торговля', 'Оптовая и розничная'),
    ('Финансы', 'Банк, страхование, инвестиции'),
    ('Технологии', 'ПО, связь, цифровые сервисы'),
    ('Другое', 'Укажу свой вариант'),
  ];

  late String _selected;

  @override
  bool get wantKeepAlive => true;

  bool get _canContinue =>
      _options.any((e) => e.$1 == _selected);

  @override
  void initState() {
    super.initState();
    _selected = widget.data.businessType;
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncFooter());
  }

  @override
  void didUpdateWidget(covariant BusinessTypeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _syncFooter();
      });
    }
  }

  void _syncFooter() {
    widget.bindFooter?.call(
      label: context.l10n.continueAction,
      onPressed: _canContinue ? _continue : null,
    );
  }

  void _continue() {
    if (!_canContinue) return;
    final option = _options.firstWhere((e) => e.$1 == _selected);
    widget.data.businessType = option.$1;
    widget.data.businessTypeSubtitle = option.$2;
    widget.onNext?.call();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final s = context.scale;
    final l10n = context.l10n;
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 2,
          showChrome: !widget.embedded,
          title: l10n.onboardingBusinessTitle,
          subtitle: l10n.onboardingBusinessSubtitle,
        ),
        SizedBox(height: 24 * s),
        for (final option in _options) ...[
          SelectableOptionTile(
            title: option.$1,
            subtitle: option.$2,
            selected: _selected == option.$1,
            onTap: () {
              setState(() => _selected = option.$1);
              _syncFooter();
            },
          ),
          SizedBox(height: 10 * s),
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
      onContinue: _canContinue ? _continue : null,
      body: body,
    );
  }
}
