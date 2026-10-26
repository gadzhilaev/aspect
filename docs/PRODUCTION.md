# Публичный стенд (production)

Актуальные адреса (DNS `alfa-aspect.ru` может быть пустым — используем path на gadzhilaev.ru):

| | URL |
|--|-----|
| Сайт (статика) | https://gadzhilaev.ru/aspekt/ |
| API | https://gadzhilaev.ru/aspekt-api |
| Health | https://gadzhilaev.ru/aspekt-api/health |
| OpenAPI | https://gadzhilaev.ru/aspekt-api/openapi.json |
| Репозиторий | https://github.com/gadzhilaev/aspect |
| APK | https://github.com/gadzhilaev/aspect/releases/tag/v1.0.0 |

Клиент по умолчанию бьёт в `https://gadzhilaev.ru/aspekt-api`.

## Хост и данные

Типичная раскладка на VPS:

| Путь | Содержимое |
|------|------------|
| `/opt/aspect` | compose, backend image, `.env` → `.env.competition` |
| `/var/www/aspect` | статика сайта (`frontend/` → `npm run build`, base `/aspekt/`) |
| `/stand/stand.db` | SQLite стенда |
| `/stand/storage/` | банковские PDF / OCR |
| `/stand/demo_password.local` | пароли demo A/B (**не в Git**) |

Исходники сайта в репо: [`frontend/`](../frontend/). На проде nginx отдаёт собранный `dist/` с path `/aspekt/`; API — отдельно на `/aspekt-api`.

Контейнеры (имена могут чуть отличаться):

- `aspect-api` — FastAPI  
- `aspect-news-scheduler` — ingestion  
- `aspect-telegram-worker` — при включённом TG  
- при необходимости `aspect-hackathon-egress` — SOCKS к LLM-шлюзу, если прямой egress с VPS до Railway недоступен  

`COMPETITION_MODE=true` на стенде: live LLM через hackathon provider; scheduler работает heuristic/whitelist.

## Demo-аккаунты жюри

Email:

- `competition-demo-a@example.com` → компания A · case `U_264`  
- `competition-demo-b@example.com` → компания B · case `U_92`  

Пароль — только из `demo_password.local` пакета стенда / private-канала команды. В README и публичные docs **не** копировать.

## Диагностика клиентских ошибок

`POST /api/v1/diagnostics/client-error` (без auth) — приложение шлёт полный текст сбоя логина (без пароля).

Хранение: таблица `client_error_reports` в `stand.db`. Пример выборки на сервере:

```bash
docker exec aspect-api python -c "
import sqlite3
c=sqlite3.connect('/stand/stand.db')
for r in c.execute(
  'SELECT created_at, source, screen, http_status, http_code, email_attempted, substr(message,1,160) '
  'FROM client_error_reports ORDER BY created_at DESC LIMIT 20'
):
    print(r)
"
```

Логи API: `docker logs aspect-api 2>&1 | grep client_error_report`.

## Важно для показа

| Ситуация | Ожидание |
|----------|----------|
| Ручная компания «не привязана к справочнику» | Норма: нет строки в `case_org_company_links` |
| Impact 404 / `calculation_unavailable` | Норма для case_profile_match без twin-расчёта |
| Одинаковый `reason_summary` monitoring_only | Мало данных twin/финансов у ручной компании |
| Чат 504 / timeout | Проверить egress к hackathon gateway и логи API |

Локальный Docker/стенд: [../backend/docs/COMPETITION_DOCKER.md](../backend/docs/COMPETITION_DOCKER.md), [MOBILE_STAND_CONNECTION.md](MOBILE_STAND_CONNECTION.md).
