import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../widgets/main_widgets.dart';

class ChatScreenData {
  const ChatScreenData({
    required this.title,
    required this.meta,
    required this.level,
    this.backLabel = 'Сценарии',
  });

  final String title;
  final String meta;
  final ImpactLevel level;
  final String backLabel;
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

class ChatScreen extends StatelessWidget {
  const ChatScreen({super.key, required this.data});

  final ChatScreenData data;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final accent = ImpactColors.accent(data.level);
    const hPad = AppColors.screenPadding; // 16
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
      ),
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
                          '‹ ${data.backLabel}',
                          style: AppTypography.regular(
                            15 * s,
                            color: AppColors.brandRed,
                          ),
                        ),
                      ),
                      SizedBox(height: 14 * s),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            width: 3.8 * s,
                            height: 46 * s,
                            decoration: BoxDecoration(
                              color: accent,
                              borderRadius: BorderRadius.circular(2 * s),
                            ),
                          ),
                          SizedBox(width: 12 * s),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  data.title,
                                  style: AppTypography.bold(
                                    18.88 * s,
                                    color: AppColors.textInput,
                                  ),
                                ),
                                SizedBox(height: 5 * s),
                                Text(
                                  data.meta,
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
                    const _AspectBubble(
                      text:
                          'Я подготовил варианты действий по этой новости. Начнём с влияния на ваши поставки из Китая?',
                    ),
                    SizedBox(height: 12 * s),
                    const _UserBubble(text: 'Какие контракты под риском?'),
                    SizedBox(height: 12 * s),
                    const _AspectBubble(
                      text:
                          'В первую очередь — контракты с поставкой критичных компонентов в ближайшие 60 дней. Риск выше по договорам без альтернативного поставщика и запаса по срокам.\n\nМогу сравнить три сценария: ждать разъяснений, искать замену или пересогласовать сроки поставки.',
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
                            _QuickChip(
                              label: 'Покажи 3 сценария',
                              onTap: () {},
                            ),
                            SizedBox(width: 10 * s),
                            _QuickChip(
                              label: 'Сравнить сценарии',
                              onTap: () {},
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
                                  hintText: 'Спросите об этом событии',
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
  const _AspectBubble({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    // Screen pad 16 → label at 26 ⇒ extra 10 inside the list.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.only(left: 10 * s),
          child: Text(
            'Аспект',
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
              child: Text(
                text,
                style: AppTypography.regular(
                  13 * s,
                  color: AppColors.textPrimary,
                ),
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
  const _QuickChip({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

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
          borderRadius: BorderRadius.circular(16 * s),
          border: Border.all(color: AppColors.textMuted, width: 1),
        ),
        child: Text(
          label,
          style: AppTypography.regular(13 * s, color: AppColors.textPrimary),
        ),
      ),
    );
  }
}
