# Kotlin / JNI keep rules (shared_preferences_android R8; see plugin consumer-rules.pro).
# Without these, release login dies after /auth/login when saving JWT to prefs.
-keep class kotlin.Unit { *; }
-keep class kotlin.Result { *; }
-keep class kotlin.Result$Failure { *; }
-keep class kotlin.coroutines.Continuation { *; }
-keep class kotlin.coroutines.intrinsics.CoroutineSingletons { *; }
-keep class kotlin.coroutines.intrinsics.IntrinsicsKt { *; }
-keep class io.flutter.plugins.sharedpreferences.** { *; }
-keep class com.github.dart_lang.jni.** { *; }
