import 'package:shared_preferences/shared_preferences.dart';

/// JWT и идентификаторы сессии на устройстве.
abstract final class AuthStore {
  static const _accessKey = 'auth_access_token';
  static const _refreshKey = 'auth_refresh_token';
  static const _userIdKey = 'auth_user_id';
  static const _emailKey = 'auth_email';
  static const _displayNameKey = 'auth_display_name';
  static const _companyIdKey = 'auth_company_id';
  static const _companyNameKey = 'auth_company_name';

  static Future<SharedPreferences> _prefs() async {
    return SharedPreferences.getInstance();
  }

  static Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    final p = await _prefs();
    await p.setString(_accessKey, accessToken);
    await p.setString(_refreshKey, refreshToken);
  }

  static Future<String?> accessToken() async =>
      (await _prefs()).getString(_accessKey);

  static Future<String?> refreshToken() async =>
      (await _prefs()).getString(_refreshKey);

  static Future<bool> hasSession() async {
    final t = await accessToken();
    return t != null && t.isNotEmpty;
  }

  /// Email / user id from a past API login (may remain after [clearTokens]).
  static Future<bool> hasStoredApiIdentity() async {
    final p = await _prefs();
    final email = p.getString(_emailKey)?.trim() ?? '';
    if (email.isNotEmpty) return true;
    final userId = p.getString(_userIdKey)?.trim() ?? '';
    return userId.isNotEmpty;
  }

  static Future<void> saveProfile({
    required String userId,
    required String email,
    required String displayName,
    String? companyId,
    String? companyName,
  }) async {
    final p = await _prefs();
    await p.setString(_userIdKey, userId);
    await p.setString(_emailKey, email);
    await p.setString(_displayNameKey, displayName);
    if (companyId != null) {
      if (companyId.isEmpty) {
        await p.remove(_companyIdKey);
      } else {
        await p.setString(_companyIdKey, companyId);
      }
    }
    if (companyName != null) {
      if (companyName.isEmpty) {
        await p.remove(_companyNameKey);
      } else {
        await p.setString(_companyNameKey, companyName);
      }
    }
  }

  static Future<String?> displayName() async =>
      (await _prefs()).getString(_displayNameKey);

  static Future<String?> email() async =>
      (await _prefs()).getString(_emailKey);

  static Future<String?> companyId() async =>
      (await _prefs()).getString(_companyIdKey);

  static Future<String?> companyName() async =>
      (await _prefs()).getString(_companyNameKey);

  static Future<void> setCompany({
    required String companyId,
    required String companyName,
  }) async {
    final p = await _prefs();
    await p.setString(_companyIdKey, companyId);
    await p.setString(_companyNameKey, companyName);
  }

  static Future<void> clearTokens() async {
    final p = await _prefs();
    await p.remove(_accessKey);
    await p.remove(_refreshKey);
  }

  static Future<void> clearAll() async {
    final p = await _prefs();
    for (final k in [
      _accessKey,
      _refreshKey,
      _userIdKey,
      _emailKey,
      _displayNameKey,
      _companyIdKey,
      _companyNameKey,
    ]) {
      await p.remove(k);
    }
  }
}
