/// Base URL API Аспекта — публичный стенд или override.
abstract final class ApiConfig {
  /// Локально: `--dart-define=API_BASE=http://127.0.0.1:8020`
  static const _define = String.fromEnvironment('API_BASE');

  /// Публичный HTTPS API (тот же origin, что и сайт).
  static const String competitionApiBase = 'https://alfa-aspect.ru';

  /// Локальный порт стенда (см. docs/MOBILE_STAND_CONNECTION.md).
  static const int standPort = 8020;

  static String get baseUrl {
    if (_define.isNotEmpty) return _define.replaceAll(RegExp(r'/$'), '');
    return competitionApiBase;
  }

  static String get apiV1 => '$baseUrl/api/v1';
}
