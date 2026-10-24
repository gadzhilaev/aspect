# Mobile ↔ sanitized competition stand

Подключение Flutter-приложения Aspect к очищенному конкурсному стенду
(`kontur_mobile_competition_stand_sanitized_20261024_1640.zip`) и копии backend
в этом репозитории. Это восстановление/подключение, не новая система.

## Версия кода

| | |
|--|--|
| Git HEAD | `ac1ca8b` (ветка `main`, локально ahead of origin) |
| Незакоммиченные изменения | да: bank_materials (оригинал), mobile prefs/012, Flutter API/честные UI, docs |
| Commit / push / deploy | **не** выполнялись |

Архив стенда (проверен до использования):

- путь: `~/Downloads/kontur_mobile_competition_stand_sanitized_20261024_1640.zip`
- SHA-256: `c4a28c1c32c25680b7fd315275d454755e61713aa5e2041516bbfcfa782c8dda` (совпал)

## Пути на этой машине (без секретов)

| Роль | Путь |
|--|--|
| Распаковка пакета (read-only DB + storage) | `_competition_stand/pack/` |
| Исходная БД (неизменная копия) | `_competition_stand/pack/stand.db.immutable_original` |
| Рабочая БД (миграции + runtime) | `_competition_stand/runtime/stand_work.db` |
| PDF / OCR storage | `_competition_stand/pack/storage/` |
| Локальный launcher / env | `_competition_stand/runtime/start_api.sh`, `stand.env.local`, `secret.key.local` |
| Пароли demo A/B | `_competition_stand/pack/demo_password.local` (**gitignore**) |

Каталоги `_competition_stand/`, `**/demo_password.local`, `**/.env.stand.local` —
в `.gitignore`. Старая `backend/kontur.db` и процесс на `:8003` не трогались
как источник данных стенда.

## Миграции

| | |
|--|--|
| Схема пакета | Alembic **011** |
| Наша миграция | **012** (`012_user_mobile_prefs.py`, `down_revision = 011`) → `users.preferences_json` |
| Рабочая БД после `alembic upgrade head` | **012** |
| Данные после upgrade | companies=2, events=41, bank_documents=9, bank_fragments=28; `PRAGMA integrity_check=ok` |
| Stamp вместо upgrade | **не** использовался |
| Runtime ALTER / `ensure_demo` поверх стенда | **не** запускались; silent ALTER в lifespan убран ранее |

## Backend: запуск

Конкурсный профиль (ключи LLM пустые — live-вызовы не делались):

```text
COMPETITION_MODE=true
ASSISTANT_PROVIDER=hackathon
ASSISTANT_AGENT_LOOP=true
HACKATHON_BASE_URL=https://changellenge.up.railway.app/v1
HACKATHON_MODEL=deepseek/deepseek-v4.1-flash
CASE_CONTEXT_SLOT_KEY=competition_default
BANK_MATERIALS_STORAGE_ROOT=<pack>/storage
BANK_MATERIALS_ALLOWED_OCR_RUN_IDS=<9 id из stand_manifest.json>
DATABASE_URL=sqlite:///<runtime>/stand_work.db
```

Запуск:

```bash
_competition_stand/runtime/start_api.sh
# uvicorn app.main:app --host 0.0.0.0 --port 8020
```

- API: `http://127.0.0.1:8020` (симулятор / эта машина)
- LAN: `http://192.168.0.45:8020` (физический телефон в той же Wi‑Fi; IP может смениться)
- Scheduler / Telegram polling / worker / webhook — **не** стартовали
- `seed_demo` / `ensure_demo` поверх стенда — **не** запускались

### bank_materials

Оригинальный модуль уже в `backend/app/services/bank_materials/`
(не stubs). Повторная установка из `aspekt_bank_materials_patch.zip`
не требовалась.

Отсутствующий в дереве модуль (не блокирует этот стенд):
`app.services.competition_stand` — из‑за него не собирается
`tests/test_competition_stand_storage_regression.py`. Остальной bank/case API
работает.

## API-проверки (выполнены против рабочей БД)

Демо: `competition-demo-a@example.com` / `competition-demo-b@example.com`
(пароль только в `demo_password.local`, в отчёт не печатается).

| Проверка | Результат |
|--|--|
| `GET /health` | ok, `telegram_configured=false` |
| Login A / B + refresh | 200 |
| `GET /users/me` | A → company A (`U_264`), B → company B (`U_92`) |
| `GET /companies/{A}/context` | `case_context.status=profile_available`, `external_uid=U_264`, slot `competition_default`, snapshot из manifest |
| ACL: A → context/profile/events B | **403** |
| `GET /public/news` | 200, items > 0 |
| `GET /companies/{A}/events` | 200 (персональная лента может быть короткой/пустой — ожидаемо) |
| Policy Rate `evt_comp_stand_policy_rate_2df103df?company_id=A` | 200 |
| Impact того же события | **404** (не блокирует bank-evidence / обсуждение) |
| `GET /events/.../bank-evidence` | `status=available`, evidence > 0 |
| Document / fragment metadata | 200 |
| PDF `GET /bank-materials/files/{id}/content` + Bearer | 200, `%PDF`, SHA-256 совпал с БД |
| PDF без Authorization | **401** |
| PDF путь | `_competition_stand/pack/storage/...` (не старый проект) |
| Перезапуск API + повтор ключевых проверок | 9/9 PASS |

Live **не** выполнялись: LLM (hackathon key пустой), DaData, Telegram send/poll,
news scheduler.

## Flutter

| | |
|--|--|
| Механизм base URL | `lib/api/api_config.dart` → `--dart-define=API_BASE=...` или default порт **8020** |
| iOS Simulator / desktop | `http://127.0.0.1:8020` |
| Android emulator | `http://10.0.2.2:8020` |
| Физический телефон | **не** localhost; нужен LAN: `--dart-define=API_BASE=http://192.168.0.45:8020` |

Честные состояния (на пути стенда):

- нет подстановки «СеверПром» при ошибке в news detail fallback title path;
- bank-блок только из API evidence (без статической цитаты);
- Telegram «подключён» только после подтверждения с сервера;
- пустая история чата при недоступности API (без выдуманного transcript);
- Impact 404 не обязан блокировать обсуждение.

### Что проверено в запущенном приложении vs только код/тестами

| | |
|--|--|
| Hot restart после смены default порта на 8020 | выполнен (DTD, устройство Gadzhilaev) |
| Login / лента / PDF **на физическом устройстве** против стенда | **не** подтверждены end-to-end в этой сессии: нужен полный `flutter run` с `API_BASE` на LAN-IP (localhost на телефоне — сам телефон) |
| `flutter analyze` (изменённые файлы) | No issues |
| `flutter test` | 1/1 passed |
| Backend pytest (case/bank/ACL/mobile/alembic/assistant context) | **59 passed, 2 skipped** (чистый env без stand leakage) |

## Следующая ручная проверка

1. Убедиться, что стенд слушает `:8020`:
   `curl -s http://127.0.0.1:8020/health`
2. Симулятор: hot restart / уже default `8020`.
3. Физический телефон (тот же Wi‑Fi):

```bash
flutter run --dart-define=API_BASE=http://192.168.0.45:8020
```

   (IP сверить: `ipconfig getifaddr en0`. Firewall/туннель не открывать без явной просьбы.)
4. Логин demo A → компания A · U_264; переключение/логин B → данные A не видны.
5. Лента / Policy Rate event / материалы банка / PDF с сессией.
6. Открыть обсуждение: история может быть пустой (ожидаемо после sanitize).
7. **Не** слать вопрос в live-модель без ключа и отдельного разрешения.
8. При появлении ключа — только в gitignored env процесса API, не в Flutter/`dart-define`.

## Diff к общему backend (для merge)

Существенные незакоммиченные области:

- `backend/app/services/bank_materials/**` — полный оригинальный модуль
- `backend/alembic/versions/012_*.py` + убранный silent ALTER
- `backend/app/api/v1/auth.py` (+ mobile prefs / delete hardening)
- Flutter `lib/api/api_config.dart` (порт 8020) + honest feed/TG/bank/chat
- docs: этот файл, reconciliation / patch README

Runtime `_competition_stand/**` в git **не** входит.
