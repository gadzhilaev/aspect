import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../l10n/app_localizations.dart';
import '../../navigation/app_page_route.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';

class BankMaterialData {
  const BankMaterialData({
    this.backLabel = 'Событие',
    this.headline =
        'Ключевая ставка ЦБ РФ: ставка без изменения стала жёстче',
    this.meta =
        'Название из перечня материалов кейса. Дата документа подставляется после загрузки.',
    this.fragmentTitle = 'Фрагмент, использованный в разборе',
    this.fragmentBody =
        'Здесь появится точная выдержка из загруженного документа с указанием страницы. До загрузки текст не выдаётся за экспертную позицию банка.',
    this.fragmentLink = 'Ключевая ставка сохранена',
  });

  final String backLabel;
  final String headline;
  final String meta;
  final String fragmentTitle;
  final String fragmentBody;
  final String fragmentLink;
}

Future<void> openBankMaterialScreen(
  BuildContext context, {
  BankMaterialData data = const BankMaterialData(),
}) {
  return Navigator.of(context).push(
    AppPageRoute<void>(
      builder: (_) => BankMaterialScreen(data: data),
    ),
  );
}

class BankMaterialScreen extends StatelessWidget {
  const BankMaterialScreen({super.key, required this.data});

  final BankMaterialData data;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;
    const titleDark = Color.fromRGBO(24, 35, 44, 1);
    const heading = Color.fromRGBO(24, 27, 34, 1);
    final backLabel = data.backLabel == 'Событие'
        ? l10n.backEvent
        : data.backLabel;

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
                child: Row(
                  children: [
                    Expanded(
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: GestureDetector(
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
                      ),
                    ),
                    const _AlfaBankBadge(),
                  ],
                ),
              ),
              Expanded(
                child: ListView(
                  padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 16 * s),
                  children: [
                    Text(
                      l10n.bankMaterialHeading,
                      style: AppTypography.bold(
                        24.83 * s,
                        color: titleDark,
                      ),
                    ),
                    SizedBox(height: 10 * s),
                    Text(
                      data.headline,
                      style: AppTypography.bold(
                        24.83 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                    SizedBox(height: 10 * s),
                    Text(
                      data.meta,
                      style: AppTypography.regular(
                        13 * s,
                        color: AppColors.textMuted,
                      ),
                    ),
                    SizedBox(height: 20 * s),
                    Container(
                      width: double.infinity,
                      padding: EdgeInsets.all(16 * s),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(7 * s),
                        border: Border(
                          left: BorderSide(
                            color: AppColors.brandRed,
                            width: 3 * s,
                          ),
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.17),
                            offset: Offset(-1 * s, -1 * s),
                            blurRadius: 14.2 * s,
                          ),
                        ],
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            data.fragmentTitle,
                            style: AppTypography.bold(
                              15.13 * s,
                              color: heading,
                            ),
                          ),
                          SizedBox(height: 10 * s),
                          Text(
                            data.fragmentBody,
                            style: AppTypography.regular(
                              15.13 * s,
                              color: Colors.black,
                            ),
                          ),
                          SizedBox(height: 14 * s),
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                data.fragmentLink,
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
                        ],
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
                    onPressed: () {},
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.brandRed,
                      foregroundColor: AppColors.surface,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(13 * s),
                      ),
                    ),
                    child: Text(
                      l10n.openOriginalDocument,
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

class _AlfaBankBadge extends StatelessWidget {
  const _AlfaBankBadge();

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Container(
      height: 23 * s,
      padding: EdgeInsets.symmetric(horizontal: 10 * s),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppColors.brandRed,
        borderRadius: BorderRadius.circular(6 * s),
      ),
      child: SvgPicture.asset(
        'assets/images/alfa_bank_logo.svg',
        width: 51 * s,
        height: 10 * s,
        fit: BoxFit.contain,
        colorFilter: ColorFilter.mode(
          AppColors.surface,
          BlendMode.srcIn,
        ),
      ),
    );
  }
}
