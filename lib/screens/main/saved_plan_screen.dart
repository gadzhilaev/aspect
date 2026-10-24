import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import 'action_plan_screen.dart';
import 'confirm_plan_screen.dart';

Future<ConfirmPlanData?> openSavedPlanScreen(
  BuildContext context,
  ConfirmPlanData data,
) {
  return Navigator.of(context).push<ConfirmPlanData>(
    MaterialPageRoute<ConfirmPlanData>(
      builder: (_) => SavedPlanScreen(data: data),
    ),
  );
}

class SavedPlanScreen extends StatefulWidget {
  const SavedPlanScreen({super.key, required this.data});

  final ConfirmPlanData data;

  @override
  State<SavedPlanScreen> createState() => _SavedPlanScreenState();
}

class _SavedPlanScreenState extends State<SavedPlanScreen> {
  late ConfirmPlanData _data;
  late Set<int> _done;

  @override
  void initState() {
    super.initState();
    _data = widget.data;
    _done = Set<int>.from(widget.data.doneSteps);
  }

  ConfirmPlanData _snapshot() => _data.copyWith(doneSteps: Set<int>.from(_done));

  void _popWithData() => Navigator.of(context).pop(_snapshot());

  Future<void> _changePlan() async {
    final next = await openActionPlanScreen(
      context,
      eventTitle: _data.eventTitle,
    );
    if (next != null && mounted) {
      setState(() {
        _data = next;
        _done = {};
      });
    }
  }

  void _toggleStep(int index) {
    setState(() {
      if (_done.contains(index)) {
        _done.remove(index);
      } else {
        _done.add(index);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;
    const titleDark = Color.fromRGBO(24, 35, 44, 1);
    const heading = Color.fromRGBO(24, 27, 34, 1);
    final total = _data.steps.length;
    final doneCount = _done.length.clamp(0, total);

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
      ),
      child: PopScope(
        canPop: false,
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop) _popWithData();
        },
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
                      onTap: _popWithData,
                      behavior: HitTestBehavior.opaque,
                      child: Text(
                        '‹ Обсуждение',
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
                    padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 16 * s),
                    children: [
                      Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: 'План действий\n',
                              style: AppTypography.bold(
                                24.83 * s,
                                color: titleDark,
                              ),
                            ),
                            TextSpan(
                              text: _data.actionTitle,
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
                        'По событию «${_data.eventTitle}»',
                        style: AppTypography.regular(
                          13 * s,
                          color: AppColors.textMuted,
                        ),
                      ),
                      SizedBox(height: 22 * s),
                      Text(
                        'Выполнено $doneCount из $total',
                        style: AppTypography.bold(15.13 * s, color: heading),
                      ),
                      SizedBox(height: 8 * s),
                      _ProgressBar(
                        progress: total == 0 ? 0 : doneCount / total,
                      ),
                      SizedBox(height: 16 * s),
                      for (var i = 0; i < _data.steps.length; i++) ...[
                        if (i > 0) SizedBox(height: 10 * s),
                        _StepCard(
                          text: _data.steps[i],
                          done: _done.contains(i),
                          onToggle: () => _toggleStep(i),
                        ),
                      ],
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
                  child: Column(
                    children: [
                      SizedBox(
                        height: 52 * s,
                        width: double.infinity,
                        child: OutlinedButton(
                          onPressed: _changePlan,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppColors.brandRed,
                            backgroundColor: Colors.transparent,
                            side: BorderSide(
                              color: AppColors.brandRed,
                              width: 1.5 * s,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(13 * s),
                            ),
                          ),
                          child: Text(
                            'Сменить план',
                            style: AppTypography.bold(
                              14.06 * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                        ),
                      ),
                      SizedBox(height: 10 * s),
                      Text(
                        'Предыдущие выводы сохранены в истории обсуждения.',
                        textAlign: TextAlign.center,
                        style: AppTypography.regular(
                          13 * s,
                          color: AppColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ProgressBar extends StatelessWidget {
  const _ProgressBar({required this.progress});

  final double progress;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return ClipRRect(
      borderRadius: BorderRadius.circular(2 * s),
      child: SizedBox(
        height: 5 * s,
        child: Stack(
          fit: StackFit.expand,
          children: [
            const ColoredBox(color: Color(0xFFF5F6F8)),
            FractionallySizedBox(
              alignment: Alignment.centerLeft,
              widthFactor: progress.clamp(0.0, 1.0),
              child: const ColoredBox(color: AppColors.brandRed),
            ),
          ],
        ),
      ),
    );
  }
}

class _StepCard extends StatelessWidget {
  const _StepCard({
    required this.text,
    required this.done,
    required this.onToggle,
  });

  final String text;
  final bool done;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final border = done ? AppColors.brandRed : const Color(0xFFE3E6EB);

    return GestureDetector(
      onTap: onToggle,
      behavior: HitTestBehavior.opaque,
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.fromLTRB(14 * s, 14 * s, 14 * s, 14 * s),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(14 * s),
          border: Border.all(color: border, width: 1.5),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Container(
              width: 18 * s,
              height: 18 * s,
              decoration: BoxDecoration(
                color: done ? AppColors.brandRed : AppColors.surface,
                borderRadius: BorderRadius.circular(4 * s),
                border: done
                    ? null
                    : Border.all(color: const Color(0xFFE3E6EB), width: 1.5),
              ),
              alignment: Alignment.center,
              child: done
                  ? Icon(
                      Icons.check,
                      size: 12 * s,
                      color: AppColors.surface,
                    )
                  : null,
            ),
            SizedBox(width: 12 * s),
            Expanded(
              child: Text(
                text,
                style: AppTypography.regular(15.13 * s, color: Colors.black),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
