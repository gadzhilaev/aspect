import 'package:permission_handler/permission_handler.dart';

import 'session_store.dart';

/// Проверка и запрос системного разрешения на уведомления.
abstract final class NotificationPermission {
  static Future<bool> isGranted() async {
    final status = await Permission.notification.status;
    return status.isGranted || status.isProvisional || status.isLimited;
  }

  static Future<PermissionStatus> status() => Permission.notification.status;

  /// Можно ли показать системный диалог разрешения.
  static Future<bool> canRequestSystemDialog() async {
    final status = await Permission.notification.status;
    if (status.isGranted || status.isProvisional || status.isLimited) {
      return false;
    }
    if (status.isPermanentlyDenied || status.isRestricted) {
      return false;
    }
    return true;
  }

  /// Системный диалог (если ещё можно запросить).
  static Future<bool> request() async {
    final status = await Permission.notification.request();
    final granted =
        status.isGranted || status.isProvisional || status.isLimited;
    await _persist(granted);
    return granted;
  }

  /// Запросить разрешение или открыть настройки ОС, если диалог недоступен.
  static Future<bool> requestOrOpenSettings() async {
    if (await isGranted()) return true;
    if (await canRequestSystemDialog()) {
      return request();
    }
    await openSystemSettings();
    final granted = await isGranted();
    await _persist(granted);
    return granted;
  }

  /// Открыть системные настройки приложения (вкл/выкл уведомления).
  static Future<bool> openSystemSettings() => openAppSettings();

  static Future<void> _persist(bool granted) async {
    await SessionStore.saveSettings(
      (await SessionStore.loadSettings()).copyWith(pushNotifications: granted),
    );
  }
}
