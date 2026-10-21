import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/onboarding_data.dart';

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
  static const _onboardingDoneKey = 'onboarding_done';
  static const _userNameKey = 'user_name';
  static const _profileKey = 'user_profile';
  static const _viewedEventsKey = 'viewed_event_ids';

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

  static bool _profileLooksComplete(OnboardingData data) {
    return data.companyName.trim().isNotEmpty ||
        data.businessType.trim().isNotEmpty;
  }

  /// True only after registration / onboarding is fully finished (or login).
  static Future<bool> isLoggedIn() async {
    final prefs = await _prefs();
    if (prefs == null) return false;
    if (prefs.getBool(_loggedInKey) != true) return false;

    if (prefs.getBool(_onboardingDoneKey) == true) return true;

    // Legacy: marked logged-in before onboarding finished.
    final profile = await loadProfile();
    if (profile != null && _profileLooksComplete(profile)) {
      await prefs.setBool(_onboardingDoneKey, true);
      return true;
    }

    await prefs.setBool(_loggedInKey, false);
    return false;
  }

  /// Full FIO as stored at login / onboarding.
  static Future<String> fullName() async {
    final prefs = await _prefs();
    final fromKey = prefs?.getString(_userNameKey)?.trim() ?? '';
    if (fromKey.isNotEmpty) return fromKey;
    final profile = await loadProfile();
    return profile?.fullName.trim() ?? '';
  }

  /// Given name for greetings (second FIO token).
  static Future<String> userName() async {
    final stored = await fullName();
    return firstNameFromFullName(stored);
  }

  /// Draft profile (email / FIO / password / partial onboarding) — does NOT log in.
  static Future<void> saveProfile(OnboardingData data) async {
    final prefs = await _prefs();
    if (prefs == null) return;
    final trimmedName = data.fullName.trim();
    if (trimmedName.isNotEmpty) {
      await prefs.setString(_userNameKey, trimmedName);
    }
    await prefs.setString(_profileKey, jsonEncode(data.toJson()));
  }

  /// Finished registration or successful login — opens the main app on next launch.
  static Future<void> finishRegistration(OnboardingData data) async {
    final prefs = await _prefs();
    if (prefs == null) return;
    await saveProfile(data);
    await prefs.setBool(_loggedInKey, true);
    await prefs.setBool(_onboardingDoneKey, true);
  }

  static Future<void> saveLogin({required String userName}) async {
    final prefs = await _prefs();
    if (prefs == null) return;
    final trimmed = userName.trim();
    if (trimmed.isEmpty) return;
    final existing = await loadProfile() ?? OnboardingData();
    existing.fullName = trimmed;
    await finishRegistration(existing);
  }

  static Future<OnboardingData?> loadProfile() async {
    final prefs = await _prefs();
    final raw = prefs?.getString(_profileKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) {
        if (decoded is Map) {
          return OnboardingData.fromJson(Map<String, dynamic>.from(decoded));
        }
        return null;
      }
      return OnboardingData.fromJson(decoded);
    } catch (_) {
      return null;
    }
  }

  static Future<Set<String>> viewedEventIds() async {
    final prefs = await _prefs();
    final list = prefs?.getStringList(_viewedEventsKey) ?? const <String>[];
    return list.toSet();
  }

  static Future<void> markEventViewed(String id) async {
    final prefs = await _prefs();
    if (prefs == null) return;
    final next = (prefs.getStringList(_viewedEventsKey) ?? <String>[])
      ..remove(id)
      ..add(id);
    await prefs.setStringList(_viewedEventsKey, next);
  }

  static Future<void> clear() async {
    final prefs = await _prefs();
    if (prefs == null) return;
    await prefs.remove(_loggedInKey);
    await prefs.remove(_onboardingDoneKey);
    await prefs.remove(_userNameKey);
    await prefs.remove(_profileKey);
    await prefs.remove(_viewedEventsKey);
  }
}
