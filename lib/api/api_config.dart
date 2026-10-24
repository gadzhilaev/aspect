import 'dart:io';

/// Base URL Kontur API для симулятора / локальной разработки.
abstract final class ApiConfig {
  /// Переопределение: `--dart-define=API_BASE=http://192.168.x.x:8020`
  /// Физический телефон: IP машины в LAN, не localhost.
  static const _define = String.fromEnvironment('API_BASE');

  /// Конкурсный очищенный стенд (см. docs/MOBILE_STAND_CONNECTION.md).
  static const int standPort = 8020;

  static String get baseUrl {
    if (_define.isNotEmpty) return _define.replaceAll(RegExp(r'/$'), '');
    if (Platform.isAndroid) {
      // Android emulator → host machine.
      return 'http://10.0.2.2:$standPort';
    }
    // iOS Simulator / desktop.
    return 'http://127.0.0.1:$standPort';
  }

  static String get apiV1 => '$baseUrl/api/v1';
}
