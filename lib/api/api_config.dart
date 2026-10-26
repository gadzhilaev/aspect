/// Base URL API Аспекта — публичный стенд или override.
abstract final class ApiConfig {
  /// Локально: `--dart-define=API_BASE=http://127.0.0.1:8020`
  static const _define = String.fromEnvironment('API_BASE');

  /// Публичный HTTPS API (рабочий, пока DNS alfa-aspect.ru пустой).
  static const String competitionApiBase = 'https://gadzhilaev.ru/aspekt-api';

  /// Локальный порт стенда (см. docs/MOBILE_STAND_CONNECTION.md).
  static const int standPort = 8020;

  static String get baseUrl {
    if (_define.isNotEmpty) return _define.replaceAll(RegExp(r'/$'), '');
    return competitionApiBase;
  }

  static String get apiV1 => '$baseUrl/api/v1';

  /// Matches pubspec `version` (build suffix omitted).
  static const String appVersion = '1.0.0';
}
