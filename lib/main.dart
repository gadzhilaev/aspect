import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'app/app_controller.dart';
import 'l10n/app_localizations.dart';
import 'screens/splash_screen.dart';
import 'theme/app_colors.dart';
import 'theme/app_typography.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppController.instance.load();
  SystemChrome.setSystemUIOverlayStyle(AppColors.systemOverlay);
  runApp(const AspectApp());
}

class AspectApp extends StatefulWidget {
  const AspectApp({super.key});

  @override
  State<AspectApp> createState() => _AspectAppState();
}

class _AspectAppState extends State<AspectApp> with WidgetsBindingObserver {
  final _controller = AppController.instance;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _controller.addListener(_onController);
  }

  @override
  void dispose() {
    _controller.removeListener(_onController);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _onController() {
    if (mounted) setState(() {});
  }

  @override
  void didChangePlatformBrightness() {
    _controller.syncPlatformBrightness();
  }

  ThemeData _theme(Brightness brightness) {
    final prev = AppColors.brightness;
    AppColors.applyBrightness(brightness);
    final isDark = brightness == Brightness.dark;
    final data = ThemeData(
      brightness: brightness,
      fontFamily: AppTypography.family,
      colorScheme: ColorScheme(
        brightness: brightness,
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
      cardColor: AppColors.surfaceRaised,
      dividerColor: AppColors.divider,
      dialogTheme: DialogThemeData(
        backgroundColor: AppColors.surfaceRaised,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: AppColors.surface,
        foregroundColor: AppColors.textPrimary,
        elevation: 0,
        systemOverlayStyle: AppColors.systemOverlay,
      ),
      inputDecorationTheme: InputDecorationTheme(
        hintStyle: TextStyle(color: AppColors.textHint),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: isDark ? AppColors.surfaceRaised : AppColors.textInk,
      ),
    );
    // Не оставляем глобальную палитру на brightness последней собранной темы.
    AppColors.applyBrightness(prev);
    return data;
  }

  @override
  Widget build(BuildContext context) {
    final locale = _controller.locale;
    final l10n = AppLocalizations(locale);
    final resolved =
        _controller.isDark ? Brightness.dark : Brightness.light;
    AppColors.applyBrightness(resolved);

    return MaterialApp(
      title: l10n.appName,
      debugShowCheckedModeBanner: false,
      locale: locale,
      supportedLocales: const [Locale('ru'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      theme: _theme(Brightness.light),
      darkTheme: _theme(Brightness.dark),
      themeMode: _controller.themeMode,
      builder: (context, child) {
        final brightness = Theme.of(context).brightness;
        AppColors.applyBrightness(brightness);
        SystemChrome.setSystemUIOverlayStyle(AppColors.systemOverlay);
        return wrapWithL10n(
          locale: locale,
          child: AnnotatedRegion<SystemUiOverlayStyle>(
            value: AppColors.systemOverlay,
            child: child ?? const SizedBox.shrink(),
          ),
        );
      },
      home: const SplashScreen(),
    );
  }
}
