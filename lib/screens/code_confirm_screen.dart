import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/onboarding_data.dart';
import '../navigation/app_page_route.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../widgets/auth_widgets.dart';
import 'onboarding/onboarding_flow.dart';

class CodeConfirmScreen extends StatefulWidget {
  const CodeConfirmScreen({super.key, required this.data});

  final OnboardingData data;

  @override
  State<CodeConfirmScreen> createState() => _CodeConfirmScreenState();
}

class _CodeConfirmScreenState extends State<CodeConfirmScreen> {
  /// Keeps each cell "non-empty" so iOS soft-keyboard backspace fires onChanged.
  static const _mark = '\u200B';
  static const _resendCooldown = 60;

  final List<TextEditingController> _digits =
      List.generate(6, (_) => TextEditingController(text: _mark));
  final List<FocusNode> _nodes = List.generate(6, (_) => FocusNode());
  final List<String> _values = List.filled(6, '');
  int _secondsLeft = _resendCooldown;
  Timer? _timer;
  bool _keepKeyboard = true;
  bool _navigating = false;
  bool _syncing = false;

  String _digitOf(int index) => _values[index];

  void _writeController(int index, String digit) {
    final text = '$_mark$digit';
    _syncing = true;
    _digits[index].value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
    _syncing = false;
  }

  @override
  void initState() {
    super.initState();
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: AppColors.surface,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
    for (final node in _nodes) {
      node.addListener(_onFocusChanged);
    }
    _startTimer();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _nodes.first.requestFocus();
    });
  }

  void _startTimer() {
    _timer?.cancel();
    setState(() => _secondsLeft = _resendCooldown);
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      if (_secondsLeft <= 0) {
        _timer?.cancel();
        return;
      }
      setState(() => _secondsLeft -= 1);
    });
  }

  void _onFocusChanged() {
    if (!mounted) return;
    setState(() {});
    if (!_keepKeyboard) return;
    if (_nodes.any((n) => n.hasFocus)) return;
    final route = ModalRoute.of(context);
    if (route != null && !route.isCurrent) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_keepKeyboard || !mounted) return;
      if (_nodes.any((n) => n.hasFocus)) return;
      final empty = _values.indexWhere((d) => d.isEmpty);
      _nodes[empty < 0 ? 5 : empty].requestFocus();
    });
  }

  @override
  void dispose() {
    _keepKeyboard = false;
    _timer?.cancel();
    for (final c in _digits) {
      c.dispose();
    }
    for (final n in _nodes) {
      n.removeListener(_onFocusChanged);
      n.dispose();
    }
    super.dispose();
  }

  String get _maskedEmail {
    final email = widget.data.email;
    if (email.isEmpty || !email.contains('@')) {
      return 'a••••@••••••.ru';
    }
    final parts = email.split('@');
    final local = parts.first;
    final domain = parts.sublist(1).join('@');

    final localVisible = local.isNotEmpty ? local[0] : 'a';
    final localMasked = '$localVisible${'•' * math.max(local.length - 1, 4)}';

    final half = (domain.length / 2).ceil().clamp(1, domain.length);
    final domainMasked =
        '${'•' * half}${domain.substring(half.clamp(0, domain.length))}';

    return '$localMasked@$domainMasked';
  }

  String get _timerLabel {
    final m = (_secondsLeft ~/ 60).toString().padLeft(2, '0');
    final s = (_secondsLeft % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  void _onDigitChanged(int index, String value) {
    if (_syncing) return;

    final digitsOnly =
        value.replaceAll(_mark, '').replaceAll(RegExp(r'\D'), '');

    if (digitsOnly.isEmpty) {
      final wasEmpty = _values[index].isEmpty;
      final markerDeleted = !value.contains(_mark);
      _values[index] = '';
      _writeController(index, '');
      // Empty cell + backspace removed the marker → clear previous
      if (wasEmpty && markerDeleted && index > 0) {
        _values[index - 1] = '';
        _writeController(index - 1, '');
        _nodes[index - 1].requestFocus();
      }
      setState(() {});
      return;
    }

    if (digitsOnly.length >= 6) {
      for (var i = 0; i < 6; i++) {
        _values[i] = digitsOnly[i];
        _writeController(i, digitsOnly[i]);
      }
      _nodes[5].requestFocus();
      setState(() {});
      _maybeAutoConfirm();
      return;
    }

    _values[index] = digitsOnly[digitsOnly.length - 1];
    _writeController(index, _values[index]);
    if (index < 5) {
      _nodes[index + 1].requestFocus();
    }
    setState(() {});
    _maybeAutoConfirm();
  }

  bool get _isComplete => _values.every((d) => d.isNotEmpty);

  void _maybeAutoConfirm() {
    if (!_isComplete || _navigating) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_isComplete || _navigating) return;
      _confirm();
    });
  }

  void _confirm() {
    if (_navigating) return;
    _navigating = true;
    _keepKeyboard = false;
    FocusManager.instance.primaryFocus?.unfocus();
    Navigator.of(context)
        .push(
      AppPageRoute<void>(
        builder: (_) => OnboardingFlow(data: widget.data),
      ),
    )
        .then((_) {
      if (!mounted) return;
      _navigating = false;
      _keepKeyboard = true;
    });
  }

  void _resend() {
    if (_secondsLeft > 0) return;
    _startTimer();
    for (var i = 0; i < 6; i++) {
      _values[i] = '';
      _writeController(i, '');
    }
    _nodes.first.requestFocus();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final canResend = _secondsLeft <= 0;

    return Scaffold(
      backgroundColor: AppColors.surface,
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(30, 20, 30, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Align(
                        alignment: Alignment.centerLeft,
                        child: AuthBackButton(),
                      ),
                      const SizedBox(height: 20),
                      const Center(child: AuthLogo()),
                      const SizedBox(height: 16),
                      Text(
                        'Подтверждение',
                        style: AppTypography.medium(
                          28,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Мы отправили код на почту\n$_maskedEmail',
                        style: AppTypography.regular(
                          14,
                          color: const Color(0xFF65717A),
                        ),
                      ),
                      const SizedBox(height: 32),
                      Text(
                        'КОД ИЗ ПИСЬМА',
                        style: AppTypography.bold(
                          11,
                          color: AppColors.brandRed,
                        ),
                      ),
                      const SizedBox(height: 8),
                      LayoutBuilder(
                        builder: (context, constraints) {
                          const gap = 8.0;
                          final box = math.min(
                            56.0,
                            (constraints.maxWidth - gap * 5) / 6,
                          );
                          return Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: List.generate(6, (index) {
                              return _CodeDigitBox(
                                size: box,
                                controller: _digits[index],
                                focusNode: _nodes[index],
                                digit: _digitOf(index),
                                onChanged: (value) =>
                                    _onDigitChanged(index, value),
                              );
                            }),
                          );
                        },
                      ),
                    ],
                  ),
                ),
              ),
              AuthPrimaryButton(
                label: 'Подтвердить',
                onPressed: _isComplete ? _confirm : null,
              ),
              const SizedBox(height: 16),
              GestureDetector(
                onTap: canResend ? _resend : null,
                behavior: HitTestBehavior.opaque,
                child: Text(
                  canResend
                      ? 'Отправить код повторно'
                      : 'Отправить код повторно через $_timerLabel',
                  textAlign: TextAlign.center,
                  style: AppTypography.regular(
                    13,
                    color: canResend
                        ? AppColors.brandRed
                        : const Color(0xFF65717A),
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

class _CodeDigitBox extends StatefulWidget {
  const _CodeDigitBox({
    required this.size,
    required this.controller,
    required this.focusNode,
    required this.digit,
    required this.onChanged,
  });

  final double size;
  final TextEditingController controller;
  final FocusNode focusNode;
  final String digit;
  final ValueChanged<String> onChanged;

  @override
  State<_CodeDigitBox> createState() => _CodeDigitBoxState();
}

class _CodeDigitBoxState extends State<_CodeDigitBox> {
  static const _border = Color(0xFF65717A);
  static const _boxHeight = 56.0;
  static const _fontSize = 24.0;

  @override
  void initState() {
    super.initState();
    widget.focusNode.addListener(_onFocus);
  }

  @override
  void didUpdateWidget(covariant _CodeDigitBox oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.focusNode != widget.focusNode) {
      oldWidget.focusNode.removeListener(_onFocus);
      widget.focusNode.addListener(_onFocus);
    }
  }

  @override
  void dispose() {
    widget.focusNode.removeListener(_onFocus);
    super.dispose();
  }

  void _onFocus() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final focused = widget.focusNode.hasFocus;
    final digit = widget.digit;

    return SizedBox(
      width: widget.size,
      height: _boxHeight,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: focused ? AppColors.brandRed : _border,
                  width: 1,
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: TextField(
              controller: widget.controller,
              focusNode: widget.focusNode,
              keyboardType: TextInputType.number,
              // Marker + digit; allow delete of marker for backspace detection
              maxLength: 2,
              showCursor: false,
              enableInteractiveSelection: false,
              style: const TextStyle(
                color: Colors.transparent,
                fontSize: _fontSize,
                height: 1,
              ),
              cursorWidth: 0,
              cursorColor: Colors.transparent,
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[\d\u200B]')),
              ],
              decoration: const InputDecoration(
                counterText: '',
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                filled: false,
                isCollapsed: true,
                contentPadding: EdgeInsets.zero,
              ),
              onChanged: widget.onChanged,
            ),
          ),
          IgnorePointer(
            child: digit.isEmpty
                ? (focused
                    ? Container(
                        width: 2,
                        height: 22,
                        color: AppColors.brandRed,
                      )
                    : const SizedBox.shrink())
                : SizedBox(
                    height: _fontSize,
                    child: Center(
                      child: Text(
                        digit,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontFamily: AppTypography.family,
                          fontWeight: FontWeight.w700,
                          fontSize: _fontSize,
                          height: 1,
                          leadingDistribution: TextLeadingDistribution.even,
                          color: AppColors.textPrimary,
                        ),
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
