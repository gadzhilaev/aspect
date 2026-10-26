import 'api_client.dart';

class EventsApi {
  EventsApi._();
  static final EventsApi instance = EventsApi._();

  final _client = ApiClient.instance;

  Future<Map<String, dynamic>> getEvent(
    String eventId, {
    String? companyId,
  }) async {
    final res = await _client.getJson(
      '/events/$eventId',
      query: {
        if (companyId != null && companyId.isNotEmpty) 'company_id': companyId,
      },
    );
    return res ?? {};
  }

  Future<Map<String, dynamic>?> getImpact(
    String eventId, {
    required String companyId,
  }) async {
    try {
      return await _client.getJson(
        '/events/$eventId/impact',
        query: {'company_id': companyId},
      );
    } catch (_) {
      return null;
    }
  }

  Future<Map<String, dynamic>> bankEvidence(
    String eventId, {
    String? companyId,
  }) async {
    final res = await _client.getJson(
      '/events/$eventId/bank-evidence',
      query: {
        if (companyId != null && companyId.isNotEmpty) 'company_id': companyId,
      },
    );
    return res ?? {};
  }

  Future<Map<String, dynamic>> createAssistantConversation({
    required String eventId,
    required String companyId,
  }) async {
    final res = await _client.postJson(
      '/events/$eventId/assistant/conversations',
      body: {'company_id': companyId},
    );
    return res ?? {};
  }

  Future<Map<String, dynamic>> postMessage({
    required String conversationId,
    required String content,
    required String clientMessageId,
  }) async {
    final res = await _client.postJson(
      '/assistant/conversations/$conversationId/messages',
      body: {
        'content': content,
        'client_message_id': clientMessageId,
      },
      // Сервер крутит LLM до ~90 с; обычный HTTP timeout 20 с обрывал ответ.
      timeout: ApiClient.assistantTimeout,
    );
    return res ?? {};
  }

  Future<Map<String, dynamic>> listMessages(String conversationId) async {
    final res =
        await _client.getJson('/assistant/conversations/$conversationId/messages');
    if (res == null) return {'items': <dynamic>[]};
    // API returns a bare list; ApiClient wraps it as {'data': [...]}.
    if (res['data'] is List) return {'items': res['data']};
    if (res['items'] is List) return res;
    if (res['messages'] is List) return {'items': res['messages']};
    return res;
  }
}
