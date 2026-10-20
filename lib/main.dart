import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'screens/splash_screen.dart';
import 'theme/app_colors.dart';
import 'theme/app_typography.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.dark,
      statusBarBrightness: Brightness.light,
      systemNavigationBarColor: AppColors.brandRed,
      systemNavigationBarIconBrightness: Brightness.dark,
    ),
  );
  runApp(const AspectApp());
}

class AspectApp extends StatelessWidget {
  const AspectApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Аспект',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        fontFamily: AppTypography.family,
        // Exact brand palette — avoid ColorScheme.fromSeed (it boosts vibrancy).
        colorScheme: const ColorScheme.light(
          primary: AppColors.brandRed,
          onPrimary: Colors.white,
          secondary: AppColors.brandRed,
          onSecondary: Colors.white,
          surface: AppColors.surface,
          onSurface: AppColors.textPrimary,
          error: AppColors.brandRed,
          onError: Colors.white,
        ),
        scaffoldBackgroundColor: AppColors.surface,
        primaryColor: AppColors.brandRed,
      ),
      home: const SplashScreen(),
    );
  }
}
