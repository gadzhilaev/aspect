import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/app_localizations.dart';
import '../../navigation/app_page_route.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

class ConfirmPlanData {
  ConfirmPlanData({
    required this.actionTitle,
    required this.eventTitle,
    this.steps = const [
      'Собрать условия действующих кредитов',
      'Уточнить даты пересмотра ставок',
      'Вернуться к сравнению вариантов',
    ],
    this.reason =
        'Сначала уточняем фактические условия, чтобы не выбирать решение вслепую.',
    Set<int>? doneSteps,
  }) : doneSteps = doneSteps ?? {};

  final String actionTitle;
  final String eventTitle;
  final List<String> steps;
  final String reason;
  final Set<int> doneSteps;

  ConfirmPlanData copyWith({
    String? actionTitle,
    String? eventTitle,
    List<String>? steps,
    String? reason,
    Set<int>? doneSteps,
  }) {
    return ConfirmPlanData(
      actionTitle: actionTitle ?? this.actionTitle,
      eventTitle: eventTitle ?? this.eventTitle,
      steps: steps ?? this.steps,
      reason: reason ?? this.reason,
      doneSteps: doneSteps ?? Set<int>.from(this.doneSteps),
    );
  }
}

Future<bool?> openConfirmPlanScreen(
  BuildContext context,
  ConfirmPlanData data,
) {
  return Navigator.of(context).push<bool>(
    AppPageRoute<bool>(
      builder: (_) => ConfirmPlanScreen(data: data),
    ),
  );
}

class ConfirmPlanScreen extends StatelessWidget {
  const ConfirmPlanScreen({super.key, required this.data});

  final ConfirmPlanData data;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;
    const titleDark = Color.fromRGBO(24, 35, 44, 1);
    const heading = Color.fromRGBO(24, 27, 34, 1);

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
                    onTap: () => Navigator.of(context).maybePop(false),
                    behavior: HitTestBehavior.opaque,
                    child: Text(
                      '‹ ${l10n.actionOptions}',
                      style: AppTypography.regular(
                        15 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ),
                ),
              ),
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 16 * s),
                  children: [
                    Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: '${l10n.confirmPlan}\n',
                            style: AppTypography.bold(
                              24.83 * s,
                              color: titleDark,
                            ),
                          ),
                          TextSpan(
                            text: data.actionTitle,
                            style: AppTypography.bold(
                              24.83 * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                        ],
                      ),
                    ),
                    SizedBox(height: 10 * s),
                    Text(
                      l10n.planForEvent(data.eventTitle),
                      style: AppTypography.regular(
                        13 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                    SizedBox(height: 20 * s),
                    Container(
                      width: double.infinity,
                      padding: EdgeInsets.fromLTRB(
                        16 * s,
                        18 * s,
                        16 * s,
                        18 * s,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(12 * s),
                        border: Border.all(
                          color: AppColors.textMuted.withValues(alpha: 0.22),
                          width: 1,
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            l10n.actionPlan,
                            style: AppTypography.bold(
                              15.13 * s,
                              color: heading,
                            ),
                          ),
                          SizedBox(height: 16 * s),
                          for (var i = 0; i < data.steps.length; i++) ...[
                            if (i > 0) SizedBox(height: 14 * s),
                            Text(
                              data.steps[i],
                              style: AppTypography.regular(
                                15.13 * s,
                                color: Colors.black,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    SizedBox(height: 24 * s),
                    Text(
                      l10n.whyThisOption,
                      style: AppTypography.bold(
                        15.13 * s,
                        color: heading,
                      ),
                    ),
                    SizedBox(height: 8 * s),
                    Text(
                      data.reason,
                      style: AppTypography.regular(
                        15.13 * s,
                        color: Colors.black,
                      ),
                    ),
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
                child: SizedBox(
                  height: 52 * s,
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: () => Navigator.of(context).pop(true),
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.brandRed,
                      foregroundColor: AppColors.surface,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(13 * s),
                      ),
                    ),
                    child: Text(
                      l10n.confirmAndSave,
                      style: AppTypography.bold(
                        14.06 * s,
                        color: AppColors.surface,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
