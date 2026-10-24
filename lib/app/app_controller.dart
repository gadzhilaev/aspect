import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/session_store.dart';
import '../theme/app_colors.dart';

/// Глобальные язык и тема. Перестраивает приложение через [ListenableBuilder].
class AppController extends ChangeNotifier {
  AppController._();
  static final AppController instance = AppController._();

  Locale _locale = const Locale('ru');
  ThemeMode _themeMode = ThemeMode.system;
  bool _ready = false;

  Locale get locale => _locale;
  ThemeMode get themeMode => _themeMode;
  bool get ready => _ready;

  bool get isDark {
    if (_themeMode == ThemeMode.dark) return true;
    if (_themeMode == ThemeMode.light) return false;
    return WidgetsBinding.instance.platformDispatcher.platformBrightness ==
        Brightness.dark;
  }

  Future<void> load() async {
    final settings = await SessionStore.loadSettings();
    _locale = Locale(settings.language == 'en' ? 'en' : 'ru');
    _themeMode = switch (settings.themeMode) {
      'dark' => ThemeMode.dark,
      'light' => ThemeMode.light,
      _ => ThemeMode.system,
    };
    _applyBrightness();
    _ready = true;
    notifyListeners();
  }

  Future<void> setLanguage(String code) async {
    final next = code == 'en' ? 'en' : 'ru';
    if (_locale.languageCode == next) return;
    _locale = Locale(next);
    notifyListeners();
    final settings = await SessionStore.loadSettings();
    await SessionStore.saveSettings(settings.copyWith(language: next));
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    if (_themeMode == mode) return;
    _themeMode = mode;
    _applyBrightness();
    notifyListeners();
    final settings = await SessionStore.loadSettings();
    final raw = switch (mode) {
      ThemeMode.dark => 'dark',
      ThemeMode.system => 'system',
      ThemeMode.light => 'light',
    };
    await SessionStore.saveSettings(settings.copyWith(themeMode: raw));
  }

  void syncPlatformBrightness() {
    if (_themeMode != ThemeMode.system) return;
    _applyBrightness();
    notifyListeners();
  }

  void _applyBrightness() {
    final brightness = isDark ? Brightness.dark : Brightness.light;
    AppColors.applyBrightness(brightness);
    SystemChrome.setSystemUIOverlayStyle(AppColors.systemOverlay);
  }
}
