import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Extracts given name from Russian FIO: «Фамилия Имя [Отчество]».
String firstNameFromFullName(String fullName) {
  final parts = fullName.trim().split(RegExp(r'\s+'));
  if (parts.isEmpty || parts.first.isEmpty) return 'Пользователь';
  if (parts.length >= 2) return parts[1];
  return parts.first;
}

class SessionStore {
  SessionStore._();

  static const _loggedInKey = 'logged_in';
  static const _userNameKey = 'user_name';

  static Future<SharedPreferences?> _prefs() async {
    try {
      return await SharedPreferences.getInstance();
    } on MissingPluginException {
      // Native plugin not linked yet — needs full app restart after pub add.
      return null;
    } catch (_) {
      return null;
    }
  }

  static Future<bool> isLoggedIn() async {
    final prefs = await _prefs();
    return prefs?.getBool(_loggedInKey) ?? false;
  }

  static Future<String> userName() async {
    final prefs = await _prefs();
    final stored = prefs?.getString(_userNameKey)?.trim() ?? '';
    return firstNameFromFullName(stored);
  }

  static Future<void> saveLogin({required String userName}) async {
    final prefs = await _prefs();
    if (prefs == null) return;
    final trimmed = userName.trim();
    if (trimmed.isEmpty) return;
    await prefs.setBool(_loggedInKey, true);
    await prefs.setString(_userNameKey, trimmed);
  }

  static Future<void> clear() async {
    final prefs = await _prefs();
    if (prefs == null) return;
    await prefs.remove(_loggedInKey);
    await prefs.remove(_userNameKey);
  }
}
