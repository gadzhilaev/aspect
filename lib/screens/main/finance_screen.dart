import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../api/companies_api.dart';
import '../../l10n/app_localizations.dart';
import '../../navigation/app_page_route.dart';
import '../../services/auth_store.dart';
import '../../services/session_store.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

Future<void> openFinanceScreen(BuildContext context) {
  return Navigator.of(context).push(
    AppPageRoute(builder: (_) => const FinanceScreen()),
  );
}

class FinanceScreen extends StatefulWidget {
  const FinanceScreen({super.key});

  @override
  State<FinanceScreen> createState() => _FinanceScreenState();
}

class _FinanceScreenState extends State<FinanceScreen> {
  static const _statusGreen = Color.fromRGBO(11, 138, 106, 1);
  static const _titleSize = 24.83;

  bool _loading = true;
  bool _alfaDemo = false;
  Map<String, dynamic> _finance = const {};
  List<String> _currencies = const [];
  Map<String, String> _productStatus = const {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  String _markLabel(String status, AppLocalizations l10n) {
    switch (status) {
      case 'true':
        return 'Есть';
      case 'false':
        return 'Нет по источнику';
      case 'conflict':
        return 'Данные расходятся';
      default:
        return l10n.unknownValue;
    }
  }

  Color? _markColor(String status) {
    switch (status) {
      case 'true':
        return _statusGreen;
      case 'conflict':
        return AppColors.brandRed;
      default:
        return null;
    }
  }

  Future<void> _load() async {
    final alfa = await SessionStore.isAlfaDemo();
    Map<String, dynamic> finance = {};
    List<String> currencies = [];
    final products = <String, String>{
      'credit': 'unknown',
      'deposit': 'unknown',
      'leasing': 'unknown',
      'factoring': 'unknown',
    };

    if (alfa) {
      products['credit'] = 'true';
      products['deposit'] = 'false';
      products['leasing'] = 'unknown';
      products['factoring'] = 'conflict';
    } else {
      final companyId = await AuthStore.companyId();
      if (companyId != null && companyId.isNotEmpty) {
        try {
          final profile = await CompaniesApi.instance.getProfile(companyId);
          final settings = profile['settings'];
          if (settings is Map) {
            final of = settings['optional_finance'];
            if (of is Map) {
              finance = Map<String, dynamic>.from(of);
            }
            final pc = settings['purchase_currencies'];
            if (pc is List) {
              currencies = [
                for (final c in pc)
                  if (c.toString().trim().isNotEmpty) c.toString().trim(),
              ];
            }
          }
        } catch (_) {}
        try {
          final ctx = await CompaniesApi.instance.getContext(companyId);
          final caseCtx = ctx['case_context'];
          if (caseCtx is Map) {
            final caseProfile = caseCtx['profile'];
            if (caseProfile is Map) {
              final marks = caseProfile['products'];
              if (marks is List) {
                for (final m in marks) {
                  if (m is! Map) continue;
                  final code = (m['code'] ?? '').toString().toUpperCase();
                  final status = (m['status'] ?? 'unknown').toString();
                  if (code == 'LOA') products['credit'] = status;
                  if (code == 'DEP') products['deposit'] = status;
                  if (code == 'LEA') products['leasing'] = status;
                }
              }
              final factoring = caseProfile['factoring'];
              if (factoring is Map) {
                products['factoring'] =
                    (factoring['status'] ?? 'unknown').toString();
              }
            }
          }
        } catch (_) {}
      }
    }

    if (!mounted) return;
    setState(() {
      _alfaDemo = alfa;
      _finance = finance;
      _currencies = currencies;
      _productStatus = products;
      _loading = false;
    });
  }

  String _fmt(dynamic raw, String fallback) {
    if (raw == null) return fallback;
    final s = raw.toString().trim();
    return s.isEmpty ? fallback : s;
  }

  String _money(dynamic raw, AppLocalizations l10n) {
    if (raw == null) return l10n.unknownValue;
    if (raw is num) {
      final n = raw.toDouble();
      if (n == n.roundToDouble()) return n.toInt().toString();
      return n.toStringAsFixed(2);
    }
    final s = raw.toString().trim();
    return s.isEmpty ? l10n.unknownValue : s;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;
    final unknown = l10n.unknownValue;

    final credit = _productStatus['credit'] ?? 'unknown';
    final deposit = _productStatus['deposit'] ?? 'unknown';
    final leasing = _productStatus['leasing'] ?? 'unknown';
    final factoring = _productStatus['factoring'] ?? 'unknown';

    // Без кейс-профиля и без демо — честно «нет данных по источнику».
    final hasCaseMarks = !_alfaDemo &&
        (credit != 'unknown' ||
            deposit != 'unknown' ||
            leasing != 'unknown' ||
            factoring != 'unknown');
    String productValue(String status) {
      if (_alfaDemo || hasCaseMarks) return _markLabel(status, l10n);
      return l10n.noSourceData;
    }

    final debt = _money(_finance['debt_amount'], l10n);
    final debtUnit = _fmt(_finance['debt_amount_unit'], '');
    final debtLabel = debt == unknown
        ? unknown
        : (debtUnit.isEmpty ? debt : '$debt $debtUnit');
    final floating = _finance['floating_rate_share_percent'];
    final floatingLabel = floating == null
        ? unknown
        : '${_money(floating, l10n)}%';
    final fxLabel = _currencies.isNotEmpty
        ? _currencies.join(', ')
        : (_finance['fx_purchase_volume'] != null
            ? _money(_finance['fx_purchase_volume'], l10n)
            : unknown);

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
                        padding:
                            EdgeInsets.fromLTRB(hPad, 10 * s, hPad, 24 * s),
                        children: [
                          Text(
                            l10n.finance,
                            style: AppTypography.medium(
                              _titleSize * s,
                              color: AppColors.textInput,
                            ),
                          ),
                          SizedBox(height: 4 * s),
                          Text(
                            l10n.financeSubtitle,
                            style: AppTypography.medium(
                              _titleSize * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                          SizedBox(height: 28 * s),
                          Padding(
                            padding: EdgeInsets.only(left: 10 * s),
                            child: Text(
                              l10n.productsFromSource,
                              style: AppTypography.bold(
                                12 * s,
                                color: AppColors.textMuted,
                              ),
                            ),
                          ),
                          SizedBox(height: 10 * s),
                          _Card(
                            children: [
                              _KvRow(
                                label: 'Кредит',
                                value: productValue(credit),
                                valueColor: (_alfaDemo || hasCaseMarks)
                                    ? _markColor(credit)
                                    : null,
                              ),
                              _KvRow(
                                label: 'Депозит',
                                value: productValue(deposit),
                                valueColor: (_alfaDemo || hasCaseMarks)
                                    ? _markColor(deposit)
                                    : null,
                              ),
                              _KvRow(
                                label: 'Лизинг',
                                value: productValue(leasing),
                                valueColor: (_alfaDemo || hasCaseMarks)
                                    ? _markColor(leasing)
                                    : null,
                              ),
                              _KvRow(
                                label: 'Факторинг',
                                value: productValue(factoring),
                                valueColor: (_alfaDemo || hasCaseMarks)
                                    ? _markColor(factoring)
                                    : null,
                              ),
                            ],
                          ),
                          SizedBox(height: 24 * s),
                          Padding(
                            padding: EdgeInsets.only(left: 10 * s),
                            child: Text(
                              l10n.forFinanceScenarios,
                              style: AppTypography.bold(
                                12 * s,
                                color: AppColors.textMuted,
                              ),
                            ),
                          ),
                          SizedBox(height: 10 * s),
                          _Card(
                            children: [
                              _KvRow(
                                label: 'Сумма долга',
                                value: debtLabel,
                              ),
                              _KvRow(
                                label: 'Доля плавающей ставки',
                                value: floatingLabel,
                              ),
                              _KvRow(
                                label: 'Валютные платежи',
                                value: fxLabel,
                              ),
                            ],
                          ),
                          SizedBox(height: 16 * s),
                          Container(
                            padding: EdgeInsets.all(16 * s),
                            decoration: BoxDecoration(
                              color: AppColors.surface,
                              borderRadius: BorderRadius.circular(16 * s),
                              border: Border.all(
                                color: AppColors.border,
                                width: 1,
                              ),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  l10n.noMonetaryCalcYet,
                                  style: AppTypography.medium(
                                    13 * s,
                                    color: AppColors.textInput,
                                  ),
                                ),
                                SizedBox(height: 6 * s),
                                Text(
                                  l10n.noMonetaryCalcBody,
                                  style: AppTypography.regular(
                                    12 * s,
                                    color: AppColors.textMuted,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          SizedBox(height: 28 * s),
                          SizedBox(
                            height: 52 * s,
                            width: double.infinity,
                            child: FilledButton(
                              onPressed: () {},
                              style: FilledButton.styleFrom(
                                backgroundColor: AppColors.brandRed,
                                foregroundColor: AppColors.surface,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(16 * s),
                                ),
                                textStyle: AppTypography.bold(
                                  14.06 * s,
                                  color: AppColors.surface,
                                ),
                              ),
                              child: Text(
                                l10n.supplementFinanceParams,
                                textAlign: TextAlign.center,
                                style: AppTypography.bold(
                                  14.06 * s,
                                  color: AppColors.surface,
                                ),
                              ),
                            ),
                          ),
                          SizedBox(height: bottom),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16 * s),
        border: Border.all(color: AppColors.border, width: 1),
      ),
      child: Column(children: children),
    );
  }
}

class _KvRow extends StatelessWidget {
  const _KvRow({
    required this.label,
    required this.value,
    this.valueColor,
  });

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: 16 * s, vertical: 14 * s),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 150 * s,
            child: Text(
              label,
              style: AppTypography.regular(12 * s, color: AppColors.textMuted),
            ),
          ),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.left,
              style: AppTypography.medium(
                12 * s,
                color: valueColor ?? AppColors.textPrimary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
