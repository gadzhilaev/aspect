import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../api/api_exception.dart';
import '../../api/auth_api.dart';
import '../../l10n/app_localizations.dart';
import '../../navigation/app_page_route.dart';
import '../../theme/app_colors.dart';
import '../../theme/app_typography.dart';
import '../../theme/design_scale.dart';
import '../../widgets/auth_widgets.dart';

Future<bool> openChangePasswordScreen(BuildContext context) async {
  final result = await Navigator.of(context).push<bool>(
    AppPageRoute(
      builder: (_) => const ChangePasswordScreen(),
    ),
  );
  return result == true;
}

class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _currentController = TextEditingController();
  final _newController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _currentController.dispose();
    _newController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  bool get _canSubmit {
    return !_submitting &&
        _currentController.text.isNotEmpty &&
        _newController.text.length >= 8 &&
        _newController.text == _confirmController.text;
  }

  Future<void> _submit() async {
    setState(() {
      _error = null;
      _submitting = true;
    });
    try {
      await AuthApi.instance.changePassword(
        currentPassword: _currentController.text,
        newPassword: _newController.text,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _submitting = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _submitting = false;
      });
    }
  }

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
                    onTap: () => Navigator.of(context).maybePop(false),
                    behavior: HitTestBehavior.opaque,
                    child: Text(
                      l10n.backMyData,
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
                    Text(
                      l10n.passwordSection,
                      style: AppTypography.bold(
                        24.83 * s,
                        color: AppColors.textInput,
                      ),
                    ),
                    SizedBox(height: 4 * s),
                    Text(
                      l10n.changePassword,
                      style: AppTypography.bold(
                        24.83 * s,
                        color: AppColors.brandRed,
                      ),
                    ),
                    SizedBox(height: 24 * s),
                    AuthTextField(
                      label: l10n.currentPassword,
                      hint: l10n.currentPasswordHint,
                      controller: _currentController,
                      obscureText: true,
                      onChanged: (_) => setState(() {}),
                    ),
                    SizedBox(height: 14 * s),
                    AuthTextField(
                      label: l10n.newPassword,
                      hint: l10n.newPasswordMinHint,
                      controller: _newController,
                      obscureText: true,
                      onChanged: (_) => setState(() {}),
                    ),
                    SizedBox(height: 14 * s),
                    AuthTextField(
                      label: l10n.confirmPassword,
                      hint: l10n.confirmNewPasswordHint,
                      controller: _confirmController,
                      obscureText: true,
                      onChanged: (_) => setState(() {}),
                    ),
                    if (_error != null) ...[
                      SizedBox(height: 12 * s),
                      Text(
                        _error!,
                        style: AppTypography.regular(
                          13 * s,
                          color: AppColors.brandRed,
                        ),
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
                child: AuthPrimaryButton(
                  label: l10n.savePassword,
                  onPressed: _canSubmit ? _submit : null,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
