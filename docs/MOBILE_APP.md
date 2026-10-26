# Flutter-приложение Аспект

Версия: `1.0.0+1` (`pubspec.yaml`). Package: `ru.gadzhilaev.aspect`.

## Запуск

```bash
flutter pub get
flutter run
# другое API:
flutter run --dart-define=API_BASE=http://127.0.0.1:8020
```

По умолчанию production base URL: `https://gadzhilaev.ru/aspekt-api`  
(`lib/api/api_config.dart`).

Release APK:

```bash
flutter build apk --release
# артефакт: build/app/outputs/flutter-apk/app-release.apk
# в корень репозитория APK не класть (gitignore `*.apk`)
```

На GitHub: [releases/tag/v1.0.0](https://github.com/gadzhilaev/aspect/releases/tag/v1.0.0).

## Структура `lib/`

| Путь | Назначение |
|------|------------|
| `api/` | HTTP-клиент, auth, companies, events, диагностика |
| `screens/login_screen.dart`, `register_screen.dart` | Вход / регистрация |
| `screens/onboarding/` | Онбординг компании |
| `screens/main/` | Оболочка: Обзор, События, Сценарии, Компания |
| `screens/main/news_detail_screen.dart` | Карточка события + банк + CTA в чат |
| `screens/main/chat_screen.dart` | «Обсудить с Аспект» |
| `screens/main/action_plan_screen.dart` | Варианты действий |
| `screens/main/saved_plan_screen.dart` | Сохранённый план / чеклист |
| `theme/` | Цвета, типографика, scale |
| `services/` | AuthStore, SessionStore, уведомления |
| `models/onboarding_data.dart` | Локальный профиль |

## Экраны (кратко)

1. **Splash** → login или Main (с таймаутом sync `/users/me`).
2. **Вход** — email/пароль; ошибка показывается полностью и уходит в diagnostics.
3. **Компания** — карточка, конкурсный справочник (linked / not_linked), плитки контекста.
4. **Обзор / События** — лента с why-label и приоритетом.
5. **Деталь новости** — факт, риск/возможность, аналитика банка отдельно от AI, чат.
6. **Чат** — история, chips, thinking-фазы, скролл вниз при открытии и после send; timeout ассистента 120 с на клиенте.

## API-клиент

`ApiClient` (`lib/api/api_client.dart`):

- Bearer + refresh на 401;
- таймаут обычных запросов ~20 с, ассистента — 120 с;
- в debug — лог запросов/ответов в консоль `flutter run` (токены маскируются);
- `reportClientError` → `POST /diagnostics/client-error`.

## Тёмная тема

- Текст: `AppColors.textPrimary` / `textSecondary` (не `Colors.black`).
- Текст на красных кнопках: `AppColors.onBrand`.
- Карточки: `AppColors.card` + `Border.all(AppColors.border)`; красный акцент слева — отдельной полоской в `Row`, не через non-uniform `Border` + `borderRadius`.

## Известные ограничения клиента

- Вкладка «Сценарии» частично демонстрационная; полный finance-flow на backend.
- Role/география синкаются на API при редактировании; старые сессии без `job_role` нужно один раз заполнить в «Мои данные».
- Release Android: нужна актуальная `shared_preferences_android` ≥ 2.5.2 (R8 / JNI); см. `android/app/proguard-rules.pro`.
