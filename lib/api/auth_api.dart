import '../services/auth_store.dart';
import 'api_client.dart';

class AuthApi {
  AuthApi._();
  static final AuthApi instance = AuthApi._();

  final _client = ApiClient.instance;

  Future<Map<String, dynamic>> register({
    required String email,
    required String password,
    required String displayName,
  }) async {
    final res = await _client.postJson(
      '/auth/register',
      auth: false,
      body: {
        'email': email,
        'password': password,
        'display_name': displayName,
      },
    );
    return res ?? {};
  }

  Future<void> verifyEmail({
    required String email,
    required String code,
  }) async {
    await _client.postJson(
      '/auth/verify-email',
      auth: false,
      body: {'email': email, 'code': code},
    );
  }

  Future<void> login({
    required String email,
    required String password,
  }) async {
    final res = await _client.postJson(
      '/auth/login',
      auth: false,
      body: {'email': email, 'password': password},
    );
    if (res == null) throw StateError('Empty login response');
    await AuthStore.saveTokens(
      accessToken: res['access_token'] as String,
      refreshToken: res['refresh_token'] as String,
    );
    await refreshMe();
  }

  Future<Map<String, dynamic>> me() async {
    final res = await _client.getJson('/users/me');
    return res ?? {};
  }

  Future<Map<String, dynamic>> refreshMe() async {
    final me = await this.me();
    final companies = (me['companies'] as List?) ?? const [];
    String? companyId;
    String? companyName;
    if (companies.isNotEmpty) {
      final first = Map<String, dynamic>.from(companies.first as Map);
      companyId = first['company_id']?.toString();
      companyName = first['name']?.toString();
    }
    await AuthStore.saveProfile(
      userId: me['id']?.toString() ?? '',
      email: me['email']?.toString() ?? '',
      displayName: me['display_name']?.toString() ?? '',
      companyId: companyId,
      companyName: companyName,
    );
    return me;
  }

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _client.postJson(
      '/users/me/change-password',
      body: {
        'current_password': currentPassword,
        'new_password': newPassword,
      },
    );
  }

  Future<void> deleteAccount({required String password}) async {
    await _client.deleteJson(
      '/users/me',
      body: {'password': password},
    );
    await AuthStore.clearAll();
  }

  Future<void> patchPreferences({
    String? language,
    String? themeMode,
    bool? registrationComplete,
  }) async {
    await _client.patchJson(
      '/users/me/preferences',
      body: {
        'language': ?language,
        'theme_mode': ?themeMode,
        'registration_complete': ?registrationComplete,
      },
    );
  }

  /// Помечает аккаунт завершённым — с этого момента email «занят».
  Future<void> markRegistrationComplete() async {
    await patchPreferences(registrationComplete: true);
  }

  Future<void> logout() async {
    await AuthStore.clearAll();
  }
}
