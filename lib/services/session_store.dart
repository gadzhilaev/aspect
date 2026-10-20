import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
    final name = prefs?.getString(_userNameKey)?.trim() ?? '';
    return name.isEmpty ? 'Пользователь' : name;
  }

  static Future<void> saveLogin({required String userName}) async {
    final prefs = await _prefs();
    if (prefs == null) return;
    final parts = userName.trim().split(RegExp(r'\s+'));
    final short =
        parts.isEmpty || parts.first.isEmpty ? 'Пользователь' : parts.first;
    await prefs.setBool(_loggedInKey, true);
    await prefs.setString(_userNameKey, short);
  }

  static Future<void> clear() async {
    final prefs = await _prefs();
    if (prefs == null) return;
    await prefs.remove(_loggedInKey);
    await prefs.remove(_userNameKey);
  }
}
