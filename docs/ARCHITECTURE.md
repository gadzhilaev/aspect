# Архитектура Аспект

## Назначение

Прототип персонализированной новостной аналитики для бизнеса (хакатон «Альфа-Будущее»).  
Цепочка для пользователя: **что произошло → почему касается компании → на чём основан вывод → какие действия рассмотреть**.

Не является модулем интернет-банка Альфа-Бизнес. Кнопка «войти через Альфа-Бизнес» — **демо-вход** в приложении, не банковский SSO.

## Компоненты

```
┌─────────────────┐     HTTPS/JSON      ┌──────────────────────┐
│  Flutter app    │◄───────────────────►│  FastAPI (aspect-api) │
│  lib/           │   Bearer JWT        │  backend/             │
└─────────────────┘                     └──────────┬───────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────┐
                    ▼                              ▼                          ▼
             SQLite stand.db              storage/ (bank PDF/OCR)     external:
             + case links                 + client_error_reports      news sources,
                                                                      hackathon LLM
┌──────────────────┐   ┌─────────────────────┐
│ news_scheduler   │   │ telegram-worker     │  (опционально)
└──────────────────┘   └─────────────────────┘
```

| Слой | Путь | Роль |
|------|------|------|
| Клиент | `lib/`, `android/`, `ios/` | UI, сессия, лента, чат, компания |
| API | `backend/app/` | Auth, компании, events, impact, assistant, bank-materials |
| Данные стенда | вне Git (`/stand` или пакет) | `stand.db`, `storage/`, `demo_password.local` |
| Scheduler | контейнер / процесс | RSS / CBR / GDELT → события |
| LLM | hackathon gateway | ассистент в `COMPETITION_MODE` |

## Данные о компании

Три независимых слоя (не путать):

1. **Ручной профиль / digital twin** — то, что пользователь заполнил (продукты, рынки, города, финансы). Узлы `company_nodes`, industry-profile в preferences.
2. **Реестр / DaData (ИНН)** — публичные реквизиты в `companies` (`hq_region`, `tax_id`). **Не** создаёт case-link.
3. **Конкурсный справочник (case CSV)** — организации `U_*`, таблица `case_org_company_links`. На стенде привязаны demo A/B (`U_264` / `U_92`). Ручная компания обычно `not_linked`.

Лента может показывать:

- `company_calculated` — есть `EventImpact`;
- `case_profile_match` / `industry_profile_match` — тематическое совпадение, **не** численный impact;
- `monitoring_only` — сигнал релевантен, данных для модели влияния мало.

## Ассистент

- Создание разговора по событию × компании.
- Без usable impact: `assessment_state=calculation_unavailable`, обсуждение всё равно возможно.
- В competition mode — agent loop + hackathon provider; таймаут цикла порядка десятков секунд.
- Материалы банка передаются в контекст с provenance; scope OCR — `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS`.

## Клиентская сессия

- JWT в `SharedPreferences` (`AuthStore`).
- Локальный черновик профиля — `SessionStore` / `OnboardingData`.
- Должность пользователя (`job_role`) — в `preferences` пользователя на API.
- Отчёты о сбоях логина: `POST /api/v1/diagnostics/client-error` → таблица `client_error_reports`.

## Темы UI

Палитра: `lib/theme/app_colors.dart`. Карточки: `AppColors.card` + равномерный `Border.all` (несмешивать с `borderRadius` и разной толщиной сторон — иначе Flutter не рисует содержимое).
