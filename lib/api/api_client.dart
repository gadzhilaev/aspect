import 'dart:convert';

import 'package:http/http.dart' as http;

import '../services/auth_store.dart';
import 'api_config.dart';
import 'api_exception.dart';

typedef JsonMap = Map<String, dynamic>;

/// HTTP-клиент с Bearer и авто-refresh при 401.
class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  final http.Client _http = http.Client();
  bool _refreshing = false;

  Uri _uri(String path, [Map<String, String>? query]) {
    final p = path.startsWith('/') ? path : '/$path';
    return Uri.parse('${ApiConfig.apiV1}$p').replace(queryParameters: query);
  }

  Future<JsonMap?> getJson(
    String path, {
    Map<String, String>? query,
    bool auth = true,
  }) async {
    final res = await _send(
      () async => _http.get(
        _uri(path, query),
        headers: await _headers(auth: auth),
      ),
      auth: auth,
    );
    return _decodeMap(res);
  }

  Future<JsonMap?> postJson(
    String path, {
    Object? body,
    bool auth = true,
  }) async {
    final res = await _send(
      () async => _http.post(
        _uri(path),
        headers: await _headers(auth: auth, json: true),
        body: body == null ? null : jsonEncode(body),
      ),
      auth: auth,
    );
    return _decodeMap(res);
  }

  Future<JsonMap?> patchJson(
    String path, {
    Object? body,
    bool auth = true,
  }) async {
    final res = await _send(
      () async => _http.patch(
        _uri(path),
        headers: await _headers(auth: auth, json: true),
        body: body == null ? null : jsonEncode(body),
      ),
      auth: auth,
    );
    return _decodeMap(res);
  }

  Future<JsonMap?> deleteJson(String path, {bool auth = true}) async {
    final res = await _send(
      () async => _http.delete(
        _uri(path),
        headers: await _headers(auth: auth),
      ),
      auth: auth,
    );
    return _decodeMap(res);
  }

  Future<http.Response> _send(
    Future<http.Response> Function() once, {
    required bool auth,
  }) async {
    var res = await once();
    if (auth && res.statusCode == 401) {
      final ok = await _tryRefresh();
      if (ok) {
        res = await once();
      }
    }
    if (res.statusCode >= 400) {
      throw _toException(res);
    }
    return res;
  }

  Future<bool> _tryRefresh() async {
    if (_refreshing) return false;
    final refresh = await AuthStore.refreshToken();
    if (refresh == null || refresh.isEmpty) return false;
    _refreshing = true;
    try {
      final res = await _http.post(
        _uri('/auth/refresh'),
        headers: await _headers(auth: false, json: true),
        body: jsonEncode({'refresh_token': refresh}),
      );
      if (res.statusCode >= 400) {
        await AuthStore.clearTokens();
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
}
