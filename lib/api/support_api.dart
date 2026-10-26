import '../services/auth_store.dart';
import 'api_client.dart';

class SupportApi {
  SupportApi._();
  static final SupportApi instance = SupportApi._();

  final _client = ApiClient.instance;

  Future<Map<String, dynamic>> getThread({String? companyId}) async {
    final query = <String, String>{
      if (companyId != null && companyId.isNotEmpty) 'company_id': companyId,
    };
    final res = await _client.getJson(
      '/support/thread',
      query: query.isEmpty ? null : query,
    );
    return res ?? {};
  }

  Future<List<Map<String, dynamic>>> listMessages({String? afterId}) async {
    final query = <String, String>{
      if (afterId != null && afterId.isNotEmpty) 'after_id': afterId,
    };
    final res = await _client.getJson(
      '/support/thread/messages',
      query: query.isEmpty ? null : query,
    );
    if (res == null) return const [];
    if (res['data'] is List) {
      return [
        for (final raw in res['data'] as List)
          if (raw is Map) Map<String, dynamic>.from(raw),
      ];
    }
    // Bare list wrapped oddly — unlikely, but keep safe.
    return const [];
  }

  Future<Map<String, dynamic>> postMessage({
    required String content,
    required String clientMessageId,
    String? companyId,
  }) async {
    final company = companyId ?? await AuthStore.companyId();
    final res = await _client.postJson(
      '/support/thread/messages',
      body: {
        'content': content,
        'client_message_id': clientMessageId,
        if (company != null && company.isNotEmpty) 'company_id': company,
      },
    );
    return res ?? {};
  }

  Future<Map<String, dynamic>> closeThread() async {
    final res = await _client.postJson('/support/thread/close', body: {});
    return res ?? {};
  }
}
