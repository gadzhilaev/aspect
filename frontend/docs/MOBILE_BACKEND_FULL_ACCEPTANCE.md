# Mobile backend ↔ frontend: полная приёмка

Дата: 2026-10-26  
Вердикт: **готово к локальному совместному демо**  
Публичное размещение: **не заявляется** (нет HTTPS, runtime secrets, проверки публичного URL).

## Стенд

| Роль | Путь / адрес |
|------|----------------|
| Frontend | `C:\Users\неважно\Desktop\kontur_back\frontend` |
| Backend (единственный для этой проверки) | `C:\Users\неважно\Desktop\kontur_back\aspect-backend-20261025\backend` |
| Runtime-копия БД | `aspect-backend-20261025\_competition_stand\runtime\stand_acceptance.db` |
| Исходный sanitized pack | `aspect-backend-20261025\_competition_stand\pack\` (**не изменялся**) |
| Старт API | `aspect-backend-20261025\_competition_stand\runtime\start_acc_api.ps1` |
| Frontend | `frontend\run_mobile_web.ps1 -ApiUrl http://127.0.0.1:8021` |
| Сайт (приёмка) | http://127.0.0.1:5182/ |
| API | http://127.0.0.1:8021/ |
| Live OpenAPI | http://127.0.0.1:8021/openapi.json — title `Kontur API`, version `1.0.0` |
| `/health` | `status=ok`, `service=kontur`, `env=test`, `telegram_configured=false` |
| Схема БД | Alembic **012** |
| Идентификация backend | uvicorn cwd = `aspect-backend-…\backend`, `DATABASE_URL` → `stand_acceptance.db` (скрипт отказывается стартовать иначе) |

Старый `kontur_back\backend` **не использовался**. Порты чужих процессов (`8003`, `8020`, `5173`, `5181`) **не останавливались**.

Scheduler / Telegram polling / массовая рассылка **не включались**. Платный DaData и live LLM **не вызывались**.

### Контракт OpenAPI

- Live API содержит `/api/v1/companies/{company_id}/industry-profile`.
- Файла `frontend/contracts/openapi.json` в дереве frontend **нет** (в адаптации отмечено отставание сохранённого контракта; расхождение зафиксировано, backend не правился).

## Изменения frontend

В этой приёмке **код frontend не менялся** — дефектов, требующих FE-fixкса, не найдено.  
Незакоммиченные локальные изменения сохранены; commit/push/deploy не выполнялись.

## Методы проверки

| Класс | Что сделано |
|-------|-------------|
| Automated API | `run_api_acceptance.py` (ранее, 47 checks ok) + целевые httpx-сценарии на `:8021` |
| Automated FE | все `npm run test:*`, `test:mobile-backend`, `build:mobile`, `lint` |
| Browser DOM | клики/формы/навигация на http://127.0.0.1:5182 без скриншотов / без `Page.captureScreenshot` |
| Real external | **не проверялись** (LLM, Telegram delivery, DaData, SMTP) |

## Таблица сценариев

| # | Сценарий | Результат | Как |
|---|----------|-----------|-----|
| A1 | Вход с неверным паролем → понятная ошибка, без demo-входа | **PASS** | browser |
| A2 | Сессия после inject / reload защищённых страниц | **PASS** | browser |
| A3 | Logout очищает access/refresh/company_id | **PASS** | browser + localStorage |
| A4 | Выбор компании только из доступных (A: одна компания) | **PASS** | browser / API |
| A5 | Preferences theme PATCH + UI «Сохранить тему» | **PASS** | API + browser |
| A6 | Смена пароля: неверный текущий → «Неверный текущий пароль» | **PASS** | browser + API |
| A7 | Успешная смена пароля + вход новым (одноразовый аккаунт) | **PASS** | API |
| A8 | Удаление SOLE_OWNER → отказ в UI и API (A и B) | **PASS** | browser + API |
| A9 | Удаление HAS_AUDIT_RECORDS | **NOT_VERIFIED** | на стенде не воспроизведено |
| A10 | Успешное удаление без данных компании | **PASS** | API (temp user) |
| A11 | Регистрация / verify-email по контракту стенда | **PASS** (стенд) / **NOT_VERIFIED** (prod email) | API: ответ содержит `demo_code`; реальная почта не проверялась |
| B1 | Компания → Продукция → интересы: GET загружает | **PASS** | browser |
| B2 | PATCH только изменённые поля (`{"brands":[…]}`) | **PASS** | browser net log |
| B3 | Очистка поля → `{"brands":[]}` | **PASS** | browser net log |
| B4 | После brand PATCH case/finance provenance не стёрты | **PASS** | API context/profile |
| B5 | Persist после reload | **PASS** | browser |
| B6 | INN lookup без ключа → `not_configured` + ручной ввод в UI | **PASS** | API + unit tests |
| B7 | Платный DaData | **NOT_VERIFIED** | намеренно не вызывался |
| C1 | Общая лента `/api/v1/public/news` в UI | **PASS** | browser |
| C2 | Фильтр категорий (`?category=macro`) | **PASS** | browser |
| C3 | Карточка demo Policy Rate, источники, ДЕМО | **PASS** | browser |
| C4 | «Для вас» по выбранной компании, `case_profile_match` без фиктивного индекса/confidence/exposure | **PASS** | browser |
| C5 | CTA «Обсудить» без обязательного Impact | **PASS** | browser |
| C6 | Empty ≠ loading ≠ error (контракты) | **PASS** | unit + UI states |
| C7 | Подбор ≠ внешний поиск публикаций по бренду | **PASS** (зафиксировано) | UI copy + API |
| D1 | Открытие беседы + история без нового LLM turn | **PASS** | browser + API |
| D2 | Impact unavailable без подставных нулей | **PASS** | browser |
| D3 | Markdown / retry без бесконечного цикла | **PASS** | unit tests |
| D4 | Банк: fragment → document UI; PDF Bearer, не в URL | **PASS** | browser + API (401 без auth, 200 PDF ~6.3MB) |
| D5 | Live LLM turn | **LIVE_LLM_NOT_VERIFIED** | новый вопрос модели не отправлялся |
| E1 | Сохранение ручного finance profile (PATCH currencies) | **PASS** | API |
| E2 | Явный recompute по demo Policy Rate | **PASS** (ожидаемый отказ) | API `422 NOT_RELEVANT` |
| E3 | Полный сценарий calc → what-if → decision draft | **NOT_VERIFIED** | нет расчётной оценки на данных стенда; UI честно показывает unavailable |
| E4 | observed/assumed/hold≠hike / FX / draft persistence | **PASS** (контракт) | unit tests; live calc path не открыт |
| F1 | Telegram settings scoped по компании; status «Не подключён» | **PASS** | browser |
| F2 | `linked` только с сервера; server news notifications off | **PASS** | API |
| F3 | Живая доставка / test-send / webhook | **NOT_VERIFIED** | намеренно не трогались |
| G1 | Viewport 375 / 390 / 430: overflow=false, меню/вкладки доступны | **PASS** | Emulation + DOM metrics |
| G2 | 768 / 1440: лента и фильтры доступны (snapshot) | **PASS** | browser snapshot |
| G3 | Светлая/тёмная тема | **PASS** | browser settings + local theme |
| H1 | FE unit/mobile-backend tests | **PASS** | 13 script packs, 0 fail |
| H2 | `build:mobile` | **PASS** | |
| H3 | `lint` (oxlint) | **PASS** (warnings only, exit 0) | |

## Backend-дефекты (не правились)

Явных багов backend, ломающих демо-маршрут, **не зафиксировано**.  
Ожидаемое поведение стенда:

| Endpoint | Условие | Ожидание | Факт |
|----------|---------|----------|------|
| `POST /api/v1/events/{id}/recompute-impact` | demo Policy Rate + U_264 без twin/feature match | unavailable / not relevant | `422 NOT_RELEVANT` |
| `POST /api/v1/company-registry/lookup` | без DaData | честный not_configured | `200 status=not_configured` |
| `DELETE /api/v1/users/me` | sole owner demo A/B | отказ | `409 SOLE_OWNER` |

## Frontend-дефекты

**Не найдены** в ходе этой приёмки (исправлений не потребовалось).

## Automated / browser / external

- **Automated:** API acceptance + npm test packs + build + lint — зелёные.
- **Browser:** auth, company/industry, news/for-you, assistant history, bank PDF, notifications, settings, logout, viewports — пройдены через DOM/клики.
- **External services:** LLM live, Telegram delivery, DaData, SMTP — **NOT_VERIFIED**.

## Перед хостингом (осталось человеку)

1. HTTPS + секреты runtime (JWT, DB, storage) вне репозитория.
2. Реальная доставка email (без `demo_code` в ответе API).
3. Опционально: LLM-ключ и лимитированный live-turn в ассистенте.
4. Telegram bot config + controlled test-send на отдельном стенде.
5. Проверка публичного URL и CORS.
6. Не смешивать со старым `kontur_back\backend` и чужими портами.

## Остановка только процессов этой приёмки

Сайт: http://127.0.0.1:5182/  
API: http://127.0.0.1:8021/

```powershell
Stop-Process -Id 24940 -ErrorAction SilentlyContinue   # Vite mobile FE :5182
Stop-Process -Id 26976 -ErrorAction SilentlyContinue   # uvicorn aspect API :8021
```

Не останавливать `:8003` / `:8020` / `:5173` / `:5181` — чужие/параллельные процессы.

## Что реально проверено vs что нужно человеку

**Проверено:** изолированный aspect API на `:8021` + mobile FE на `:5182`, вход/ошибки/logout, интересы (diff PATCH / `[]` / persist), лента и «Для вас» без фиктивных индексов, банк PDF с Bearer, ассистент без Impact, TG «не подключён», finance save + честный NOT_RELEVANT, SOLE_OWNER, одноразовый change-password/delete, автотесты и mobile build.

**Нужно человеку:** разрешение на 1–2 live LLM turn; Telegram test-send; прод-регистрация с почтой; полный calc→decision на компании с достаточным финансовым/twin профилем; HAS_AUDIT_RECORDS; хостинг.
