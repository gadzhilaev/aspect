import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../api/companies_api.dart';
import '../../l10n/app_localizations.dart';
import '../../models/onboarding_data.dart';
import '../../navigation/app_page_route.dart';
import '../../services/auth_store.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

Future<void> openCounterpartiesScreen(BuildContext context) {
  return Navigator.of(context).push(
    AppPageRoute(builder: (_) => const CounterpartiesScreen()),
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
  final _listKey = GlobalKey();
  bool _adding = false;
  bool _loading = true;
  bool _alfaDemo = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final alfa = await SessionStore.isAlfaDemo();
    final profile = await SessionStore.loadProfile() ?? OnboardingData();
    final names = <String>{
      for (final name in profile.counterparties)
        if (name.trim().isNotEmpty) name.trim(),
    };

    if (!alfa) {
      final companyId = await AuthStore.companyId();
      if (companyId != null && companyId.isNotEmpty) {
        try {
          final apiProfile = await CompaniesApi.instance.getProfile(companyId);
          final nodes = apiProfile['nodes'];
          if (nodes is List) {
            for (final n in nodes) {
              if (n is! Map) continue;
              final type = (n['node_type'] ?? '').toString();
              if (type != 'supplier' && type != 'counterparty') continue;
              final name = (n['name'] ?? '').toString().trim();
              if (name.isNotEmpty) names.add(name);
            }
          }
        } catch (_) {}
      }
    }

    if (!mounted) return;
    setState(() {
      _alfaDemo = alfa;
      _profile = profile;
      _suppliers
        ..clear()
        ..addAll([for (final name in names) _Supplier(name: name, detail: '')]);
      _loading = false;
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
      if (!mounted) return;
      _addFocus.requestFocus();
      Scrollable.ensureVisible(
        _listKey.currentContext ?? context,
        duration: const Duration(milliseconds: 200),
        alignment: 1.0,
      );
    });
  }

  Future<void> _commitAdd() async {
    final value = _addController.text.trim();
    if (value.isEmpty) {
      // Не закрываем поле из‑за случайной потери фокуса.
      return;
    }
    _addController.clear();
    setState(() {
      _adding = false;
      _suppliers.add(_Supplier(name: value, detail: ''));
    });
    await _persistSuppliers();
  }

  void _cancelAdd() {
    _addController.clear();
    _addFocus.unfocus();
    setState(() => _adding = false);
  }

  Future<void> _editSupplier(int index) async {
    final current = _suppliers[index];
    final controller = TextEditingController(text: current.name);
    final next = await showDialog<String>(
      context: context,
      builder: (ctx) {
        final s = ctx.scale;
        final l10n = ctx.l10n;
        return AlertDialog(
          title: Text(
            l10n.supplierRole,
            style: AppTypography.bold(16 * s, color: AppColors.textInput),
          ),
          content: TextField(
            controller: controller,
            autofocus: true,
            textCapitalization: TextCapitalization.sentences,
            cursorColor: AppColors.brandRed,
            style: AppTypography.medium(14 * s, color: AppColors.textInput),
            decoration: InputDecoration(
              hintText: l10n.supplierNameHint,
              hintStyle:
                  AppTypography.regular(14 * s, color: AppColors.textHint),
              focusedBorder: UnderlineInputBorder(
                borderSide: BorderSide(color: AppColors.brandRed),
              ),
            ),
            onSubmitted: (v) => Navigator.of(ctx).pop(v.trim()),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: Text(
                l10n.cancel,
                style: AppTypography.medium(14 * s, color: AppColors.textMuted),
              ),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(controller.text.trim()),
              child: Text(
                l10n.save,
                style: AppTypography.bold(14 * s, color: AppColors.brandRed),
              ),
            ),
          ],
        );
      },
    );
    controller.dispose();
    if (!mounted || next == null) return;
    if (next.isEmpty) {
      setState(() => _suppliers.removeAt(index));
      await _persistSuppliers();
      return;
    }
    setState(() => _suppliers[index] = _Supplier(name: next, detail: ''));
    await _persistSuppliers();
  }

  Future<void> _deleteSupplier(int index) async {
    setState(() => _suppliers.removeAt(index));
    await _persistSuppliers();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
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
                      l10n.settingsBackCompany,
                      style: AppTypography.regular(
                        15 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                  ),
                ),
              ),
              Expanded(
                child: _loading
                    ? const Center(
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : ListView(
                        key: _listKey,
                        padding: EdgeInsets.fromLTRB(
                          hPad,
                          10 * s,
                          hPad,
                          24 * s + bottom,
                        ),
                        children: [
                          Text(
                            l10n.counterpartiesAndLinks,
                            style: AppTypography.medium(
                              _titleSize * s,
                              color: AppColors.textInput,
                            ),
                          ),
                          SizedBox(height: 4 * s),
                          Text(
                            l10n.counterpartiesSubtitle,
                            style: AppTypography.medium(
                              _titleSize * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                          SizedBox(height: 28 * s),
                          _sectionLabel(context, l10n.paymentLinks),
                          SizedBox(height: 10 * s),
                          if (_alfaDemo) ...[
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
                          ] else
                            _EmptyHint(text: l10n.noPaymentLinksYet),
                          SizedBox(height: 24 * s),
                          _sectionLabel(context, l10n.companyGroupSection),
                          SizedBox(height: 10 * s),
                          if (_alfaDemo)
                            const _InfoCard(
                              title: 'Группа G_17',
                              body:
                                  'Принадлежность по данным источника. Операционная зависимость не установлена.',
                            )
                          else
                            _EmptyHint(text: l10n.noCompanyGroupYet),
                          SizedBox(height: 24 * s),
                          _sectionLabel(context, l10n.listedSuppliers),
                          SizedBox(height: 10 * s),
                          if (_suppliers.isEmpty)
                            _EmptyHint(text: l10n.noSuppliersYet),
                          for (var i = 0; i < _suppliers.length; i++) ...[
                            if (i > 0) SizedBox(height: 12 * s),
                            _InfoCard(
                              title: _suppliers[i].name,
                              body: _suppliers[i].detail.isEmpty
                                  ? l10n.supplierRole
                                  : _suppliers[i].detail,
                              onTap: () => _editSupplier(i),
                              trailing: IconButton(
                                onPressed: () => _deleteSupplier(i),
                                icon: Icon(
                                  Icons.close,
                                  size: 18 * s,
                                  color: AppColors.textMuted,
                                ),
                                tooltip: l10n.delete,
                              ),
                            ),
                          ],
                          SizedBox(height: 12 * s),
                          _adding
                              ? Container(
                                  height: 50 * s,
                                  padding: EdgeInsets.only(left: 16 * s),
                                  decoration: BoxDecoration(
                                    color: AppColors.surface,
                                    borderRadius: BorderRadius.circular(16 * s),
                                    border: Border.all(
                                      color: _addBorder,
                                      width: 1,
                                    ),
                                  ),
                                  child: Row(
                                    children: [
                                      Expanded(
                                        child: TextField(
                                          controller: _addController,
                                          focusNode: _addFocus,
                                          cursorColor: _addBorder,
                                          textInputAction: TextInputAction.done,
                                          textCapitalization:
                                              TextCapitalization.sentences,
                                          onSubmitted: (_) => _commitAdd(),
                                          style: AppTypography.bold(
                                            13 * s,
                                            color: AppColors.textInput,
                                          ),
                                          decoration: InputDecoration(
                                            isCollapsed: true,
                                            border: InputBorder.none,
                                            hintText: l10n.supplierNameHint,
                                            hintStyle: AppTypography.regular(
                                              13 * s,
                                              color: AppColors.textHint,
                                            ),
                                            contentPadding: EdgeInsets.zero,
                                          ),
                                        ),
                                      ),
                                      IconButton(
                                        onPressed: _cancelAdd,
                                        icon: Icon(
                                          Icons.close,
                                          size: 18 * s,
                                          color: AppColors.textMuted,
                                        ),
                                      ),
                                      IconButton(
                                        onPressed: _commitAdd,
                                        icon: Icon(
                                          Icons.check,
                                          size: 20 * s,
                                          color: _addBorder,
                                        ),
                                      ),
                                    ],
                                  ),
                                )
                              : Material(
                                  color: Colors.transparent,
                                  child: InkWell(
                                    onTap: _startAdding,
                                    borderRadius: BorderRadius.circular(16 * s),
                                    child: Container(
                                      height: 50 * s,
                                      alignment: Alignment.center,
                                      decoration: BoxDecoration(
                                        color: AppColors.surface,
                                        borderRadius:
                                            BorderRadius.circular(16 * s),
                                        border: Border.all(
                                          color: _addBorder,
                                          width: 1,
                                        ),
                                      ),
                                      child: Text(
                                        l10n.addSupplier,
                                        style: AppTypography.bold(
                                          13 * s,
                                          color: _addBorder,
                                        ),
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

class _EmptyHint extends StatelessWidget {
  const _EmptyHint({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(16 * s, 14 * s, 16 * s, 14 * s),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(color: AppColors.border, width: 1),
      ),
      child: Text(
        text,
        style: AppTypography.regular(12 * s, color: AppColors.textMuted),
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({
    required this.title,
    required this.body,
    this.linkLabel,
    this.onLinkTap,
    this.onTap,
    this.trailing,
  });

  final String title;
  final String body;
  final String? linkLabel;
  final VoidCallback? onLinkTap;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16 * s),
        child: Container(
          width: double.infinity,
          padding: EdgeInsets.fromLTRB(16 * s, 16 * s, 8 * s, 14 * s),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16 * s),
            border: Border.all(color: AppColors.border, width: 1),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Padding(
                  padding: EdgeInsets.only(right: 8 * s),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: AppTypography.medium(
                          13 * s,
                          color: AppColors.textInput,
                        ),
                      ),
                      SizedBox(height: 6 * s),
                      Text(
                        body,
                        style: AppTypography.regular(
                          12 * s,
                          color: AppColors.textMuted,
                        ),
                      ),
                      if (linkLabel != null) ...[
                        SizedBox(height: 10 * s),
                        GestureDetector(
                          onTap: onLinkTap,
                          behavior: HitTestBehavior.opaque,
                          child: Text(
                            linkLabel!,
                            style: AppTypography.bold(
                              13 * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              ?trailing,
            ],
          ),
        ),
      ),
    );
  }
}
