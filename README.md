# Аспект

Персонализированная новостная аналитика для бизнеса.

Сервис помогает ответить на цепочку: **что произошло → почему это может касаться компании → на каких данных основан вывод → какие действия можно рассмотреть**. Клиент — Flutter-приложение; API — FastAPI (каталог `backend/`).

Это прототип для хакатона «Альфа-Будущее», **не** встройка в интернет-банк Альфа-Бизнес. Кнопка «войти через Альфа-Бизнес» в приложении — демо-вход, не банковский SSO.

| | |
|--|--|
| Ветка | `main` |
| Commit / тег сдачи | [`v1.0.0`](https://github.com/gadzhilaev/aspect/releases/tag/v1.0.0) |
| Клиент в этом репозитории | Flutter (`lib/`) |
| API в этом репозитории | `backend/` |
| React web | **не** входит в этот репозиторий |

---

## Быстрый старт для жюри

### Публичные адреса

| | |
|--|--|
| Демо / стенд | https://alfa-aspect.ru/ |
| Репозиторий | https://github.com/gadzhilaev/aspect |
| Релиз сдачи | https://github.com/gadzhilaev/aspect/releases/tag/v1.0.0 |

Локальный конкурсный API после запуска стенда обычно на порту **8020**:

```bash
curl -fsS http://127.0.0.1:8020/health
```

### Demo-учётные данные

Выдаются **отдельно** (файл `demo_password.local` пакета данных стенда, не из Git).

| | |
|--|--|
| Demo A | `competition-demo-a@example.com` → компания · `U_264` |
| Demo B | `competition-demo-b@example.com` → компания · `U_92` |
| Пароль | только в `demo_password.local` пакета |

Пароли, JWT и API-ключи в репозиторий и в этот файл **не** публикуются.

### Короткий проверочный маршрут

1. Войти demo A (или демо-кнопкой Альфа-Бизнес → далее стендовый логин с JWT).
2. Открыть компанию: отрасль / case-контекст при наличии связи.
3. Лента «для вас» → карточка с why-label (case / industry / impact).
4. Карточка новости: факт, связь с компанией, блок аналитики банка отдельно от вывода модели.
5. Материалы банка / PDF (с сессией Bearer).
6. «Обсудить с Аспект» — при настроенном ключе шлюза.

Пошагово: [`docs/JURY_MOBILE_SCENARIO.md`](docs/JURY_MOBILE_SCENARIO.md).  
Подключение к стенду: [`docs/MOBILE_STAND_CONNECTION.md`](docs/MOBILE_STAND_CONNECTION.md).

### Демонстрационное событие

На подготовленном стенде для разбора удобно событие **ключевой ставки** (синтетическое, отбор по `case_profile_match`, не как готовый Impact-расчёт). Идентификатор и OCR-scope — в `stand_manifest.json` пакета данных (`AGENT_DEMO_EVENT_ID` / `ocr_run_ids`). AI-цитирование опирается в первую очередь на материал Policy Rate; остальные PDF банка доступны как поиск / оригинал при настроенном scope.

---

## Возможности

Реализовано в коде этого репозитория (полный UX зависит от подготовленной БД и env):

| Возможность | Кратко |
|-------------|--------|
| Общая и персональная лента | Публичные новости и события компании с основаниями попадания в ленту |
| Профиль компании и отраслевые интересы | Case-контекст (CSV), ручной twin, industry-profile (продукты / бренды / рынки) |
| Связь новости с компанией | Why-label, case/industry match, Impact при достаточных данных twin |
| AI-ассистент | Обсуждение события; в конкурсном режиме — hackathon provider + agent loop |
| Банковские материалы | Метаданные, фрагменты с источниками, PDF по Bearer |
| Сценарии и решения | На **backend** (финансы → пересчёт → compare-scenarios → подтверждение). В Flutter вкладка «Сценарии» / часть finance UI **не** полностью подключены к этим API — см. ограничения |
| Telegram | Привязка и outbox в коде; по умолчанию **выключены**. Нужны токен, worker/polling или webhook, осознанное включение news |
| Обновление новостей | Отдельный процесс `news_scheduler` (RSS / CBR / GDELT по whitelist); не стартует вместе с «голым» API |

**Отбор vs внешний поиск.** Лента отбирает уже загруженные в корпус публикации (и результаты scheduler, если он запущен). Отраслевой профиль формирует общие search-interests для scheduler/GDELT — это **не** универсальный поиск «любых новостей интернета» из GET ленты и не обещание полного покрытия рынка.

---

## Источники и достоверность

- Новости поступают из **настроенных** источников (whitelist RSS, CBR, GDELT-запросы) либо уже лежат в корпусе стенда.
- Конкурсные CSV содержат **обезличенные** профили и связи (`U_*`), не реквизиты реальных юрлиц в демо-ярлыках.
- Банковская аналитика (PDF / OCR / фрагменты) хранится **отдельно** от новостного корпуса и отдаётся через bank-materials API.
- Не все PDF/фрагменты разрешены для AI-цитирования: scope задаётся `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS`; часть материалов — только просмотр / поиск.
- **Индекс влияния ≠ убыток** и не процент потерь (`score_kind=company_calculated` — модельный индекс).
- **Качество данных (confidence) ≠ вероятность** правильного ответа.
- Тематическое / профильное совпадение (`case_profile_match`, `industry_profile_match`) **не** является расчётом влияния.
- Различайте: **факт события**, **прогноз/аналитика банка**, **what-if допущение** пользователя в сценариях.

Подробнее: [`backend/docs/ASSESSMENT_TRUST_AUDIT.md`](backend/docs/ASSESSMENT_TRUST_AUDIT.md).

---

## Подключение ИИ для проверки

При проверке **развёрнутого нами** сервиса ключ уже должен быть настроен на сервере — вводить его в приложении не требуется.

При **самостоятельном** запуске для проверки AI-функций необходимо задать действующий API-ключ, выданный команде организаторами, в серверной переменной `HACKATHON_API_KEY` и перезапустить API. Ключ передаётся отдельно по приватному каналу и **не** входит в репозиторий.

Задание переменной подключает ключ к приложению, но **не** активирует и **не** продлевает его у провайдера. Если организаторы отключили ключ или срок его действия истёк, требуется восстановление доступа со стороны организаторов.

Безопасный пример (значения совпадают с [`backend/.env.example`](backend/.env.example)):

```env
COMPETITION_MODE=true
ASSISTANT_PROVIDER=hackathon
ASSISTANT_AGENT_LOOP=true
HACKATHON_API_KEY=<ключ_команды_передаётся_отдельно>
HACKATHON_BASE_URL=https://changellenge.up.railway.app/v1
HACKATHON_MODEL=deepseek/deepseek-v4.1-flash
```

Пояснения:

- Секрет задаётся **только на backend** (process env / compose env_file). Не в Flutter, не в `--dart-define`, не в `VITE_*`.
- При отсутствии ключа или сбое провайдера AI-функции недоступны (`PROVIDER_UNAVAILABLE` и др.). Скрытая подмена live-ответа mock **не** используется в `COMPETITION_MODE`.
- Метка провайдера в `/health` или стартовое сообщение **не** доказывают успешную генерацию ответа.
- По инструкции организаторов бюджет общий для команды: **500 ₽/сутки**, сброс в **03:00 МСК**; условия могут измениться организаторами.
- При ответе шлюза `Budget has been exceeded` — дождаться сброса или обратиться к организаторам; **не** повторять запрос бесконечно (клиент не делает авто-retry по бюджету).

Разрешённые ID моделей и диагностика: [`backend/docs/HACKATHON_PROVIDER.md`](backend/docs/HACKATHON_PROVIDER.md).

---

## Локальный запуск

**Основной поддерживаемый путь для полного демо:** код из этого репозитория + **подготовленный пакет данных стенда** (БД + `storage/` + `stand.env`), полученный по согласованному приватному каналу. Пакет **не** хранится в Git (`_competition_stand/` в `.gitignore`).

Требования: **Python 3.12** (см. `backend/.python-version`), Flutter stable (SDK по `pubspec.yaml`), опционально Docker Engine + Compose.

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install --require-hashes -r requirements.lock
```

Скопируйте профиль из пакета стенда (пути к БД и storage — **абсолютные** или относительно cwd):

```text
DATABASE_URL=sqlite:////…/stand.db
BANK_MATERIALS_STORAGE_ROOT=/…/storage
BANK_MATERIALS_ALLOWED_OCR_RUN_IDS=<из stand.env / stand_manifest.json пакета>
CASE_CONTEXT_SLOT_KEY=competition_default
COMPETITION_MODE=true
ASSISTANT_PROVIDER=hackathon
ASSISTANT_AGENT_LOOP=true
HACKATHON_BASE_URL=https://changellenge.up.railway.app/v1
HACKATHON_MODEL=deepseek/deepseek-v4.1-flash
# HACKATHON_API_KEY=…   только при проверке AI
SECRET_KEY=<локальный секрет стенда>
```

```bash
alembic upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8020
```

OpenAPI UI: `http://127.0.0.1:8020/docs`  
Контракт: [`backend/contracts/openapi.json`](backend/contracts/openapi.json)

Не выполняйте runtime `ALTER TABLE` и `seed` / `ensure_demo` **поверх** готовой конкурсной БД.

### 2. Flutter

```bash
flutter pub get
# симулятор / эта машина:
flutter run
# физическое устройство в той же сети:
flutter run --dart-define=API_BASE=http://<LAN-IP-хоста>:8020
```

По умолчанию клиент ждёт API на порту **8020** ([`lib/api/api_config.dart`](lib/api/api_config.dart)): iOS Simulator / desktop → `127.0.0.1`, Android emulator → `10.0.2.2`.

### Docker (опционально)

Compose в корне: [`docker-compose.competition.yml`](docker-compose.competition.yml) (API + `news_scheduler`; UI — Flutter). Шаблон env: [`backend/.env.competition.example`](backend/.env.competition.example).

API-контейнер ожидает уже готовый volume `/stand` (`stand.db`, `storage/`, `stand_status.json`, `stand.env`).  
В **этом** дереве исходников модуль `app.services.competition_stand` **отсутствует** — one-shot bootstrap из CSV/PDF/OCR через Compose/скрипт **не обещается**. Для демо используйте переданный готовый пакет данных.

Проверка Compose на синтетических fixtures (не полный production-стенд): [`backend/docs/COMPETITION_DOCKER_VERIFICATION.md`](backend/docs/COMPETITION_DOCKER_VERIFICATION.md) (2026-10-24, build + fixture smoke PASS). Полный импорт реальных CSV и live AI в Docker **не** заявлялись как пройденные.

---

## БД и банковские PDF

| Часть | Где |
|-------|-----|
| Код (Flutter + API) | этот Git-репозиторий |
| Конкурсные данные (SQLite, PDF/OCR storage, demo-пароли) | отдельный пакет; не в Git |

Для полного демонстрационного сценария нужны подготовленная БД и связанный `storage/`. Получение — по согласованному приватному каналу команды (архив стенда). Тяжёлые сырые стенды OCR/CSV на десятки гигабайт для проверки жюри **не** требуются, если передан уже собранный sanitized-пакет.

Постоянные пути (нативный запуск — пути пакета; Docker volume — `/stand`):

| Переменная | Назначение |
|------------|------------|
| `DATABASE_URL` | SQLite стенда |
| `BANK_MATERIALS_STORAGE_ROOT` | корень PDF/OCR (`storage/`) |
| `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS` | allow-list OCR run id (из пакета) |
| `CASE_CONTEXT_SLOT_KEY` | слот case-снимка; для переданного стенда — `competition_default` |

Значения scope/slot **должны** совпадать с переданной БД (`stand_manifest.json` / `stand.env`). Не подставляйте чужие UUID и пути с другой машины.

---

## Клиенты и API

| Клиент | В этом репозитории? |
|--------|---------------------|
| Flutter Aspect | да (`lib/`, `android/`, `ios/`, …) |
| FastAPI backend | да (`backend/`) |
| React web (legacy Kontur) | нет |
| Пакет данных стенда | нет (поставка отдельно) |

- Документация API: [`backend/docs/MOBILE_API.md`](backend/docs/MOBILE_API.md), Swagger `/docs`, контракт [`backend/contracts/openapi.json`](backend/contracts/openapi.json).
- Авторизация: Bearer access token (login / refresh).
- PDF: `GET /api/v1/bank-materials/files/{id}/content` **с** `Authorization`; токен в URL не передаётся. Без заголовка — 401.

Подключение мобилки к стенду: [`docs/MOBILE_STAND_CONNECTION.md`](docs/MOBILE_STAND_CONNECTION.md).

---

## Проверка и ограничения

### Автоматические проверки (подтверждённые отчёты)

| Проверка | Результат | Источник |
|----------|-----------|----------|
| Выборка pytest (case/bank/ACL/mobile/alembic/assistant context), чистый env | **59 passed, 2 skipped** | [`docs/MOBILE_STAND_CONNECTION.md`](docs/MOBILE_STAND_CONNECTION.md) (2026-10-24) |
| `flutter test` | 1/1 passed | там же |
| `flutter analyze` (затронутые файлы) | без замечаний | там же |
| Hackathon provider (mocked HTTP) | pytest в `tests/test_hackathon_provider.py` | [`backend/docs/HACKATHON_PROVIDER.md`](backend/docs/HACKATHON_PROVIDER.md) |
| Live smoke шлюза организаторов | PASS 2026-10-21 (контракт ответа; не полный чат с bank citations) | там же |
| Docker competition: build + fixture smoke | PASS 2026-10-24 | [`backend/docs/COMPETITION_DOCKER_VERIFICATION.md`](backend/docs/COMPETITION_DOCKER_VERIFICATION.md) |
| Telegram Compose smoke (мок Bot API) | PASS 2026-10-24 | [`backend/docs/FINAL_COMPOSE_VERIFICATION.md`](backend/docs/FINAL_COMPOSE_VERIFICATION.md) |

Примеры команд:

```bash
cd backend
pytest tests/test_industry_news_personalization.py tests/test_holdout_personalization.py -q
pytest tests/test_mobile_user_endpoints.py tests/test_event_bank_evidence.py tests/test_bank_materials_api.py -q
python scripts/verify_competition_docker_static.py
```

```bash
flutter test
```

Успешный `GET /health` **не** означает, что весь продукт проверен.

### Браузерный / мобильный маршрут

Чеклист: [`docs/JURY_MOBILE_SCENARIO.md`](docs/JURY_MOBILE_SCENARIO.md).  
API-smoke против рабочей копии стенда (login A/B, ACL, case_context, bank-evidence, PDF+SHA) — в [`docs/MOBILE_STAND_CONNECTION.md`](docs/MOBILE_STAND_CONNECTION.md). End-to-end на физическом телефоне в той сессии **не** подтверждён.

### Live AI / Telegram / публичный deployment

| | Статус |
|--|--------|
| Live AI на полном assistant+bank пути стенда | не заявляется как пройденный в mobile-handoff |
| Live Telegram send / news на основном Compose | не заявляется; news по умолчанию выключены |
| Публичный HTTPS-деплой | **не проверен** в документации handoff |

### Существенные ограничения

- Демо-вход «Альфа-Бизнес» — макет, не SSO банка.
- Регистрация/почта в dev/test могут использовать упрощённое подтверждение — не считать это production-почтой банка.
- Без пакета данных bank/case API честно отвечает `not_configured` / пустыми состояниями.
- Вкладки сценариев / часть finance UI во Flutter могут показывать локальные заглушки при том, что API сценариев на backend существует.
- Модуль bootstrap конкурсного стенда из CSV в этом дереве отсутствует — не запускайте обещанный «bootstrap из сырых файлов» как обязательный шаг.
- PostgreSQL-путь Compose **не** проверен.
- DaData (ИНН) и сторонние сервисы не обещаются бесплатными; без ключа lookup = `not_configured`.

Мониторинг качества (операционный процесс): [`docs/QUALITY_MONITORING.md`](docs/QUALITY_MONITORING.md).

---

## Структура и зависимости

```text
aspect/
├── lib/                          # Flutter-клиент
├── android/ ios/ …               # платформенные оболочки
├── backend/                      # FastAPI, alembic, tests, docs API
│   ├── app/
│   ├── contracts/openapi.json
│   ├── docs/
│   ├── .env.example
│   └── requirements.lock
├── docs/                         # mobile / жюри
├── docker-compose.competition.yml
├── THIRD_PARTY_NOTICES
└── README.md
```

Сторонние компоненты: [`THIRD_PARTY_NOTICES`](THIRD_PARTY_NOTICES).  
Отдельного файла `LICENSE` в репозитории нет — лицензия проекту здесь не назначается.

---

## Перед проверкой жюри

1. Демо: https://alfa-aspect.ru/
2. Релиз: https://github.com/gadzhilaev/aspect/releases/tag/v1.0.0
3. Demo-пароли и (при необходимости) `HACKATHON_API_KEY` — отдельно, не в Git.
4. Сборка Flutter (TestFlight / APK) — если передаётся жюри отдельно.
