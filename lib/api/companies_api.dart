import 'api_client.dart';

class CompaniesApi {
  CompaniesApi._();
  static final CompaniesApi instance = CompaniesApi._();

  final _client = ApiClient.instance;

  /// Поиск в реестре: ИНН или название компании (`query`).
  Future<Map<String, dynamic>> lookupCompany(String query) async {
    final res = await _client.postJson(
      '/company-registry/lookup',
      body: {'query': query},
    );
    return res ?? {};
  }

  @Deprecated('Use lookupCompany')
  Future<Map<String, dynamic>> lookupByInn(String inn) => lookupCompany(inn);

  Future<Map<String, dynamic>> confirmLookup({
    required String lookupId,
    required String candidateId,
  }) async {
    final res = await _client.postJson(
      '/company-registry/confirm',
      body: {
        'lookup_id': lookupId,
        'candidate_id': candidateId,
      },
    );
    return res ?? {};
  }

  Future<Map<String, dynamic>> createCompany({
    required String name,
    String? industry,
    String? taxId,
  }) async {
    final res = await _client.postJson(
      '/companies',
      body: {
        'name': name,
        if (industry != null && industry.isNotEmpty) 'industry': industry,
        if (taxId != null && taxId.isNotEmpty) 'tax_id': taxId,
      },
    );
    return res ?? {};
  }

  Future<Map<String, dynamic>> getProfile(String companyId) async {
    final res = await _client.getJson('/companies/$companyId/profile');
    return res ?? {};
  }

  Future<Map<String, dynamic>> getContext(String companyId) async {
    final res = await _client.getJson('/companies/$companyId/context');
    return res ?? {};
  }

  Future<Map<String, dynamic>> getDashboard(String companyId) async {
    final res = await _client.getJson('/companies/$companyId/dashboard');
    return res ?? {};
  }

  Future<Map<String, dynamic>> listEvents(
    String companyId, {
    int limit = 20,
    String? cursor,
  }) async {
    final res = await _client.getJson(
      '/companies/$companyId/events',
      query: {
        'limit': '$limit',
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
      },
    );
    return res ?? {};
  }

  Future<Map<String, dynamic>> patchCompany(
    String companyId,
    Map<String, dynamic> body,
  ) async {
    final res = await _client.patchJson('/companies/$companyId', body: body);
    return res ?? {};
  }

  Future<Map<String, dynamic>> patchFinance(
    String companyId,
    Map<String, dynamic> body,
  ) async {
    final res =
        await _client.patchJson('/companies/$companyId/finance', body: body);
    return res ?? {};
  }

  Future<Map<String, dynamic>> addNode(
    String companyId, {
    required String nodeType,
    required String name,
    String? country,
  }) async {
    final res = await _client.postJson(
      '/companies/$companyId/nodes',
      body: {
        'node_type': nodeType,
        'name': name,
        if (country != null && country.isNotEmpty) 'country': country,
      },
    );
    return res ?? {};
  }

  Future<Map<String, dynamic>> getIndustryProfile(String companyId) async {
    final res = await _client.getJson('/companies/$companyId/industry-profile');
    return res ?? {};
  }

  Future<Map<String, dynamic>> patchIndustryProfile(
    String companyId,
    Map<String, dynamic> body,
  ) async {
    final res = await _client.patchJson(
      '/companies/$companyId/industry-profile',
      body: body,
    );
    return res ?? {};
  }

  Future<void> completeProfile(String companyId) async {
    await _client.postJson('/companies/$companyId/profile/complete');
  }

  Future<Map<String, dynamic>> buildDigitalTwin(String companyId) async {
    final res =
        await _client.postJson('/companies/$companyId/digital-twin/build');
    return res ?? {};
  }

  Future<Map<String, dynamic>> notificationSettings(String companyId) async {
    final res =
        await _client.getJson('/companies/$companyId/notification-settings');
    return res ?? {};
  }

  Future<Map<String, dynamic>> telegramLinkToken(String companyId) async {
    final res = await _client.postJson(
      '/telegram/link-token',
      body: {'company_id': companyId},
    );
    return res ?? {};
  }
}
