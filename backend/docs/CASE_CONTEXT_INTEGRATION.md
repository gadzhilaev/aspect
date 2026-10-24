# Case context integration (Этап 1.14)

Дата: 2026-10-20  
Изолированная сквозная проверка: копия БД импорта 1.9 → activate → demo Company links → HTTP API → отдельный Vite для ручного просмотра.

## Копия БД

| | |
|--|--|
| Источник (1.9, не изменялся) | `data/case/verification/case_verify_20261020T121608Z.db` (~1.69 GiB) |
| Копия (SQLite `Connection.backup`) | `data/case/verification/case_ctx_integration_20261020T134746Z.db` |
| Свободное место перед копией | ~372 GiB на `C:` |
| Артефакт стенда (gitignore) | `data/case/verification/case_context_integration_latest.json` |

Рабочая БД, root `.env`, `web/.env` и исходная БД 1.9 **не** менялись.  
CSV повторно не импортировались. Предыдущие verification DB не удалялись.

## Активация (только в копии)

| Проверка | Результат |
|----------|-----------|
| Ready snapshot | `d8fa5477-058e-47c2-9c88-030a20ea92fe` (`hack-raw-v2`, seq=1) |
| `expect-no-active` | `activated` |
| Повтор | `already_active` |
| Pointer в копии | → тот же snapshot, status=`active` |
| Исходная БД 1.9 | status=`ready`, pointer=`NULL` |

## Demo-пользователи и компании (только копия)

Демонстрационные названия, не выдаются за реальные юрлица каталога.

| Роль | Email | Company |
|------|-------|---------|
| A | `case-demo-a@example.com` | «Демо-контур Альфа (стенд)» |
| B | `case-demo-b@example.com` | «Демо-контур Бета (стенд)» |
| Outsider | `case-demo-outsider@example.com` | — |

Пароль стенда: `CaseCtxDemo1!` (только эти изолированные аккаунты).

### Привязанные организации (различающиеся продукты)

| Company | U_ID | LOA | DEP | OKVED (consensus) | город |
|---------|------|-----|-----|-------------------|-------|
| Альфа | `U_264` | true | false | 46.69.2 | г. Санкт-Петербург |
| Бета | `U_92` | false | true | 46.46 | г. Челябинск |

Единицы выручки не угадывались; порог 15 млрд ₽ не применялся.

### Дефект и исправление

Первый логин с `@example.test` получил HTTP 422 (`EmailStr`).  
Аккаунты переведены на `@example.com`. Тест: `tests/test_login_email_validation.py` (2 passed).  
ACL и fallback UI не ослаблялись.

## HTTP API (проверено)

Backend: `http://127.0.0.1:8014`  
`DATABASE_URL` + `CASE_CONTEXT_SLOT_KEY=competition_default` только в окружении процесса.  
Токены в отчёт не выводились. Результат: `case_context_http_verify.json` → **passed=true**.

| Проверка | OK |
|----------|----|
| Login A/B/outsider | ✓ |
| `GET /users/me` | ✓ |
| Context A → `profile_available`, snapshot `hack-raw-v2` | ✓ |
| Ручное имя компании сохранено | ✓ |
| Products A: LOA=true, DEP=false | ✓ |
| Products B: LOA=false, DEP=true (отличие от A) | ✓ |
| Factoring status валиден | ✓ |
| Revenue: unit null, `do_not_treat_as_rub`, без «₽» | ✓ |
| Provenance = active snapshot + `df_Uid_data_hack.csv` | ✓ |
| A → context B = 403 | ✓ |
| Outsider → A/B = 403 | ✓ |
| Нет `raw_json` в ответе | ✓ |
| GET не меняет links/memberships (осталось 2/2) | ✓ |

Проверка шла через настоящий HTTP (`httpx`), не через прямой вызов Python-сервиса.

## Frontend для ручного просмотра

| | |
|--|--|
| Vite | `http://127.0.0.1:5174/` |
| Страница компании | `http://127.0.0.1:5174/company` |
| API base / proxy target процесса | `http://127.0.0.1:8014` |
| `web/.env` | не редактировался |

Сетевая проверка: `GET 5174/api/v1/public/categories` ≡ ответ uvicorn на 8014.

**Браузер / CDP / скриншоты не запускались.**  
HTTP API проверен; визуальный UI и клики в браузере — на ручной просмотр.

### Ручной вход

1. Открыть `http://127.0.0.1:5174/login`
2. Войти: `case-demo-a@example.com` / `CaseCtxDemo1!`
3. Открыть `http://127.0.0.1:5174/company` — блок «Данные компании из источника»
4. Для сравнения: выйти и войти как `case-demo-b@example.com` (другие LOA/DEP)

## Процессы и остановка

Запущены отдельно (обычный сайт на 5173/8003 не трогали):

| Назначение | Как поднят | Как остановить только его |
|------------|------------|---------------------------|
| Isolated API | `python scripts/run_case_context_api.py 8014` | завершить процесс на порту **8014** (или PID launcher’а) |
| Isolated Vite | `npx vite --port 5174` с env `VITE_API_BASE_URL`/`VITE_PROXY_TARGET` | завершить процесс на порту **5174** |

PowerShell (только эти порты):

```powershell
Get-NetTCPConnection -LocalPort 8014,5174 -State Listen |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

Повторный подъём API:

```bash
python scripts/run_case_context_api.py 8014
```

Vite (из `web/`, без правки `.env`):

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8014"
$env:VITE_PROXY_TARGET="http://127.0.0.1:8014"
npx vite --host 127.0.0.1 --port 5174 --strictPort
```

## Что проверено / что остаётся ручным

**Проверено:** backup, activate/idempotent, source 1.9 intact, link двух разных профилей, полный HTTP ACL/context/provenance/products/revenue, proxy Vite→API, отсутствие записи на GET.

**Ручное:** визуальный вид страницы `/company`, светлая/тёмная тема, смена компании в UI, focus/keyboard.

**Не делалось:** полный pytest-сюит, повторный CSV-импорт, активация/привязка на рабочей или исходной 1.9 БД.

Технические артефакты с данными — под `data/case/verification/` (gitignore), в Git не добавлялись.

**Стоп этапа 1.14.**
