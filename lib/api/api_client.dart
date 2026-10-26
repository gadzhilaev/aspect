import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../services/auth_store.dart';
import '../services/session_store.dart';
import 'api_config.dart';
import 'api_exception.dart';

typedef JsonMap = Map<String, dynamic>;

/// HTTP-клиент с Bearer и авто-refresh при 401.
class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  final http.Client _http = http.Client();
  bool _refreshing = false;

  /// Лог всех HTTP в терминал `flutter run` (только debug).
  static bool logHttp = kDebugMode;

  static const Duration receiveTimeout = Duration(seconds: 20);

  /// Цикл ассистента на стенде до ~90 с — клиент ждёт дольше обычного HTTP.
  static const Duration assistantTimeout = Duration(seconds: 120);

  static const _networkUnavailableMessage =
      'Сервер недоступен. Проверьте, что API запущен, и попробуйте снова.';

  /// Сырой Socket/ClientException → понятный ApiException (без stack в UI).
  static ApiException networkUnavailable([Object? cause]) {
    return ApiException(
      statusCode: 0,
      code: 'NETWORK_UNAVAILABLE',
      message: _networkUnavailableMessage,
      details: cause?.toString(),
      underlyingCause: cause?.toString(),
    );
  }

  /// Fire-and-forget diagnostic report (works without auth).
  Future<void> reportClientError({
    required String source,
    required String screen,
    required String message,
    String? exceptionType,
    String? stack,
    int? httpStatus,
    String? httpCode,
    String? url,
    String? method,
    Map<String, dynamic>? details,
    String? appVersion,
    String? platform,
    String? deviceInfo,
    String? emailAttempted,
  }) async {
    final body = <String, dynamic>{
      'source': source,
      'screen': screen,
      'message': message,
      'exception_type': ?exceptionType,
      'stack': ?stack,
      'http_status': ?httpStatus,
      'http_code': ?httpCode,
      'url': ?url,
      'method': ?method,
      if (details != null && details.isNotEmpty) 'details': details,
      'app_version': ?appVersion,
      'platform': ?platform,
      'device_info': ?deviceInfo,
      if (emailAttempted != null && emailAttempted.isNotEmpty)
        'email_attempted': emailAttempted,
    };
    try {
      await postJson(
        '/diagnostics/client-error',
        auth: false,
        body: body,
        timeout: const Duration(seconds: 8),
      );
    } catch (e) {
      if (logHttp) {
        _logLine('client-error report failed: $e');
      }
    }
  }

  static String clientSource() {
    if (kIsWeb) return 'web';
    if (Platform.isAndroid) return 'android';
    if (Platform.isIOS) return 'ios';
    return 'unknown';
  }

  static String clientPlatformLabel() {
    if (kIsWeb) return 'web';
    return Platform.operatingSystem;
  }

  static String clientDeviceInfo() {
    if (kIsWeb) return 'web';
    return '${Platform.operatingSystem} ${Platform.operatingSystemVersion}';
  }

  static Never _requestTimedOut([Duration? limit]) {
    throw TimeoutException(
      'HTTP request timed out',
      limit ?? receiveTimeout,
    );
  }

  static bool isNetworkFailure(Object error) {
    if (error is SocketException) return true;
    if (error is TimeoutException) return true;
    if (error is http.ClientException) return true;
    if (error is HandshakeException) return true;
    final text = error.toString().toLowerCase();
    return text.contains('socketexception') ||
        text.contains('connection refused') ||
        text.contains('failed host lookup') ||
        text.contains('network is unreachable') ||
        text.contains('timed out');
  }

  Uri _uri(String path, [Map<String, String>? query]) {
    final p = path.startsWith('/') ? path : '/$path';
    return Uri.parse('${ApiConfig.apiV1}$p').replace(queryParameters: query);
  }

  Future<JsonMap?> getJson(
    String path, {
    Map<String, String>? query,
    bool auth = true,
    Duration? timeout,
  }) async {
    final res = await _send(
      'GET',
      _uri(path, query),
      auth: auth,
      timeout: timeout,
    );
    return _decodeMap(res);
  }

  Future<JsonMap?> postJson(
    String path, {
    Object? body,
    bool auth = true,
    Duration? timeout,
  }) async {
    final res = await _send(
      'POST',
      _uri(path),
      auth: auth,
      jsonBody: body,
      timeout: timeout,
    );
    return _decodeMap(res);
  }

  Future<JsonMap?> patchJson(
    String path, {
    Object? body,
    bool auth = true,
    Duration? timeout,
  }) async {
    final res = await _send(
      'PATCH',
      _uri(path),
      auth: auth,
      jsonBody: body,
      timeout: timeout,
    );
    return _decodeMap(res);
  }

  Future<JsonMap?> deleteJson(
    String path, {
    Object? body,
    bool auth = true,
    Duration? timeout,
  }) async {
    final res = await _send(
      'DELETE',
      _uri(path),
      auth: auth,
      jsonBody: body,
      timeout: timeout,
    );
    return _decodeMap(res);
  }

  Future<http.Response> _send(
    String method,
    Uri uri, {
    required bool auth,
    Object? jsonBody,
    Duration? timeout,
  }) async {
    try {
      var res = await _once(
        method,
        uri,
        auth: auth,
        jsonBody: jsonBody,
        timeout: timeout,
      );
      if (auth && res.statusCode == 401) {
        final ok = await _tryRefresh();
        if (ok) {
          res = await _once(
            method,
            uri,
            auth: auth,
            jsonBody: jsonBody,
            timeout: timeout,
          );
        }
      }
      if (res.statusCode >= 400) {
        throw _toException(res);
      }
      return res;
    } on ApiException {
      rethrow;
    } catch (e) {
      if (isNetworkFailure(e)) {
        _logLine('HTTP NET-ERR $method $uri → $e');
        throw networkUnavailable(e);
      }
      rethrow;
    }
  }

  Future<http.Response> _once(
    String method,
    Uri uri, {
    required bool auth,
    Object? jsonBody,
    Duration? timeout,
  }) async {
    final headers = await _headers(auth: auth, json: jsonBody != null);
    final encoded = jsonBody == null ? null : jsonEncode(jsonBody);
    _logRequest(method, uri, headers, encoded);
    final limit = timeout ?? receiveTimeout;

    late http.Response res;
    switch (method) {
      case 'GET':
        res = await _http
            .get(uri, headers: headers)
            .timeout(limit, onTimeout: () => _requestTimedOut(limit));
      case 'POST':
        res = await _http
            .post(uri, headers: headers, body: encoded)
            .timeout(limit, onTimeout: () => _requestTimedOut(limit));
      case 'PATCH':
        res = await _http
            .patch(uri, headers: headers, body: encoded)
            .timeout(limit, onTimeout: () => _requestTimedOut(limit));
      case 'DELETE':
        res = await _http
            .delete(uri, headers: headers, body: encoded)
            .timeout(limit, onTimeout: () => _requestTimedOut(limit));
      default:
        throw StateError('Unsupported HTTP method: $method');
    }
    _logResponse(method, uri, res);
    return res;
  }

  Future<bool> _tryRefresh() async {
    if (_refreshing) return false;
    final refresh = await AuthStore.refreshToken();
    if (refresh == null || refresh.isEmpty) return false;
    _refreshing = true;
    try {
      final res = await _once(
        'POST',
        _uri('/auth/refresh'),
        auth: false,
        jsonBody: {'refresh_token': refresh},
      );
      if (res.statusCode >= 400) {
        await AuthStore.clearTokens();
        await SessionStore.clearLoginFlags();
        return false;
      }
      final map = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
      await AuthStore.saveTokens(
        accessToken: map['access_token'] as String,
        refreshToken: map['refresh_token'] as String,
      );
      return true;
    } catch (_) {
      await AuthStore.clearTokens();
      await SessionStore.clearLoginFlags();
      return false;
    } finally {
      _refreshing = false;
    }
  }

  Future<Map<String, String>> _headers({
    required bool auth,
    bool json = false,
  }) async {
    final h = <String, String>{
      'Accept': 'application/json',
      if (json) 'Content-Type': 'application/json',
    };
    if (auth) {
      final token = await AuthStore.accessToken();
      if (token != null && token.isNotEmpty) {
        h['Authorization'] = 'Bearer $token';
      }
    }
    return h;
  }

  JsonMap? _decodeMap(http.Response res) {
    if (res.bodyBytes.isEmpty) return null;
    final decoded = jsonDecode(utf8.decode(res.bodyBytes));
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) return Map<String, dynamic>.from(decoded);
    return {'data': decoded};
  }

  ApiException _toException(http.Response res) {
    String code = 'HTTP_ERROR';
    String message = res.reasonPhrase ?? 'Ошибка запроса';
    dynamic details;
    try {
      final map = jsonDecode(utf8.decode(res.bodyBytes));
      if (map is Map && map['error'] is Map) {
        final err = Map<String, dynamic>.from(map['error'] as Map);
        code = err['code']?.toString() ?? code;
        message = err['message']?.toString() ?? message;
        details = err['details'];
      }
    } catch (_) {}
    return ApiException(
      statusCode: res.statusCode,
      code: code,
      message: message,
      details: details,
    );
  }

  void _logRequest(
    String method,
    Uri uri,
    Map<String, String> headers,
    String? body,
  ) {
    if (!logHttp) return;
    final buf = StringBuffer()
      ..writeln('┌─ HTTP → $method $uri')
      ..writeln('│ headers: ${_redactHeaders(headers)}');
    if (body != null && body.isNotEmpty) {
      buf.writeln('│ body: ${_prettyBody(body)}');
    }
    buf.write('└─');
    _logLine(buf.toString());
  }

  void _logResponse(String method, Uri uri, http.Response res) {
    if (!logHttp) return;
    final body = utf8.decode(res.bodyBytes, allowMalformed: true);
    final buf = StringBuffer()
      ..writeln('┌─ HTTP ← ${res.statusCode} $method $uri')
      ..writeln('│ body: ${_prettyBody(body)}')
      ..write('└─');
    _logLine(buf.toString());
  }

  static void _logLine(String text) {
    // debugPrint режет длинные строки — для JSON в терминале нужен print.
    // ignore: avoid_print
    print(text);
  }

  static Map<String, String> _redactHeaders(Map<String, String> headers) {
    final out = Map<String, String>.from(headers);
    final auth = out['Authorization'];
    if (auth != null && auth.startsWith('Bearer ')) {
      out['Authorization'] = 'Bearer ${_maskSecret(auth.substring(7))}';
    }
    return out;
  }

  static String _prettyBody(String raw) {
    if (raw.isEmpty) return '(empty)';
    try {
      final decoded = jsonDecode(raw);
      final redacted = _redactJson(decoded);
      var pretty = const JsonEncoder.withIndent('  ').convert(redacted);
      const max = 8000;
      if (pretty.length > max) {
        pretty = '${pretty.substring(0, max)}… (+${pretty.length - max} chars)';
      }
      return pretty;
    } catch (_) {
      if (raw.length > 2000) {
        return '${raw.substring(0, 2000)}… (+${raw.length - 2000} chars)';
      }
      return raw;
    }
  }

  static dynamic _redactJson(dynamic value) {
    if (value is Map) {
      return {
        for (final e in value.entries)
          e.key: _sensitiveKey(e.key.toString())
              ? _maskSecret(e.value?.toString() ?? '')
              : _redactJson(e.value),
      };
    }
    if (value is List) {
      return [for (final item in value) _redactJson(item)];
    }
    return value;
  }

  static bool _sensitiveKey(String key) {
    final k = key.toLowerCase();
    return k.contains('password') ||
        k.contains('token') ||
        k == 'authorization' ||
        k == 'code';
  }

  static String _maskSecret(String value) {
    if (value.isEmpty) return '(empty)';
    if (value.length <= 8) return '***';
    return '${value.substring(0, 4)}…${value.substring(value.length - 4)} (${value.length} chars)';
  }
}
