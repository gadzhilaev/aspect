import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../models/onboarding_data.dart';
import '../../navigation/app_page_route.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/auth_widgets.dart';
import '../code_confirm_screen.dart';

enum ProfileEditField { fullName, email, role }

Future<String?> openProfileFieldEdit(
  BuildContext context, {
  required ProfileEditField field,
  required String initialValue,
  required String currentEmail,
  List<String> roleOptions = const [],
}) {
  return Navigator.of(context).push<String>(
    AppPageRoute(
      builder: (_) => ProfileFieldEditScreen(
        field: field,
        initialValue: initialValue,
        currentEmail: currentEmail,
        roleOptions: roleOptions,
      ),
    ),
  );
}

class ProfileFieldEditScreen extends StatefulWidget {
  const ProfileFieldEditScreen({
    super.key,
    required this.field,
    required this.initialValue,
    required this.currentEmail,
    this.roleOptions = const [],
  });

  final ProfileEditField field;
  final String initialValue;
  final String currentEmail;
  final List<String> roleOptions;

  @override
  State<ProfileFieldEditScreen> createState() => _ProfileFieldEditScreenState();
}

class _ProfileFieldEditScreenState extends State<ProfileFieldEditScreen> {
  late final TextEditingController _controller;
  late String _role;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialValue);
    _role = widget.initialValue;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  String get _title => switch (widget.field) {
        ProfileEditField.fullName => 'ФИО',
        ProfileEditField.email => 'Рабочая почта',
        ProfileEditField.role => 'Должность',
      };

  String get _accent => switch (widget.field) {
        ProfileEditField.fullName => 'Изменение имени',
        ProfileEditField.email => 'Изменение почты',
        ProfileEditField.role => 'Изменение должности',
      };

  String get _buttonLabel => switch (widget.field) {
        ProfileEditField.email => 'Продолжить',
        ProfileEditField.fullName || ProfileEditField.role => 'Подтвердить',
      };

  Future<bool> _verifyCode({
    required String email,
    required String hint,
  }) async {
    final ok = await Navigator.of(context).push<bool>(
      AppPageRoute(
        builder: (_) => CodeConfirmScreen(
          data: OnboardingData(email: email),
          verifyOnly: true,
          verifyHint: hint,
        ),
      ),
    );
    return ok == true;
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final next = widget.field == ProfileEditField.role
        ? _role.trim()
        : _controller.text.trim();
    if (next.isEmpty) return;
    if (next == widget.initialValue.trim()) {
      Navigator.of(context).pop();
      return;
    }

    setState(() => _submitting = true);

    if (widget.field == ProfileEditField.email) {
      final oldEmail = widget.currentEmail.trim();
      if (oldEmail.isNotEmpty) {
        final oldOk = await _verifyCode(
          email: oldEmail,
          hint: 'Код отправлен на текущую почту',
        );
        if (!mounted) return;
        if (!oldOk) {
          setState(() => _submitting = false);
          return;
        }
      }
      final newOk = await _verifyCode(
        email: next,
        hint: 'Код отправлен на новую почту',
      );
      if (!mounted) return;
      if (!newOk) {
        setState(() => _submitting = false);
        return;
      }
      Navigator.of(context).pop(next);
      return;
    }

    final email = widget.currentEmail.trim();
    if (email.isNotEmpty) {
      final ok = await _verifyCode(
        email: email,
        hint: 'Код отправлен на вашу почту',
      );
      if (!mounted) return;
      if (!ok) {
        setState(() => _submitting = false);
        return;
      }
    }
    if (!mounted) return;
    Navigator.of(context).pop(next);
  }

  @override
  Widget build(BuildContext context) {
    final s = context.scale;
    final hPad = AppColors.screenPadding * s;
    final bottom = MediaQuery.paddingOf(context).bottom;

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
              Padding(
                padding: EdgeInsets.fromLTRB(hPad, 8 * s, hPad, 8 * s),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: GestureDetector(
                    onTap: () => Navigator.of(context).maybePop(),
                    behavior: HitTestBehavior.opaque,
                    child: Text(
                      '‹ Назад',
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
                      _title,
                      style: AppTypography.medium(
                        24.83 * s,
                        color: AppColors.textInput,
                      ),
                    ),
                    SizedBox(height: 4 * s),
                    Text(
                      _accent,
                      style: AppTypography.medium(
                        24.83 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                    SizedBox(height: 28 * s),
                    if (widget.field == ProfileEditField.role)
                      AuthDropdown(
                        label: 'Должность',
                        value: widget.roleOptions.contains(_role) ? _role : '',
                        items: widget.roleOptions,
                        onChanged: (value) => setState(() => _role = value),
                      )
                    else
                      AuthTextField(
                        label: _title,
                        controller: _controller,
                        hint: widget.field == ProfileEditField.email
                            ? 'name@company.com'
                            : 'Фамилия Имя Отчество',
                        keyboardType: widget.field == ProfileEditField.email
                            ? TextInputType.emailAddress
                            : TextInputType.text,
                        textCapitalization: widget.field == ProfileEditField.email
                            ? TextCapitalization.none
                            : TextCapitalization.words,
                        textInputAction: TextInputAction.done,
                        autofocus: true,
                        onSubmitted: (_) => _submit(),
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
                child: AuthPrimaryButton(
                  label: _buttonLabel,
                  onPressed: _submitting ? null : _submit,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
