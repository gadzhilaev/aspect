import 'package:flutter/material.dart';

import '../../models/onboarding_data.dart';
import '../../widgets/auth_widgets.dart';
import '../../widgets/onboarding_widgets.dart';

class CompanyVerifyScreen extends StatefulWidget {
  const CompanyVerifyScreen({
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
  State<CompanyVerifyScreen> createState() => _CompanyVerifyScreenState();
}

class _CompanyVerifyScreenState extends State<CompanyVerifyScreen>
    with AutomaticKeepAliveClientMixin {
  static const _roles = [
    'Операционный директор',
    'Генеральный директор',
    'Финансовый директор',
    'Коммерческий директор',
    'Руководитель подразделения',
    'Сотрудник',
  ];

  static const _sizes = [
    'Микро • до 15 сотрудников',
    'Малая • 15–100 сотрудников',
    'Средняя • 100–500 сотрудников',
    'Средняя • 500–1 000 сотрудников',
    'Крупная • 1 000+ сотрудников',
  ];

  late String _role;
  late String _size;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _role = _roles.contains(widget.data.role) ? widget.data.role : '';
    _size =
        _sizes.contains(widget.data.companySize) ? widget.data.companySize : '';
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncFooter());
  }

  @override
  void didUpdateWidget(covariant CompanyVerifyScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !oldWidget.isActive) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _syncFooter();
      });
    }
  }

  void _syncFooter() {
    widget.bindFooter?.call(
      label: 'Подтвердить данные',
      hint:
          'Эти сведения нужны, чтобы подобрать релевантные события и отраслевые источники.',
      onPressed: _continue,
    );
  }

  void _continue() {
    widget.data.role = _role;
    widget.data.companySize = _size;
    widget.onNext?.call();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final data = widget.data;
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OnboardingHeader(
          step: 1,
          showChrome: !widget.embedded,
          title: 'Проверьте данные',
          subtitle: 'Мы нашли открытую карточку компании',
        ),
        const SizedBox(height: 24),
        CompanyCard(
          name: data.companyName,
          inn: data.companyInn,
          city: data.companyCity,
          industry: data.companyIndustry,
        ),
        const SizedBox(height: 28),
        AuthDropdown(
          label: 'Ваша роль',
          value: _role,
          items: _roles,
          onChanged: (value) => setState(() => _role = value),
        ),
        const SizedBox(height: 20),
        AuthDropdown(
          label: 'Размер компании',
          value: _size,
          items: _sizes,
          onChanged: (value) => setState(() => _size = value),
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
      buttonLabel: 'Подтвердить данные',
      footerHint:
          'Эти сведения нужны, чтобы подобрать релевантные события и отраслевые источники.',
      onContinue: _continue,
      body: body,
    );
  }
}
