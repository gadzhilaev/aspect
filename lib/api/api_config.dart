/// Base URL API Аспекта — публичный стенд или override.
abstract final class ApiConfig {
  /// Локально: `--dart-define=API_BASE=http://127.0.0.1:8020`
  static const _define = String.fromEnvironment('API_BASE');

  /// Рабочий HTTPS, пока у alfa-aspect.ru нет A-записи в DNS.
  /// После DNS: `--dart-define=API_BASE=https://alfa-aspect.ru` или вернуть default.
  static const String competitionApiBase = 'https://gadzhilaev.ru/aspekt-api';

  /// Целевой прод-домен (когда DNS поднимется).
  static const String primaryDomain = 'https://alfa-aspect.ru';

  /// Локальный порт стенда (см. docs/MOBILE_STAND_CONNECTION.md).
  static const int standPort = 8020;

  static String get baseUrl {
    if (_define.isNotEmpty) return _define.replaceAll(RegExp(r'/$'), '');
    return competitionApiBase;
  }

  static String get apiV1 => '$baseUrl/api/v1';
}
