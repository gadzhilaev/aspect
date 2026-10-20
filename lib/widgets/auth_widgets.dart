import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/design_scale.dart';

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
        '‹ Назад',
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
    this.textCapitalization = TextCapitalization.none,
    this.inputFormatters,
    this.suffix,
    this.onChanged,
    this.onSubmitted,
    this.focusNode,
    this.autofocus = false,
  });

  final String label;
  final TextEditingController controller;
  final String? hint;
  final bool obscureText;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final TextCapitalization textCapitalization;
  final List<TextInputFormatter>? inputFormatters;
  final Widget? suffix;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final FocusNode? focusNode;
  final bool autofocus;

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
    if (mounted) setState(() {});
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
                color: focused ? AppColors.brandRed : AppColors.border,
                width: 1,
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
                    controller: widget.controller,
                    focusNode: _focusNode,
                    autofocus: widget.autofocus,
                    obscureText: showToggle ? _isObscured : widget.obscureText,
                    keyboardType: widget.keyboardType,
                    textInputAction: widget.textInputAction,
                    textCapitalization: widget.textCapitalization,
                    inputFormatters: widget.inputFormatters,
                    onChanged: widget.onChanged,
                    onSubmitted: widget.onSubmitted,
                    cursorColor: AppColors.brandRed,
                    scrollPadding: EdgeInsets.fromLTRB(20 * s, 20 * s, 20 * s, 80 * s),
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
    this.hint = 'Выберите',
  });

  final String label;
  final String value;
  final List<String> items;
  final ValueChanged<String> onChanged;
  final String hint;

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
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
                hint,
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
