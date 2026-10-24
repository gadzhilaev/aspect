import 'package:flutter/material.dart';

import '../screens/main/main_shell.dart';
import '../screens/notification_permission_screen.dart';
import '../services/notification_permission.dart';

/// После входа / регистрации: при отсутствии разрешения — экран-объяснение.
Future<void> enterMainApp(
  BuildContext context, {
  required String userName,
}) async {
  final granted = await NotificationPermission.isGranted();
  if (!context.mounted) return;

  final Widget next = granted
      ? MainShell(userName: userName)
      : NotificationPermissionScreen(
          userName: userName,
          allowSkip: false,
        );

  Navigator.of(context).pushAndRemoveUntil(
    PageRouteBuilder<void>(
      transitionDuration: Duration.zero,
      reverseTransitionDuration: Duration.zero,
      pageBuilder: (_, _, _) => next,
    ),
    (_) => false,
  );
}
