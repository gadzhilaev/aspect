import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/app_colors.dart';
import 'welcome_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: AppColors.brandRed,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
    _openWelcome();
  }

  Future<void> _openWelcome() async {
    await Future<void>.delayed(const Duration(milliseconds: 1600));
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      PageRouteBuilder<void>(
        transitionDuration: const Duration(milliseconds: 450),
        pageBuilder: (_, animation, _) => FadeTransition(
          opacity: animation,
          child: const WelcomeScreen(),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    return Scaffold(
      backgroundColor: AppColors.brandRed,
      body: SizedBox.expand(
        child: SvgPicture.asset(
          'assets/images/splash.svg',
          fit: BoxFit.fitHeight,
          alignment: Alignment.center,
          width: size.width,
          height: size.height,
        ),
      ),
    );
  }
}
