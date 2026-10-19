import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'package:aspect/main.dart';
import 'package:aspect/screens/splash_screen.dart';

void main() {
  testWidgets('App opens on splash screen', (WidgetTester tester) async {
    await tester.pumpWidget(const AspectApp());

    expect(find.byType(SplashScreen), findsOneWidget);
    expect(find.byType(SvgPicture), findsOneWidget);

    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
  });
}
