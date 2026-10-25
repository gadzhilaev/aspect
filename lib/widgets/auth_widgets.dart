import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../l10n/app_localizations.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';

/// iOS часто не поднимает Shift для words/sentences — капитализируем ввод сами.
class _CapitalizeWordsFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    final text = newValue.text;
    if (text.isEmpty) return newValue;
    final buffer = StringBuffer();
    var capitalizeNext = true;
    for (final unit in text.runes) {
      final ch = String.fromCharCode(unit);
      if (capitalizeNext && _isLowerLetter(ch)) {
        buffer.write(ch.toUpperCase());
        capitalizeNext = false;
      } else {
        buffer.write(ch);
        if (ch == ' ' || ch == '-' || ch == '\n') {
          capitalizeNext = true;
        } else if (ch.trim().isNotEmpty) {
          capitalizeNext = false;
        }
      }
    }
    final next = buffer.toString();
    if (next == text) return newValue;
    return TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(
        offset: newValue.selection.baseOffset.clamp(0, next.length),
      ),
      composing: TextRange.empty,
    );
  }
}

bool _isLowerLetter(String ch) {
  if (ch.length != 1) return false;
  final lower = ch.toLowerCase();
  final upper = ch.toUpperCase();
  return lower != upper && ch == lower;
}

class AuthBackButton extends StatelessWidget {
  const AuthBackButton({super.key, this.onPressed});

  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return GestureDetector(
      onTap: onPressed ?? () => Navigator.of(context).maybePop(),
      behavior: HitTestBehavior.opaque,
      child: Text(
        context.l10n.back,
        style: AppTypography.regular(15 * s, color: AppColors.textSecondary),
      ),
    );
  }
}

class AuthLogo extends StatelessWidget {
  const AuthLogo({super.key, this.height});

  final double? height;

  @override
  Widget build(BuildContext context) {
    return SvgPicture.asset(
      'assets/images/welcome_logo.svg',
      height: height ?? context.ds(32),
      fit: BoxFit.contain,
    );
  }
}

class AuthTextField extends StatefulWidget {
  const AuthTextField({
    super.key,
    required this.label,
    required this.controller,
    this.hint,
    this.obscureText = false,
    this.keyboardType,
    this.textInputAction,
    this.textCapitalization,
    this.autofillHints,
    this.autocorrect,
    this.enableSuggestions,
    this.inputFormatters,
    this.suffix,
    this.onChanged,
    this.onSubmitted,
    this.focusNode,
    this.autofocus = false,
    this.autoScrollOnFocus = true,
    this.hasError = false,
  });

  final String label;
  final TextEditingController controller;
  final String? hint;
  final bool obscureText;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  /// Defaults to sentences (только начало поля). ФИО — words.
  /// Email / password → none.
  final TextCapitalization? textCapitalization;
  final Iterable<String>? autofillHints;
  /// Null → Flutter default (true), except email/password → false.
  final bool? autocorrect;
  final bool? enableSuggestions;
  final List<TextInputFormatter>? inputFormatters;
  final Widget? suffix;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final FocusNode? focusNode;
  final bool autofocus;
  /// When false, parent handles scroll (e.g. login form + button).
  final bool autoScrollOnFocus;
  /// Красная обводка при ошибке валидации / API.
  final bool hasError;

  @override
  State<AuthTextField> createState() => _AuthTextFieldState();
}

class _AuthTextFieldState extends State<AuthTextField> {
  FocusNode? _internalFocusNode;
  bool? _obscured;

  FocusNode get _focusNode {
    if (widget.focusNode != null) return widget.focusNode!;
    _internalFocusNode ??= FocusNode()..addListener(_onFocus);
    return _internalFocusNode!;
  }

  bool get _isObscured => _obscured ?? widget.obscureText;

  bool get _hasVisibilityToggle => widget.obscureText && widget.suffix == null;

  @override
  void initState() {
    super.initState();
    _obscured = widget.obscureText;
    if (widget.focusNode != null) {
      widget.focusNode!.addListener(_onFocus);
    } else {
      _focusNode;
    }
  }

  @override
  void didUpdateWidget(covariant AuthTextField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.obscureText != oldWidget.obscureText && !_hasVisibilityToggle) {
      _obscured = widget.obscureText;
    }
    final oldNode = oldWidget.focusNode ?? _internalFocusNode;
    final newNode = _focusNode;
    if (oldNode != null && oldNode != newNode) {
      oldNode.removeListener(_onFocus);
      newNode.addListener(_onFocus);
    }
  }

  @override
  void dispose() {
    widget.focusNode?.removeListener(_onFocus);
    _internalFocusNode?.removeListener(_onFocus);
    _internalFocusNode?.dispose();
    super.dispose();
  }

  void _onFocus() {
    if (!mounted) return;
    setState(() {});
    if (!_focusNode.hasFocus || !widget.autoScrollOnFocus) return;
    // Scroll only when the field is under / clipped by the keyboard.
    void ensureIfObscured() {
      if (!mounted || !_focusNode.hasFocus) return;
      final box = context.findRenderObject();
      if (box is! RenderBox || !box.hasSize) return;
      final fieldBottom = box.localToGlobal(Offset(0, box.size.height)).dy;
      final media = MediaQuery.of(context);
      final keyboardTop = media.size.height - media.viewInsets.bottom;
      if (fieldBottom <= keyboardTop - 12) return;
      Scrollable.ensureVisible(
        context,
        alignment: 0.2,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      );
    }

    WidgetsBinding.instance.addPostFrameCallback((_) => ensureIfObscured());
    Future<void>.delayed(const Duration(milliseconds: 320), ensureIfObscured);
  }

  bool get _isEmail => widget.keyboardType == TextInputType.emailAddress;

  /// iOS: явный text, иначе sentences/words часто не поднимают Shift.
  TextInputType? get _keyboardType {
    if (widget.keyboardType != null) return widget.keyboardType;
    if (widget.obscureText) return TextInputType.visiblePassword;
    return TextInputType.text;
  }

  TextCapitalization get _capitalization {
    if (widget.textCapitalization != null) return widget.textCapitalization!;
    if (widget.obscureText || _isEmail) return TextCapitalization.none;
    // Только первая буква поля; после пробела — как есть (не как ФИО).
    return TextCapitalization.sentences;
  }

  bool get _autocorrect {
    if (widget.autocorrect != null) return widget.autocorrect!;
    if (widget.obscureText || _isEmail) return false;
    return true;
  }

  bool get _enableSuggestions {
    if (widget.enableSuggestions != null) return widget.enableSuggestions!;
    if (widget.obscureText || _isEmail) return false;
    return true;
  }

  /// Принудительная капитализация слов — только для явного words (ФИО).
  bool get _forceWordCaps =>
      !widget.obscureText &&
      !_isEmail &&
      widget.textCapitalization == TextCapitalization.words;

  List<TextInputFormatter> get _formatters {
    final base = widget.inputFormatters ?? const <TextInputFormatter>[];
    if (!_forceWordCaps) return base;
    return [...base, _CapitalizeWordsFormatter()];
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final focused = _focusNode.hasFocus;
    final showToggle = _hasVisibilityToggle;
    final trailing = widget.suffix ??
        (showToggle
            ? ExcludeFocus(
                child: IconButton(
                  onPressed: () => setState(() => _obscured = !_isObscured),
                  icon: Icon(
                    _isObscured
                        ? Icons.visibility_off_outlined
                        : Icons.visibility_outlined,
                    color: AppColors.textSecondary,
                    size: 22 * s,
                  ),
                  padding: EdgeInsets.zero,
                  constraints: BoxConstraints(
                    minWidth: 40 * s,
                    minHeight: 40 * s,
                  ),
                ),
              )
            : null);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          widget.label,
          style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
        ),
        SizedBox(height: 8 * s),
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => _focusNode.requestFocus(),
          child: Container(
            height: 50 * s,
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(16 * s),
              border: Border.all(
                color: (widget.hasError || focused)
                    ? AppColors.brandRed
                    : AppColors.border,
                width: widget.hasError ? 1.5 : 1,
              ),
            ),
            padding: EdgeInsets.only(
              left: 16 * s,
              right: trailing != null ? 12 * s : 16 * s,
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(
                  child: TextField(
                    // Key: iOS не всегда меняет раскладку при смене keyboardType
                    // без пересоздания TextInputConnection.
                    key: ValueKey<String>(
                      'auth-tf-$_keyboardType-$_capitalization-$showToggle',
                    ),
                    controller: widget.controller,
                    focusNode: _focusNode,
                    autofocus: widget.autofocus,
                    obscureText: showToggle ? _isObscured : widget.obscureText,
                    // Явный text (не name): NamePhonePad на iOS ломает Shift.
                    keyboardType: _keyboardType,
                    textInputAction: widget.textInputAction,
                    textCapitalization: _capitalization,
                    // Autofill name/email часто сбрасывает autocapitalization на iOS.
                    autofillHints: (_isEmail || widget.obscureText)
                        ? widget.autofillHints
                        : null,
                    autocorrect: _autocorrect,
                    enableSuggestions: _enableSuggestions,
                    smartDashesType: SmartDashesType.disabled,
                    smartQuotesType: SmartQuotesType.disabled,
                    keyboardAppearance: Brightness.light,
                    inputFormatters: _formatters,
                    onChanged: widget.onChanged,
                    onSubmitted: widget.onSubmitted,
                    cursorColor: AppColors.brandRed,
                    // Keep modest — large padding forces scroll even when field is visible.
                    scrollPadding: EdgeInsets.fromLTRB(20 * s, 20 * s, 20 * s, 20 * s),
                    textAlignVertical: TextAlignVertical.center,
                    onEditingComplete: widget.onSubmitted != null
                        ? null
                        : () {
                            final action = widget.textInputAction ??
                                TextInputAction.done;
                            if (action == TextInputAction.next) {
                              FocusScope.of(context).nextFocus();
                            } else if (action == TextInputAction.search) {
                              widget.onSubmitted?.call(widget.controller.text);
                            } else {
                              _focusNode.unfocus();
                            }
                          },
                    style: TextStyle(
                      fontFamily: AppTypography.family,
                      fontWeight: FontWeight.w400,
                      fontSize: 15 * s,
                      height: 1,
                      leadingDistribution: TextLeadingDistribution.even,
                      color: AppColors.textPrimary,
                    ),
                    decoration: InputDecoration(
                      isCollapsed: true,
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      hintText: widget.hint,
                      hintStyle: TextStyle(
                        fontFamily: AppTypography.family,
                        fontWeight: FontWeight.w400,
                        fontSize: 15 * s,
                        height: 1,
                        leadingDistribution: TextLeadingDistribution.even,
                        color: AppColors.textHint,
                      ),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                ),
                if (trailing != null) ...[
                  SizedBox(width: 8 * s),
                  ExcludeFocus(child: trailing),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class AuthDropdown extends StatelessWidget {
  const AuthDropdown({
    super.key,
    required this.label,
    required this.value,
    required this.items,
    required this.onChanged,
    this.hint,
  });

  final String label;
  final String value;
  final List<String> items;
  final ValueChanged<String> onChanged;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final hintText = hint ?? context.l10n.selectHint;
    final selected = items.contains(value) ? value : null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: AppTypography.bold(12 * s, color: AppColors.textSecondary),
        ),
        SizedBox(height: 8 * s),
        Container(
          height: 50 * s,
          padding: EdgeInsets.symmetric(horizontal: 16 * s),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16 * s),
            border: Border.all(color: AppColors.border, width: 1),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: selected,
              isExpanded: true,
              hint: Text(
                hintText,
                style: AppTypography.regular(15 * s, color: AppColors.textHint),
              ),
              icon: Icon(
                Icons.keyboard_arrow_down_rounded,
                color: AppColors.textSecondary,
                size: 24 * s,
              ),
              style: AppTypography.regular(15 * s, color: AppColors.textPrimary),
              dropdownColor: AppColors.surface,
              borderRadius: BorderRadius.circular(16 * s),
              items: [
                for (final item in items)
                  DropdownMenuItem<String>(
                    value: item,
                    child: Text(
                      item,
                      overflow: TextOverflow.ellipsis,
                      style: AppTypography.regular(
                        15 * s,
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ),
              ],
              onChanged: (next) {
                if (next != null) onChanged(next);
              },
            ),
          ),
        ),
      ],
    );
  }
}

class AuthPrimaryButton extends StatelessWidget {
  const AuthPrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
  });

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return SizedBox(
      height: 52 * s,
      width: double.infinity,
      child: FilledButton(
        onPressed: onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.brandRed,
          disabledBackgroundColor: AppColors.brandRed.withValues(alpha: 0.4),
          foregroundColor: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16 * s),
          ),
          textStyle: AppTypography.bold(16 * s, color: AppColors.surface),
        ),
        child: Text(label, textAlign: TextAlign.center),
      ),
    );
  }
}

class AuthFooterLink extends StatelessWidget {
  const AuthFooterLink({
    super.key,
    required this.prefix,
    required this.action,
    required this.onTap,
  });

  final String prefix;
  final String action;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    return Center(
      child: Text.rich(
        TextSpan(
          style: AppTypography.regular(13 * s, color: AppColors.textSecondary),
          children: [
            TextSpan(text: prefix),
            WidgetSpan(
              alignment: PlaceholderAlignment.baseline,
              baseline: TextBaseline.alphabetic,
              child: GestureDetector(
                onTap: onTap,
                child: Text(
                  action,
                  style: AppTypography.regular(13 * s, color: AppColors.brandRed),
                ),
              ),
            ),
          ],
        ),
        textAlign: TextAlign.center,
      ),
    );
  }
}
