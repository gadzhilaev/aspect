import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/app_localizations.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
Future<void> openFinanceScreen(BuildContext context) {
  return Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => const FinanceScreen(),
    ),
  );
}

class FinanceScreen extends StatelessWidget {
  const FinanceScreen({super.key});

  static const _statusGreen = Color.fromRGBO(11, 138, 106, 1);
  static const _titleSize = 24.83;

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
                child: ListView(
                  padding: EdgeInsets.fromLTRB(hPad, 10 * s, hPad, 24 * s),
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
                          value: 'Есть',
                          valueColor: _statusGreen,
                        ),
                        _KvRow(
                          label: 'Депозит',
                          value: 'Нет по источнику',
                        ),
                        _KvRow(
                          label: 'Лизинг',
                          value: 'Неизвестно',
                        ),
                        _KvRow(
                          label: 'Факторинг',
                          value: 'Данные расходятся',
                          valueColor: AppColors.brandRed,
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
                          value: 'Неизвестно',
                        ),
                        _KvRow(
                          label: 'Доля плавающей ставки',
                          value: 'Неизвестно',
                        ),
                        _KvRow(
                          label: 'Валютные платежи',
                          value: 'Неизвестно',
                        ),
                      ],
                    ),
                    SizedBox(height: 16 * s),
                    Container(
                      padding: EdgeInsets.all(16 * s),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(16 * s),
                        border: Border.all(color: AppColors.border, width: 1),
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
  _KvRow({
    required this.label,
    required this.value,
    Color? valueColor,
  }) : valueColor = valueColor ?? AppColors.textPrimary;

  final String label;
  final String value;
  final Color valueColor;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: 16 * s, vertical: 14 * s),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: AppTypography.regular(12 * s, color: AppColors.textMuted),
            ),
          ),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: AppTypography.medium(12 * s, color: valueColor),
            ),
          ),
        ],
      ),
    );
  }
}
