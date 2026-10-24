import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../l10n/app_localizations.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';
import 'action_plan_screen.dart';
import 'bank_material_screen.dart';
import 'confirm_plan_screen.dart';
import 'saved_plan_screen.dart';

class ChatScreenData {
  const ChatScreenData({
    required this.title,
    required this.meta,
    required this.level,
    this.backLabel,
  });

  final String title;
  final String meta;
  final ImpactLevel level;
  final String? backLabel;
}

const chinaExportChat = ChatScreenData(
  title: 'Китай ограничивает экспорт электроники',
  meta: 'Высокое влияние · Сегодня 08:24',
  level: ImpactLevel.high,
);

Future<void> openChatScreen(
  BuildContext context,
  ChatScreenData data,
) {
  return Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => ChatScreen(data: data),
    ),
  );
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, required this.data});

  final ChatScreenData data;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  ConfirmPlanData? _savedPlan;

  Future<void> _openScenarios() async {
    final plan = await openActionPlanScreen(
      context,
      eventTitle: widget.data.title,
    );
    if (plan != null && mounted) {
      setState(() => _savedPlan = plan);
    }
  }

  Future<void> _openSavedPlan() async {
    final plan = _savedPlan;
    if (plan == null) return;
    final updated = await openSavedPlanScreen(context, plan);
    if (updated != null && mounted) {
      setState(() => _savedPlan = updated);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    final accent = ImpactColors.accent(widget.data.level);
    const hPad = AppColors.screenPadding;
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final backLabel = widget.data.backLabel ?? l10n.navScenarios;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppColors.systemOverlay,
      child: Scaffold(
        backgroundColor: AppColors.surface,
        body: SafeArea(
          bottom: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Material(
                color: AppColors.surface,
                child: Padding(
                  padding: EdgeInsets.fromLTRB(hPad * s, 8 * s, hPad * s, 0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      GestureDetector(
                        onTap: () => Navigator.of(context).maybePop(),
                        behavior: HitTestBehavior.opaque,
                        child: Text(
                          '‹ $backLabel',
                          style: AppTypography.regular(
                            15 * s,
                            color: AppColors.brandRed,
                          ),
                        ),
                      ),
                      SizedBox(height: 14 * s),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Container(
                            width: 3.8 * s,
                            height: 40 * s,
                            decoration: BoxDecoration(
                              color: accent,
                              borderRadius: BorderRadius.circular(2 * s),
                            ),
                          ),
                          SizedBox(width: 12 * s),
                          Expanded(
                            child: Text(
                              widget.data.title,
                              style: AppTypography.bold(
                                18.88 * s,
                                color: AppColors.textInput,
                              ),
                            ),
                          ),
                        ],
                      ),
                      SizedBox(height: 10 * s),
                      IntrinsicWidth(
                        child: Container(
                          height: 25 * s,
                          padding: EdgeInsets.symmetric(horizontal: 6 * s),
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: AppColors.brandRed,
                            borderRadius: BorderRadius.circular(6 * s),
                          ),
                          child: Text(
                            l10n.aiExplanation,
                            softWrap: false,
                            style: AppTypography.medium(
                              9.4 * s,
                              color: AppColors.surface,
                            ),
                          ),
                        ),
                      ),
                      SizedBox(height: 14 * s),
                      Divider(
                        height: 1 * s,
                        thickness: 1 * s,
                        color: Colors.black.withValues(alpha: 0.1),
                      ),
                    ],
                  ),
                ),
              ),
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(
                    hPad * s,
                    16 * s,
                    hPad * s,
                    16 * s,
                  ),
                  children: [
                    _AspectBubble(
                      text:
                          'Я подготовил варианты действий по этой новости. Начнём с влияния на ваши поставки из Китая?',
                      showBankLink: true,
                      senderLabel: l10n.appName,
                      bankLinkLabel: l10n.showBankMaterial,
                      onBankLinkTap: () => openBankMaterialScreen(
                        context,
                        data: BankMaterialData(backLabel: l10n.backEvent),
                      ),
                    ),
                    SizedBox(height: 12 * s),
                    const _UserBubble(text: 'Какие контракты под риском?'),
                    SizedBox(height: 12 * s),
                    _AspectBubble(
                      text:
                          'В первую очередь — контракты с поставкой критичных компонентов в ближайшие 60 дней. Риск выше по договорам без альтернативного поставщика и запаса по срокам.\n\nМогу сравнить три сценария: ждать разъяснений, искать замену или пересогласовать сроки поставки.',
                      senderLabel: l10n.appName,
                    ),
                  ],
                ),
              ),
              Material(
                color: AppColors.surface,
                child: Padding(
                  padding: EdgeInsets.fromLTRB(
                    hPad * s,
                    8 * s,
                    hPad * s,
                    12 * s + bottomInset,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: [
                            if (_savedPlan == null)
                              _QuickChip(
                                label: l10n.showThreeScenarios,
                                onTap: _openScenarios,
                              )
                            else
                              _QuickChip(
                                label: l10n.actionPlan,
                                filled: true,
                                onTap: _openSavedPlan,
                              ),
                          ],
                        ),
                      ),
                      SizedBox(height: 10 * s),
                      Container(
                        height: 50 * s,
                        decoration: BoxDecoration(
                          color: Colors.transparent,
                          borderRadius: BorderRadius.circular(10 * s),
                          border: Border.all(
                            color: AppColors.border,
                            width: 1,
                          ),
                        ),
                        padding: EdgeInsets.only(left: 16 * s, right: 10 * s),
                        child: Row(
                          children: [
                            Expanded(
                              child: TextField(
                                textCapitalization:
                                    TextCapitalization.sentences,
                                style: AppTypography.regular(
                                  15.9 * s,
                                  color: AppColors.textPrimary,
                                ),
                                cursorColor: AppColors.brandRed,
                                decoration: InputDecoration(
                                  isDense: true,
                                  border: InputBorder.none,
                                  filled: false,
                                  hintText: l10n.askAboutEvent,
                                  hintStyle: AppTypography.regular(
                                    15.9 * s,
                                    color: AppColors.textMuted,
                                  ),
                                  contentPadding: EdgeInsets.zero,
                                ),
                              ),
                            ),
                            GestureDetector(
                              onTap: () {},
                              behavior: HitTestBehavior.opaque,
                              child: SvgPicture.asset(
                                'assets/images/icon_send.svg',
                                width: 30 * s,
                                height: 30 * s,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
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

class _AspectBubble extends StatelessWidget {
  const _AspectBubble({
    required this.text,
    this.showBankLink = false,
    this.onBankLinkTap,
    this.senderLabel = 'Аспект',
    this.bankLinkLabel = 'Показать материал банка',
  });

  final String text;
  final bool showBankLink;
  final VoidCallback? onBankLinkTap;
  final String senderLabel;
  final String bankLinkLabel;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.only(left: 10 * s),
          child: Text(
            senderLabel,
            style: AppTypography.medium(13 * s, color: AppColors.textMuted),
          ),
        ),
        SizedBox(height: 10 * s),
        Align(
          alignment: Alignment.centerLeft,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: 280 * s),
            child: Container(
              padding: EdgeInsets.all(16 * s),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(16 * s),
                border: Border.all(
                  color: Colors.black.withValues(alpha: 0.11),
                  width: 0.5,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.15),
                    offset: Offset(-1 * s, 0),
                    blurRadius: 5.8 * s,
                    spreadRadius: 0,
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    text,
                    style: AppTypography.regular(
                      13 * s,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  if (showBankLink) ...[
                    SizedBox(height: 14 * s),
                    GestureDetector(
                      onTap: onBankLinkTap,
                      behavior: HitTestBehavior.opaque,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Text(
                            bankLinkLabel,
                            style: AppTypography.bold(
                              13 * s,
                              color: AppColors.brandRed,
                            ),
                          ),
                          SizedBox(width: 4 * s),
                          Icon(
                            Icons.arrow_forward,
                            size: 14 * s,
                            color: AppColors.brandRed,
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _UserBubble extends StatelessWidget {
  const _UserBubble({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: BoxConstraints(maxWidth: 248 * s),
        padding: EdgeInsets.all(16 * s),
        decoration: BoxDecoration(
          color: AppColors.brandRed,
          borderRadius: BorderRadius.circular(16 * s),
        ),
        child: Text(
          text,
          style: AppTypography.regular(13 * s, color: AppColors.surface),
        ),
      ),
    );
  }
}

class _QuickChip extends StatelessWidget {
  const _QuickChip({
    required this.label,
    required this.onTap,
    this.filled = false,
  });

  final String label;
  final VoidCallback onTap;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 30 * s,
        padding: EdgeInsets.symmetric(horizontal: 10 * s),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: filled ? AppColors.brandRed : Colors.transparent,
          borderRadius: BorderRadius.circular(16 * s),
          border: filled
              ? null
              : Border.all(color: AppColors.textMuted, width: 1),
        ),
        child: Text(
          label,
          style: AppTypography.regular(
            13 * s,
            color: filled ? AppColors.surface : AppColors.textPrimary,
          ),
        ),
      ),
    );
  }
}
