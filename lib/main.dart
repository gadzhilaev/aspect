import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'screens/splash_screen.dart';
import 'theme/app_colors.dart';

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
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.brandRed,
          primary: AppColors.brandRed,
        ),
        scaffoldBackgroundColor: AppColors.brandRed,
      ),
      home: const SplashScreen(),
    );
  }
}
