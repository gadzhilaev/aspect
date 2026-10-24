# Финальный приёмочный аудит «Аспекта» против ТЗ конкурса

Источник требований: `Альфа Хак_Новостная аналитика.pdf` (19 стр.; основные — стр. 6–14 и 18).
Дата аудита: 2026-10-24. Этап аудита: реализация и тесты не менялись, в репозитории изменён только этот документ.
Отчёты прогонов лежат в `data/competition_stand/handoff_reports/` (каталог в git не попадает).

---

## 0. Вердикты

| Вопрос | Вердикт | Почему |
|---|---|---|
| Готов ли backend к интеграции мобильного клиента | **Условно готов — для локальной/стендовой интеграции** | OpenAPI совпадает с приложением (59 операций, расхождений 0); auth/refresh, ACL, коды ошибок, null-поля и Bearer для PDF покрыты тестами; полный backend-suite рабочего дерева зелёный. Но код, на который ориентируется handoff, **не опубликован** (дефект D1), а реальный мобильный клиент не проверялся. |
| Готов ли к публичному хостингу | **Не готов** | Compose-API фактически работает в `APP_ENV=test` с фиксированным кодом подтверждения `123456`, который ещё и возвращается в ответе (D2, D3). Telegram-webhook принимает публично известный секрет и доступен через web-proxy (D4). Публичный HTTPS-деплой не выполнялся. |
| Соответствие ТЗ конкурса | **Частичное; общий PASS не ставится** | Ключевые цепочки (новость → релевантность → Impact → интерпретация с аналитикой банка → финансы → решение → Telegram) работают на коде, unit/integration-тестах и in-process E2E. Но: опубликованный коммит не проходит собственные тесты (D1); нет точки входа с главного экрана Альфа-Бизнеса (K08); нет метрик качества и процесса мониторинга с обратной связью (K12); качество live-агента в этом аудите не перепроверялось; Telegram news-путь в основной Compose не работает (D5). |

Процент готовности сознательно не указывается.

---

## 1. Зафиксированное состояние

| Слой | Состояние |
|---|---|
| Git HEAD | `5f768eaaafa960c81f7de788898925c4215e7ff0` (`main`, 2026-10-24 13:22 +0300, «Save competition MVP progress…») |
| Публикация | `main...origin/main` без расхождений: HEAD уже есть на `https://github.com/Sidikov213/kontur_back.git`. **Тега на HEAD нет.** Доступ `alfa-hack-2026` не проверялся. |
| Рабочее дерево | Не закоммичено 108 путей: 61 изменённый tracked-файл (+1924/−634) и 47 untracked. Среди untracked — `alembic/versions/009_*`, `010_*`, `app/services/telegram_news_policy.py`, `app/workers/news_scheduler.py`, `app/services/ingestion/scheduler_*.py`, `docker/competition/entrypoint-telegram-*.sh`, тесты `test_telegram_news_policy.py`, `test_news_scheduler.py`, `test_news_classification_heuristic.py`, `tests/_alembic_util.py`. **Рабочее дерево — не релиз.** |
| Миграции | Рабочее дерево: head `010`. Опубликованный HEAD: последняя миграция `008`. |
| Окружение | Python 3.12.10, Node v24.19.0, Docker 29.9.2 |
| Код | Аудит проверял рабочее дерево; опубликованный HEAD прогнан отдельно (см. §2) |
| Локальный runtime | Основной стенд (`real_news_613`, его polling/worker/scheduler) не трогался |
| Docker | Образ `kontur-competition-api:local` собран 2026-10-24 15:57; после сборки менялись только два smoke-скрипта, код `app/` в образе актуален. Проверки шли на отдельном project/volume `kontur_audit_fca` с фиктивными секретами; после проверки volume удалён. |
| Внешний сервер | Не разворачивался — NOT_VERIFIED |
| Мобильный клиент | В репозитории нет; Flutter не запускался — NOT_VERIFIED |

---

## 2. Свежие результаты проверок (этот аудит)

| Проверка | Объект | Результат | Отчёт |
|---|---|---|---|
| Полный backend pytest (`-ra`, чистое env, mock-провайдер) | рабочее дерево | **698 passed, 4 skipped, 0 failed** (231 с). Все 4 skip — PostgreSQL (`ALEMBIC_POSTGRES_URL` не задан). | `pytest_final_acceptance.txt` |
| Полный backend pytest | **опубликованный HEAD 5f768ea** (`git archive` во временный каталог) | **16 failed, 636 passed, 5 skipped**. Падают alembic/bank/case schema, `test_assistant_manual_context_fix` (×5), `test_manual_profile_feed`, `test_hackathon_provider`, `test_assessment_trust`, `test_frontend_routes_contract` (FK `company_edges`, коды ошибок). Пятый skip: `test_competition_stand_bootstrap` — в чистой копии нет локального OCR-корпуса. | `pytest_published_head_5f768ea.txt` |
| Frontend-тесты (9 наборов `npm run test:*`) | рабочее дерево | **89 pass, 0 fail** | `fe_final_acceptance.txt` |
| `npm run build` | рабочее дерево | exit 0; есть предупреждение о chunk > 500 kB | там же |
| `npm run lint` (oxlint) | рабочее дерево | exit 0, 3 предупреждения (set-state-in-effect, immutability, exhaustive-deps) | там же |
| Сверка OpenAPI | `contracts/openapi.json` и `create_app().openapi()` | 59 и 59 операций; путей, схем и изменённых схем, отличающихся между ними, — 0 | — |
| Docker: основная `docker-compose.competition.yml`, `config` | разрешённое env по сервисам | см. §5, таблица | — |
| Docker: API из основной compose, runtime | изолированный volume, `stand.env` в формате bootstrap | воспроизведены D2, D4, D6 | — |
| Docker: restart API | тот же volume | users/companies/link_tokens/alembic не изменились (1/1/1/`010`); в логе `no import on restart` | — |
| Docker: guard'ы Telegram | `telegram_polling` с `INGRESS_MODE=webhook` | exit 3, отказ | — |
|  | `telegram_worker` с пустым токеном | exit 2, отказ | — |
| Telegram news-путь E2E (in-process, временная SQLite, mocked Bot API) | рабочее дерево | пройден; воспроизведены D5, D7 | §10 |

Чего в этом аудите не запускали (из-за ограничений): live LLM, реальные отправки в Telegram, регистрацию webhook, реальные RSS/CBR/GDELT, PostgreSQL, браузер/скриншоты.

---

## 3. Подтверждённые дефекты

Приоритеты: **P0** блокирует сдачу; **P1** блокирует публичный хостинг или ломает заявленную функцию в основной конфигурации; **P2** даёт неверное поведение при типичной настройке; **P3** — латентный риск.

### D1 — P0. Опубликованный коммит не соответствует проверяемому состоянию и не проходит собственные тесты
- **Где:** весь репозиторий; `origin/main` = `5f768ea`, тега нет.
- **Воспроизведение:** `git archive HEAD` → распаковать во временный каталог → `python -m pytest tests -ra` → 16 failed. В HEAD нет миграций 009/010, политики Telegram-новостей, news_scheduler и telegram-entrypoint'ов, на которые ссылаются docs/handoff и compose рабочего дерева.
- **Последствие:** жюри по ссылке на коммит получит версию, которая не совпадает с README/handoff и не проходит свои тесты. Все PASS ниже относятся к рабочему дереву, а не к опубликованной версии.

### D2 — P1. Compose-API подменяет `APP_ENV` и `SECRET_KEY` значениями из `stand.env`; в «production» работает тестовый режим
- **Где:** `docker/competition/entrypoint-api.sh` (цикл экспорта, стр. 30–42, исключения только для `DATABASE_URL|BANK_MATERIALS_STORAGE_ROOT|HACKATHON_API_KEY|OPENAI_API_KEY|GIGACHAT_AUTH_KEY`); `app/services/competition_stand/bootstrap.py:464-465` пишет `APP_ENV=test` и свой `SECRET_KEY`.
- **Воспроизведение:** изолированный project с `COMPETITION_SECRET_KEY=audit-fake-runtime-secret`, `stand.env` в формате bootstrap, `up -d api`. Окружение PID 1: `APP_ENV=test`, `secret_key == COMPETITION_SECRET_KEY` → `false`. `/health` → `env: "test"`. `POST /auth/register` → `details.demo_code == "123456"`; `verify-email` с `123456` → 200.
- **Последствие:** подтверждение email в Docker-стенде фактически отключено (код фиксированный и приходит в ответе); заданный оператором секрет подписи JWT игнорируется.

### D3 — P1. `debug=True` по умолчанию: код подтверждения возвращается в ответе и в `APP_ENV=production`
- **Где:** `app/core/config.py:18` (`debug: bool = True`); `app/api/v1/auth.py:43,56` (`"demo_code": code if settings.debug`). Compose нигде не задаёт `DEBUG=false`.
- **Доказательство:** только чтение кода. Runtime-проба на временной БД не запускалась — её остановило автоматическое ревью инструментов.
- **Последствие:** даже после исправления D2 случайный production-код подтверждения уйдёт клиенту в ответе на регистрацию.

### D4 — P1. Telegram-webhook в API принимает публично известный секрет и доступен через web-proxy
- **Где:** `app/core/config.py:42` (`telegram_webhook_secret = "kontur-webhook-secret"`, значение лежит в репозитории); `docker-compose.competition.yml`: сервис `api` не получает `TELEGRAM_WEBHOOK_SECRET`; `app/api/v1/telegram.py` подключён всегда, в том числе в polling-режиме; `docker/competition/nginx.conf:22` проксирует `/api/`.
- **Воспроизведение (основная compose, `TELEGRAM_WEBHOOK_SECRET=audit-fake-webhook` у оператора):** `POST /api/v1/telegram/webhook` с заголовком `kontur-webhook-secret` → **200**, с секретом оператора → **403**.
- **Последствие:** любой, кто достучится до web/API, может подделывать update'ы Bot API (`/unlink`, `/mute` для известного chat_id; `/start <token>` с перехваченным токеном) мимо polling-процесса.

### D5 — P1. В основной compose автоматические Telegram-уведомления о новостях не ставятся в очередь
- **Где:** `docker-compose.competition.yml`: `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED` есть только у `telegram_worker` и `telegram_polling`. Enqueue же выполняется в `api` (`POST /events/{id}/recompute-impact`, `PATCH /companies/{id}/finance`) и в `news_scheduler` (`pipeline.process_pending → recompute_event_for_ready_companies → enqueue_impact_notifications`, `app/services/impact.py:692,790`). `news_scheduler` идёт в обход `entrypoint-api.sh` и `stand.env` не читает; bootstrap-`stand.env` флаг тоже не содержит.
- **Воспроизведение:** `docker compose … --profile telegram config` при `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED=true` → у `api` и `news_scheduler` переменная `<unset>`. In-process E2E: тот же ingest при выключенном флаге в процессе enqueue → опубликовано 1 событие, news-outbox **0**.
- **Последствие:** заявленный путь «новая новость → Telegram» в основной конфигурации не работает. Telegram compose smoke этого не поймал: он запускал отдельный compose, монтировал исходники поверх образа и проверял заранее созданный outbox `kind="test"`.

### D6 — P2. Deep link для pairing ведёт на чужого/выдуманного бота
- **Где:** `app/core/config.py:41` (`telegram_bot_username = "KonturDemoBot"`); `api` в compose не получает `TELEGRAM_BOT_USERNAME`; `app/services/notifications.py:99-100`.
- **Воспроизведение:** основная compose, `TELEGRAM_BOT_USERNAME=AuditFakeBot` у оператора → `POST /telegram/link-token` → `https://t.me/KonturDemoBot?start=…`.

### D7 — P2. Без `PUBLIC_WEB_BASE_URL` кнопка в Telegram ведёт на сторонний домен `kontur.app`
- **Где:** `app/services/notifications.py:48-80`: при пустом `PUBLIC_WEB_BASE_URL` берётся `deep_link_base` (по умолчанию `https://kontur.app/e`, `config.py:57`). Payload собирается при enqueue, то есть в `api`/`news_scheduler`, которым compose `PUBLIC_WEB_BASE_URL` не передаёт.
- **Воспроизведение:** in-process E2E без `PUBLIC_WEB_BASE_URL` → `https://kontur.app/e/evt_live_…`. Если задать переменную: `https://aspect.example.com/news/evt_live_…`.

### D8 — P3. Известные fallback-секреты подписи без защиты в production
- **Где:** `docker-compose.competition.yml` (`${COMPETITION_SECRET_KEY:-competition-docker-local-secret}` у всех сервисов); `entrypoint-api.sh:53`; `config.py:23` (`kontur-hackathon-dev-secret-change-me`). Отказа стартовать с известным секретом при `APP_ENV=production` нет.
- **Сейчас:** в стандартном bootstrap API подписывает JWT случайным секретом из `stand.env` (см. D2), так что дефект латентный. Он станет реальным после исправления D2, если `COMPETITION_SECRET_KEY` не задан.

---

## 4. Матрица соответствия ТЗ

Типы доказательств: **C** — чтение кода; **U** — unit; **I** — integration (TestClient/временная БД); **E** — in-process E2E этого аудита; **D** — Docker этого аудита; **L** — реальный внешний вызов (в этом аудите не делались); **M** — ручная проверка UI (не делалась).
Статусы старых отчётов без перепроверки сюда не переносились.

| Стр. | Требование | Реализация | Доказательство | Статус | Ограничение |
|---|---|---|---|---|---|
| 6 | Анализ данных компании: отрасль, положение, доля рынка, деятельность, масштаб | Импорт case-CSV, `GET /companies/{id}/context`, ручной цифровой двойник (узлы и связи) | C, I (`test_case_context_api`, `test_company_context`) | PARTIAL | Доля рынка и положение не рассчитываются; единицы выручки неизвестны и сознательно не трактуются |
| 6 | Персонализированный отбор и ранжирование | Relevance gate + `EventImpact` (вес severity/exposure/dependency/proximity) + `case_profile_match` | U/I (`test_personalization_ingestion`, `test_case_personalized_feed`, `test_personalization_proof`), E (Impact для СеверПром 61.7, `company_calculated`) | PARTIAL | Расчётный Impact требует ручного двойника; из CSV в ранжирование идут только отметки LOA/DEP × ключевая ставка (§6) |
| 6 | Персонализированная интерпретация с аналитикой Альфа | Bank evidence/fragments, `NewsBankAnalytics`, валидация цитат | U/I (`test_assistant_bank_evidence`, `test_bank_fragment_retrieval`, `test_event_bank_evidence`), FE-тесты | PARTIAL | Live-ответы модели в этом аудите не проверялись; проверка цитат структурная, не смысловая |
| 6 | UX в интернет-банке Альфа-Бизнес | Отдельный web-прототип (React) в стилистике Альфа | C, FE build | PARTIAL | Встраивания и мокапа главного экрана Альфа-Бизнеса нет (см. K08) |
| 6 | Парсер внешних новостей и материалов Альфа, классификация, ключевая информация | RSS/CBR/GDELT-провайдеры, кластеризация, `heuristic_v2`; OCR-конвейер для 9 материалов | U (`test_news_classification_heuristic`, `test_ingestion`), E (ingest → publish) | PARTIAL | Реальные источники в аудите не запускались; качество классификации на потоке не измерено |
| 7 | Агент: планирование, инструменты, контекст, самопроверка, адаптация | `hackathon_loop`: tool → observation → следующий запрос модели, repair, budget, trace | U/I (`test_assistant_agent_hackathon_loop` 16, `test_assistant_agent_api_integration` 19) | PARTIAL | Все проверки на сценарных/mocked ответах модели; live-качество — NOT_VERIFIED |
| 8 | GitHub: хеш коммита/тег, приватный доступ `alfa-hack-2026` | `origin/main` = 5f768ea | git | **FAIL** | D1: опубликованная версия не та и не зелёная; тега нет; доступ не проверен |
| 8 | README: назначение, архитектура, env, запуск, переменные, компоненты, пошаговый сценарий | `README.md` (разделы: жюри, быстрый старт, демо-маршрут, ассистент, ingestion, Docker, мобильный клиент, структура) | C | PARTIAL | Описывает состояние рабочего дерева, а не опубликованного коммита |
| 8 | Docker: единый воспроизводимый запуск | `docker-compose.competition.yml` (bootstrap → api/web/news_scheduler; профиль telegram) | D | PARTIAL | D2, D4, D5, D6, D7; bootstrap требует внешних материалов жюри |
| 8 | Lock-файлы | `requirements.lock`, `requirements-linux.lock`, `requirements-dev.lock`, `web/package-lock.json` | C | PASS | Установка с `--require-hashes` в аудите не повторялась |
| 8 | THIRD_PARTY_NOTICES | Файл есть (152 строки) | C | PARTIAL | Полнота по всем зависимостям lock-файлов не сверялась |
| 8 | Синтетические данные и тестовые аккаунты | `scripts/seed_demo.py` (demo@kontur.app), синтетические фикстуры тестов | I | PASS | — |
| 8 | Архитектура / API / OpenAPI / модель данных (опционально) | `contracts/openapi.json`, `docs/MOBILE_API.md` | C (сверка: расхождений 0) | PASS | Только для рабочего дерева |
| 8 | Внешний бесплатный сервер (рекомендация) | — | — | NOT_VERIFIED | Деплой не выполнялся; перед ним нужны D2–D4 |
| 8 | Демо: лента меняется под клиента, интерактивный прототип | Разные Impact для разных компаний | I (`test_personalization_proof`) | PARTIAL | Ручной прогон UI не делался |
| 9 | K01 Контекст и отбор | см. стр. 6 | U/I/E | PARTIAL | — |
| 9 | K02 Аналитика Альфа и явное разделение «банк / ИИ» | `text_kind`, `source_role`, метки в UI | U/I, FE-тесты | PARTIAL | Визуально не проверено |
| 9 | K03 Корректный отбор, склейка, резюме со ссылками, минимум фактических ошибок | Кластер из ≥2 источников, `strip_invented_numbers`, URL источников | U/I/E | PARTIAL | Доля фактических ошибок не измерялась |
| 9 | K04 Устойчивость на незнакомых новостях, без сценария | Детерминированная эвристика; E2E на новых статьях | E | PARTIAL | Только 5 синтетических заголовков; на реальном потоке не проверено |
| 9 | K05 Полный сценарий вход → интерпретация → следующее действие | API-цепочка | I (`test_acceptance`, `test_finance_rate_fx_e2e`, `test_user_triggered_finance_scenarios`) | PARTIAL | UI — M не делалась |
| 10 | K06 Многофакторная интерпретация | Веса Impact, пути влияния, finance state | U/I | PASS (C/U/I) | Зависит от полноты двойника |
| 10 | K07 Масштабируемость и сопровождение | SQLite + один volume, один scheduler с lock, документы | C | PARTIAL | Горизонтальное масштабирование не описано и не проверено; PostgreSQL-пути пропущены |
| 10 | K08 Заметная постоянная точка входа на главном экране Альфа-Бизнеса | — | C (`COMPETITION_REQUIREMENTS_STATUS.md` K08) | **FAIL** | Документированный разрыв |
| 10 | K09 Интерактивные вопросы, другой срез, переход к источнику | Ассистент по событию, ссылки на фрагменты и PDF | I | PARTIAL | Live не проверялось |
| 10 | K10 Агентная логика с коррекцией при неполных/противоречивых данных | repair/retry/stop, неизвестные и конфликтующие поля | U/I (mocked) | PARTIAL | См. стр. 7 |
| 10 | K11 Прослеживаемость: источники, признаки компании, промежуточные шаги | persisted trace, tool runs, provenance | U/I (`test_assistant_provenance`, `test_assistant_agent_runtime`) | PASS (mocked) | Трасса live-хода не перепроверялась |
| 10 | K12 Метрики качества и регулярный мониторинг с обратной связью пользователей/экспертов | — | C (механизмов feedback/metrics в `app/` и `web/src` нет) | **FAIL** | Количество unit-тестов — не метрика качества по ТЗ |
| 11 | Не просто лента/пересказ | Impact + интерпретация + финансы + решения | I | PASS (I) | — |
| 11 | Пример «ключевая ставка» | `key_rate` → market, severity 60; rate scenarios hold/hike/unknown | U (`test_finance_setup_rate_fx`, heuristic) | PASS (U) | — |
| 11 | Аналитика Альфа — видимая часть ценности | Блок «Аналитика Альфа-Банка» | FE-тесты | PARTIAL | Визуально не проверено |
| 12 | Безопасность ИИ: разделение доступа, защита чувствительных данных, логирование инструментов, ограничение небезопасных действий | ACL `require_company_member`, ключи только на сервере, tool-trace, бюджет хода, подтверждение решений только пользователем | I (ACL-тесты TG2, assistant, decisions) | PARTIAL | D2–D4 нарушают защиту аутентификации и ingress |
| 12 | Только разрешённые LLM, лимит 500 ₽/сутки | `COMPETITION_MODE` validator: allow-list моделей, точный base URL; стоп по `PROVIDER_BUDGET_EXCEEDED` | U (`test_competition_profile`, `test_hackathon_provider`) | PARTIAL | Собственного учёта суточных расходов нет: остановка только по ответу шлюза |
| 12 | Устойчивость к неполным, неоднозначным, шумным данным | `severity=null`, `unknown`/`conflict`, profile-only, без поддельных нулей | U/I/E (расследование без меры → neutral, не в Telegram) | PASS (U/I/E) | — |
| 13 | JSON-обмен, где разделены факты, источники, признаки клиента, релевантность, риски/возможности, подтверждённое / аналитика Альфа / выводы модели | `ImpactOut.claims`, `score_kind`, `text_kind`/`source_role` у цитат, OpenAPI | C, I | PASS (C/I) | — |
| 14 | 6 вопросов интерпретации | Разделы карточки события и ответы ассистента | C, FE-тесты | PARTIAL | Полноту ответов live-модели не проверяли |
| 15–16 | Поля CSV (`df_Uid…`, `df_Fid_Uid…`, payments) | Импорт, validate, dry-run, связывание org/company | U/I | PARTIAL | Используются узко (§6) |
| 17 | 9 материалов Альфа | OCR/QA-конвейер, allow-list OCR run | I | PARTIAL | Материалов нет в репозитории; bootstrap-тест в чистой копии пропускается |
| 18 | Только разрешённые модели; внешние ИИ-сервисы не основа решения | Validator запрещает OpenAI/GigaChat/mock в `COMPETITION_MODE` | U | PASS (U) | Код OpenAI/GigaChat-провайдеров в репозитории остаётся (вне режима конкурса) |

---

## 5. Границы Docker-конфигурации

Разрешённое окружение (`docker compose -f docker-compose.competition.yml --profile telegram config`, фиктивные значения оператора):

| Переменная | api | news_scheduler | telegram_worker | telegram_polling |
|---|---|---|---|---|
| `DATABASE_URL` | из entrypoint: `sqlite:////stand/stand.db` | `sqlite:////stand/stand.db` | то же | то же |
| `APP_ENV` | не задан → **`test` из `stand.env`** | `production` | `production` | `production` |
| `SECRET_KEY` | задан, но **перетирается `stand.env`** | fallback-секрет | fallback-секрет | fallback-секрет |
| `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED` | **нет** | **нет** | есть | есть |
| `TELEGRAM_BOT_USERNAME` | **нет** | нет | есть | есть |
| `TELEGRAM_WEBHOOK_SECRET` | **нет → публичный default** | нет | нет | есть |
| `PUBLIC_WEB_BASE_URL` | **нет** | **нет** | есть | есть |

| Проверка | Результат |
|---|---|
| Один и тот же DB/volume у всех процессов | PASS (D) |
| Флаг auto-news доходит до процессов enqueue | **FAIL** — D5 |
| Правильный `TELEGRAM_BOT_USERNAME` у API | **FAIL** — D6 |
| `PUBLIC_WEB_BASE_URL` и webhook-настройки в нужных процессах | **FAIL** — D4, D7 |
| `entrypoint-api.sh` не перетирает runtime `SECRET_KEY`/`APP_ENV` | **FAIL** — D2 |
| Production не уходит молча в test-режим и не работает на известном секрете | **FAIL** — D2, D3, D8 |
| Polling и webhook взаимоисключающие | PARTIAL: `telegram_polling` отказывается при `INGRESS_MODE=webhook` (exit 3, D) и проверяет `getWebhookInfo` (U); при этом HTTP-webhook в API всегда включён (D4) |
| Пустой токен → worker не стартует | PASS (exit 2, D) |
| Restart сохраняет БД | PASS для БД (D). PDF/outbox/состояние scheduler лежат в том же volume — рестарт с ними в этом аудите не прогонялся (NOT_VERIFIED) |
| Smoke-compose ≠ проверка основной конфигурации | Подтверждено: `docker-compose.telegram_compose_smoke.yml` — один контейнер, исходники смонтированы поверх образа, outbox `kind=test`. Его PASS к основной compose не относится. |

---

## 6. Данные и персонализация

| Пункт | Вывод | Доказательство |
|---|---|---|
| Case snapshot, связь компании, membership, конфликты/unknown | Реализовано; статусы `known/unknown/conflict` по полям | U/I (`test_case_snapshot_activation`, `test_case_context_api`) |
| Ручной профиль без case-link доступен агенту | Да (manual company context) | I (`test_assistant_manual_context_fix` — зелёный в рабочем дереве, **падает в HEAD**) |
| Новая регистрация не получает чужую/демо-компанию | Подтверждено в Docker: после регистрации `companies=0`, после создания своей — 1 | D |
| Одна новость → обоснованно разные оценки для разных компаний | Да | I (`test_personalization_proof`) |
| Переименование компании не меняет смысл | Сопоставление идёт по id/узлам, не по имени | C, U (`test_unconfirmed_node_names`, `test_impact_skips_unconfirmed_names`) |
| Платёж ≠ поставка; страна ФТС ≠ направление торговли | Явные ограничения в контексте агента (`case_company_context.py:26-33`) | C |
| Какие признаки CSV реально используются | В **ранжировании** — только отметки продуктов `LOA`/`DEP` × тема ключевой ставки (`case_profile_relevance.py`, 2 правила). ОКВЭД, ФТС, выручка, платежи показываются в контексте и передаются агенту, в отбор не идут. | C |
| Нет утверждений о единицах выручки и сегменте > 15 млрд | `revenue_units_unknown: не трактовать как рубли; не применять порог 15 млрд` | C |
| profile-only, null, известный ноль, пагинация | `score_kind=case_profile_match` без денег; `severity=null` допустим | U/I |
| GET не создаёт Impact/Scenario/Decision | `GET /events/{id}/impact` только читает (404 при отсутствии); TG-политика без побочных эффектов | C, U (`test_no_scenario_decision_side_effects`) |
| Ограничение | `PATCH /companies/{id}/finance` пересчитывает **существующие** macro/FX Impact и может поставить их в Telegram-очередь. Это задокументировано в коде, но это неявный пересчёт. | C |

---

## 7. Новости и планировщик

| Пункт | Вывод | Доказательство |
|---|---|---|
| Источник → raw → классификация → публикация → релевантность → лента | Пройдено целиком | E (ingest → `evt_live_*` → Impact) |
| Официальный источник ≠ риск ≠ полезная новость | `official_source_does_not_imply_risk` | U |
| Выставка/культура → neutral; запрет экспорта → risk 75; расследование без меры → neutral/null; ключевая ставка → market 60; неизвестная значимость → null | Правила `heuristic_v2` | U (`test_news_classification_heuristic`); E (расследование → 0 в outbox) |
| Swap/RUONIA | Отдельного правила нет; попадают в key_rate/fx, только если в тексте есть «ставк» + «ключев»/«ЦБ» | C — PARTIAL |
| Даты, первичный источник, редиректы, дедупликация, повторный запуск | Дедуп по raw | E (повтор тех же статей: inserted 0, duplicates 2, published 0) |
| 1200 с, нет параллельного запуска, 429/partial, restart без catch-up | Интервал по умолчанию 1200 (минимум 30); межпроцессный file lock; после тика фиксированная пауза («no catch-up burst») | C, U (`test_news_scheduler`) |
| Эвристика без LLM | `prefer_live_enrich=False` в scheduler | C, E |
| Устаревший Impact после изменения события | Повторная проверка политики перед отправкой | U (`test_event_reclassified_after_enqueue_skips`) |

---

## 8. Аналитика банка и агент

| Пункт | Вывод | Доказательство |
|---|---|---|
| Актуальная ревизия, eligibility, даты, исторические материалы | `revision_mismatch` отклоняется; allow-list OCR run | C, U |
| Точная цитата ≠ пересказ | `exact_quote_not_allowed_for_summary`, `exact_quote_text_mismatch` | C, U |
| Проверенные фрагменты ≠ все страницы 9 PDF | Агенту передаются только фрагменты из allow-list | C |
| Факт / интерпретация банка / прогноз / вывод ИИ | `text_kind`, `source_role` | C, U |
| Цитата доступна в текущем ходе; история не расширяет scope | `unknown_or_not_passed_fragment_id` | C, U |
| PDF: auth + path + SHA | Bearer, storage root confinement | I (FE `bank-materials`, backend bank tests) |
| tool → observation → следующий запрос модели | Да | U/I (mocked) |
| Нет смешения контекста разных пользователей | ACL на беседы | I |
| Лимиты, stop, repair, retry, идемпотентность | Budget (4 HTTP, 3 tool, 1 repair, 90 с), `client_message_id` | U/I |
| Восстановимость сохранённой трассы | Да | I |
| Не требуется скрытое рассуждение модели | Трасса — шаги и инструменты, без chain-of-thought | C |
| Prompt-injection в новостях/OCR | Экранирование/маркировка недоверенного текста (`safety.py`, протокол цикла) | C, U — устойчивость live-модели NOT_VERIFIED |
| Структурная проверка цитат ≠ смысловое обоснование | Прямо оговорено в `validate_bank_evidence_citations` | C |
| Неполнота/противоречие/нерелевантность → адаптация или честный PARTIAL | Состояния unknown/conflict, профиль без Impact | U/I |
| Scripted/mocked ≠ live-качество | **Live-качество в этом аудите не проверялось** | — |

---

## 9. Финансы и решения

| Пункт | Вывод | Доказательство |
|---|---|---|
| Ставка: сохранение / повышение / неизвестно / конфликт; наблюдаемое vs предположение | Реализовано | U/I (`test_finance_setup_rate_fx`, `test_finance_rate_fx_e2e`) |
| FX: платёж/поступление, валюты, направление котировки, смена пары, нет курса | `validate_optional_finance_fx`, `fx_exposure_direction` | U/I |
| Деньги не выводятся из severity; нет поддельных нулей; нет автоматического RUB | Тесты на отсутствие денежного эффекта у profile-only | U/I |
| PATCH finance → явный recompute → сравнение → черновик → подтверждение → GET | Цепочка есть; оговорка о неявном пересчёте macro/FX — см. §6 | I (`test_user_triggered_finance_scenarios`, `test_decisions`), FE `finance-recompute-cta` |
| Повтор what-if, сетевой retry, двойное подтверждение | Уникальность decision/scenario (миграции 003/005) | I |
| Исторические решения не переписываются | Да | I |
| Нет FX-плана без данных | `finance_data_required` + CTA настройки | I, FE |

---

## 10. Telegram без реальной отправки

In-process E2E на временной SQLite: эвристика без LLM, Bot API подменён через `httpx.MockTransport`, фиктивный токен. Путь проходил через **новость**, а не через заранее созданный test-outbox.

| Шаг | Результат |
|---|---|
| `POST /telegram/link-token` | deep link на бота из env (`AuditFakeBot`) |
| `/start <token>` в группе | отказ («только в личном чате») |
| `/start <token>` в private | «Готово»; подписка `connected`, `risks_enabled=true`, `min_severity=medium`, watermark выставлен |
| Повтор того же токена | отказ |
| Seed-события до подключения | 0 в очереди (watermark, нет backfill) |
| Новая статья «расследование без меры» | опубликована как neutral → 0 в очереди |
| Новая статья «export ban on semiconductor components» | published 1 → Impact `action_required`, `company_calculated`, 61.7 → outbox `news` `pending` |
| Worker | `sent`; `sendMessage` на chat 990001; в тексте нет токена; кнопка `https://aspect.example.com/news/<id>` |
| Повтор тех же статей | duplicates 2, новых outbox нет |
| 429 / timeout / 403 на news-строке | `retry` (`telegram_429`) / `uncertain` (`timeout_uncertain`) / `blocked` + подписка `blocked` |
| Потеря membership после enqueue | `skipped: pre_send_denied:membership_missing` |
| Флаг выключен в процессе enqueue | 0 в очереди — **D5** |
| `PUBLIC_WEB_BASE_URL` не задан | кнопка на `https://kontur.app/e/<id>` — **D7** |

Остальные пункты покрыты unit/integration-тестами (в этом прогоне зелёные): demo без controlled pair, профильные/нейтральные/null-сигналы, порог, quiet hours (отложить, а не выбросить), pause/mute, отключение и повторное включение без backfill, rollback, идемпотентность (`test_telegram_news_policy`, `test_telegram_tg2`, `test_telegram_polling`, `test_telegram_worker_kinds`).

**Политика v1 узкая, и это нужно говорить прямо:** только личный чат; только `event_type=risk` с известной severity; активный Impact с `score_kind=company_calculated` выше порога; только события после подключения (watermark); группы, возможности, profile-only и macro без расчёта не отправляются. При timeout статус `uncertain` и повторная попытка, поэтому доставка at-least-once и дубль сообщения возможен.

---

## 11. Продуктовый сценарий и мобильный handoff

| Пункт | Статус |
|---|---|
| Вход из демо-UI Альфа-Бизнеса | FAIL / документированный разрыв (K08): web-прототип отдельный |
| Компания → лента → новость → материал банка → обсуждение → финансы → решение | API: PASS (I). UI: NOT_VERIFIED (M) |
| CTA и заглушки | FE-тесты: `finance-recompute-cta`, `event-discoverability` — PASS (U). Визуально NOT_VERIFIED |
| OpenAPI и фактические ответы | Схема совпадает с приложением; ответы проверены тестами (I) |
| auth/refresh, ACL/IDOR, null, enum, ошибки, пагинация, идемпотентность, PDF Bearer, Telegram | I — PASS в рабочем дереве; D2/D3 влияют на регистрацию в Docker |
| Flutter, темы, клавиатура, мобильная вёрстка, поведение браузера | **NOT_VERIFIED** |

**Короткий ручной чек-лист (визуальные пункты, на реальном устройстве/браузере):**
1. Светлая и тёмная тема: «Аналитика Альфа-Банка», карточка новости, ассистент читаемы.
2. Мобильная ширина 360–414 px: лента, карточка, ассистент, финансы без горизонтального скролла.
3. Экранная клавиатура не перекрывает поле ввода ассистента.
4. PDF фрагмента открывается с Bearer и на нужной странице.
5. Кнопка из Telegram открывает правильную новость на публичном HTTPS-домене.
6. После повторного входа (refresh) сценарий продолжается без потери беседы.

---

## 12. Готовность к сдаче

| Пункт | Статус |
|---|---|
| README, runbook (`COMPETITION_JURY_RUNBOOK.md`), lock-файлы, THIRD_PARTY_NOTICES, синтетические фикстуры | Есть в рабочем дереве; часть документов не закоммичена (D1) |
| Исходные материалы жюри (CSV, 9 PDF, OCR, QA) | Не в репозитории; bootstrap требует `COMPETITION_INPUTS_DIR` |
| Идентификатор версии (хеш/тег) | FAIL — D1, тега нет |
| Доступ GitHub `alfa-hack-2026` | NOT_VERIFIED |
| Воспроизводимость в чистом временном окружении | HEAD: 16 failed. Рабочее дерево: зелёное, но не опубликовано |
| Что требует внешних ресурсов | публичный HTTPS (Telegram-кнопки, webhook, мобильный клиент); реальный мобильный клиент; разрешённый live-прогон LLM (качество агента); реальные источники новостей |
| Метрики качества и процесс мониторинга по ТЗ (K12) | FAIL: нет сбора оценок пользователей/экспертов, нет метрик точности отбора и интерпретации, нет регулярного процесса |

---

## 13. Не проверено и осознанные ограничения

Не проверено в этом аудите:
- live LLM (качество, prompt-injection на реальной модели, расход бюджета);
- реальные Telegram-send, регистрация webhook, `getWebhookInfo` на настоящем боте;
- реальные RSS/CBR/GDELT и поведение при 429 от источников;
- PostgreSQL (4 skip);
- публичный деплой/HTTPS, доступ `alfa-hack-2026`;
- Flutter/мобильный клиент, темы, клавиатура, вёрстка, браузер;
- restart с PDF/outbox/состоянием scheduler в основной compose (проверена только БД);
- runtime-проба D3 (есть только чтение кода);
- полнота THIRD_PARTY_NOTICES.

Осознанные ограничения продукта:
- узкая политика Telegram v1 (§10); доставка at-least-once;
- из CSV в ранжирование идут только продуктовые отметки LOA/DEP;
- расчётный Impact требует ручного двойника;
- проверка цитат структурная, не смысловая;
- суточный лимит 500 ₽ отслеживается только по ответу шлюза;
- SQLite на одном volume, один экземпляр scheduler.

---

## 14. Минимальный порядок исправлений перед сдачей

1. **D1:** закоммитить и опубликовать проверенное состояние, поставить тег; на опубликованном теге из чистой копии повторить полный pytest, frontend-тесты и build; проверить доступ `alfa-hack-2026`.
2. **D2:** в `entrypoint-api.sh` не экспортировать из `stand.env` ключи `APP_ENV` и `SECRET_KEY` (runtime-значения приоритетнее), либо bootstrap не должен их писать.
3. **D3 + D8:** `DEBUG=false` в compose; не возвращать код подтверждения, когда debug выключен; отказ старта в production с известным секретом.
4. **D4:** передать `TELEGRAM_WEBHOOK_SECRET` в `api`, убрать публичный default; в polling-режиме отключить HTTP-webhook или требовать явный секрет.
5. **D5 + D6 + D7:** передать `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED`, `TELEGRAM_BOT_USERNAME`, `PUBLIC_WEB_BASE_URL` в `api` и `news_scheduler`; не подставлять `kontur.app` как fallback.
6. Повторить Telegram news-путь на **основной** compose (изолированный volume, mocked Bot API), а не на smoke-compose.
7. K12: описать и включить минимальный процесс метрик и обратной связи (например, оценка полезности карточки и журнал экспертной проверки) — либо явно указать как ограничение в материалах сдачи.
8. K08: явно указать в README и материалах сдачи, что точка входа Альфа-Бизнеса — ограничение прототипа (или добавить мокап главного экрана).
9. Скорректировать прежние отчёты (`FINAL_COMPOSE_VERIFICATION.md`, `BACKEND_DEPLOYMENT_HANDOFF.md`): smoke-compose не подтверждает основную Telegram-конфигурацию.
