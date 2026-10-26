# Аспект

Персонализированная новостная аналитика для бизнеса.

Сервис помогает ответить на цепочку: **что произошло → почему это может касаться компании → на каких данных основан вывод → какие действия можно рассмотреть**.

| | |
|--|--|
| Мобильный клиент | Flutter (`lib/`) |
| Веб-сайт | React + Vite (`frontend/`) → https://gadzhilaev.ru/aspekt/ |
| API | FastAPI (`backend/`) |
| Версия | `1.0.0+1` · релиз [`v1.0.0`](https://github.com/gadzhilaev/aspect/releases/tag/v1.0.0) |
| Документация | **[`docs/INDEX.md`](docs/INDEX.md)** |

Прототип для хакатона «Альфа-Будущее», **не** встройка в интернет-банк Альфа-Бизнес. Кнопка «войти через Альфа-Бизнес» — демо-вход, не банковский SSO.

---

## Публичные адреса

| | |
|--|--|
| Сайт | https://gadzhilaev.ru/aspekt/ |
| API | https://gadzhilaev.ru/aspekt-api |
| Health | https://gadzhilaev.ru/aspekt-api/health |
| APK | [aspect-1.0.0.apk](https://github.com/gadzhilaev/aspect/releases/download/v1.0.0/aspect-1.0.0.apk) |
| Репозиторий | https://github.com/gadzhilaev/aspect |

Домен `alfa-aspect.ru` может быть зарегистрирован, но без DNS — рабочий вход через path на `gadzhilaev.ru`.

Подробнее о стенде: [`docs/PRODUCTION.md`](docs/PRODUCTION.md).

---

## Быстрый старт для жюри

1. Установить APK из релиза **или** открыть сайт / Flutter на стендовый API.
2. Войти учётками **demo A/B** (email ниже; **пароль** — только из `demo_password.local` пакета стенда, не из Git).
3. Пройти сценарий: компания → лента → карточка новости → материалы банка → «Обсудить с Аспект».

| Email | Компания |
|-------|----------|
| `competition-demo-a@example.com` | Демо A · case `U_264` |
| `competition-demo-b@example.com` | Демо B · case `U_92` |

Пошагово: [`docs/JURY_MOBILE_SCENARIO.md`](docs/JURY_MOBILE_SCENARIO.md).

---

## Возможности

| Возможность | Кратко |
|-------------|--------|
| Лента | Публичные и персональные события; why-label (case / industry / impact) |
| Компания | Профиль, twin, industry-profile; конкурсный справочник при case-link |
| Новость | Факт, связь с компанией, аналитика банка отдельно от вывода AI |
| Ассистент | Обсуждение события; в competition mode — hackathon LLM + agent loop |
| Банк | Фрагменты / PDF по Bearer |
| Планы действий | Варианты → подтверждение → чеклист шагов |
| Scheduler | Отдельный процесс новостей (RSS / CBR / GDELT) |
| Telegram | В коде; на стенде включается осознанно |

**Отбор ≠ поиск интернета.** Лента отбирает корпус / результат scheduler, не «все новости мира» из GET.

---

## Достоверность оценок

- **Индекс влияния ≠ убыток** и не % потерь.
- `case_profile_match` / `industry_profile_match` — тема/профиль, **не** расчёт Impact.
- `calculation_unavailable` / Impact 404 — обсуждение возможно, численные сценарии нет.
- Различайте: факт события · позиция банка · вывод модели · what-if пользователя.

Подробнее: [`backend/docs/ASSESSMENT_TRUST_AUDIT.md`](backend/docs/ASSESSMENT_TRUST_AUDIT.md).

---

## Локальный запуск

Полное демо: код из Git + **пакет данных стенда** (БД + `storage/` + env), пакет **не** в репозитории.

Требования: Python **3.12**, Flutter stable, опционально Docker.

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install --require-hashes -r requirements.lock
# env из пакета стенда: DATABASE_URL, BANK_MATERIALS_*, COMPETITION_MODE, …
alembic upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8020
```

Swagger: `http://127.0.0.1:8020/docs`  
Контракт: [`backend/contracts/openapi.json`](backend/contracts/openapi.json)

### Flutter

```bash
flutter pub get
flutter run
# другое API:
flutter run --dart-define=API_BASE=http://127.0.0.1:8020
```

По умолчанию клиент ходит на публичный API (`lib/api/api_config.dart`).  
Подключение к локальному стенду: [`docs/MOBILE_STAND_CONNECTION.md`](docs/MOBILE_STAND_CONNECTION.md).

### Docker

[`docker-compose.competition.yml`](docker-compose.competition.yml) — API + news_scheduler.  
Env-шаблон: [`backend/.env.competition.example`](backend/.env.competition.example).  
Руководство: [`backend/docs/COMPETITION_DOCKER.md`](backend/docs/COMPETITION_DOCKER.md).

Не гоняйте `seed` / destructive migrate **поверх** готовой конкурсной БД без бэкапа.

---

## ИИ (hackathon gateway)

Ключ `HACKATHON_API_KEY` — **только на сервере**, не в Flutter и не в Git.

```env
COMPETITION_MODE=true
ASSISTANT_PROVIDER=hackathon
ASSISTANT_AGENT_LOOP=true
HACKATHON_BASE_URL=https://changellenge.up.railway.app/v1
HACKATHON_MODEL=deepseek/deepseek-v4.1-flash
HACKATHON_API_KEY=<отдельно от организаторов>
```

Без ключа / при сетевом недоступе к шлюзу AI недоступен (`PROVIDER_UNAVAILABLE`, timeout).  
Диагностика: [`backend/docs/HACKATHON_PROVIDER.md`](backend/docs/HACKATHON_PROVIDER.md).

---

## Документация

Полный указатель: **[`docs/INDEX.md`](docs/INDEX.md)**

| | |
|--|--|
| Архитектура | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Мобильное приложение | [`docs/MOBILE_APP.md`](docs/MOBILE_APP.md) |
| Production / диагностика | [`docs/PRODUCTION.md`](docs/PRODUCTION.md) |
| HTTP API | [`backend/docs/MOBILE_API.md`](backend/docs/MOBILE_API.md) |

---

## Ограничения (честно)

- Пакет данных стенда и demo-пароли **вне** Git.
- Ручная регистрация без case-link → справочник «не привязан» — ожидаемо.
- Вкладка «Сценарии» во Flutter не покрывает весь backend finance-flow.
- Live LLM зависит от сети до шлюза организаторов и дневного бюджета команды.
- Telegram и часть news-путей на «голом» API выключены, пока не настроены env + worker.

---

## Лицензия / сдача

Код: репозиторий GitHub. Данные стенда и секреты — отдельная поставка команде / жюри.
