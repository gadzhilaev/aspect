import 'dart:io';

/// Base URL Kontur API для симулятора / локальной разработки.
abstract final class ApiConfig {
  /// Переопределение: `--dart-define=API_BASE=http://192.168.x.x:8003`
  static const _define = String.fromEnvironment('API_BASE');

  static String get baseUrl {
    if (_define.isNotEmpty) return _define.replaceAll(RegExp(r'/$'), '');
    if (Platform.isAndroid) {
      // Android emulator → host machine.
      return 'http://10.0.2.2:8003';
    }
    // iOS Simulator / desktop.
    return 'http://127.0.0.1:8003';
  }

  static String get apiV1 => '$baseUrl/api/v1';
}
