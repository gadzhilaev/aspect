import 'dart:convert';

class ApiException implements Exception {
  ApiException({
    required this.statusCode,
    required this.code,
    required this.message,
    this.details,
    this.underlyingCause,
  });

  final int statusCode;
  final String code;
  final String message;
  final dynamic details;
  /// Raw network / transport error when statusCode is 0.
  final String? underlyingCause;

  bool get isUnauthorized => statusCode == 401;
  bool get isForbidden => statusCode == 403;

  /// Full text for UI and client-error reports (not a generic stub).
  String get userDisplayMessage {
    final lines = <String>[message];
    final meta = <String>[];
    if (statusCode != 0) meta.add('HTTP $statusCode');
    if (code.isNotEmpty && code != 'HTTP_ERROR') meta.add(code);
    if (meta.isNotEmpty) lines.add(meta.join(' · '));
    final detailText = _formatDetails(details);
    if (detailText.isNotEmpty) lines.add(detailText);
    final cause = underlyingCause?.trim();
    if (cause != null && cause.isNotEmpty) {
      lines.add(cause);
    }
    return lines.join('\n');
  }

  static String _formatDetails(dynamic value) {
    if (value == null) return '';
    if (value is String) return value.trim();
    try {
      return const JsonEncoder.withIndent('  ').convert(value);
    } catch (_) {
      return value.toString();
    }
  }

  @override
  String toString() => 'ApiException($statusCode $code: $message)';
}
