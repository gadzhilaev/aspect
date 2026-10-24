# Проверка runtime для нового пользователя

Дата: **2026-10-24**  
Цель: установить, почему открытый сайт показывал demo seed и «Демо-объяснение»,  
и подготовить согласованный адрес с реальными новостями.

Процессы Telegram-стенда (**5187/8027**) **не** останавливались.  
Live LLM в проверке нового пользователя **не** вызывался (только маршрутизация/конфиг).

---

## 1. Что сейчас запущено (факт процесса, не root `.env`)

| URL сайта | API | БД | Provider | Agent loop | Назначение |
|-----------|-----|----|----------|------------|------------|
| **http://127.0.0.1:5187** | **127.0.0.1:8027** | `data/telegram_live/telegram_live.db` | **mock** | false | TG-3.1 polling / demo seed |
| **http://127.0.0.1:5180** | **127.0.0.1:8020** | `data/competition_stand/real_news_613/stand.db` | **hackathon** | **true** | Согласованный стенд для проверки |
| ~~5180/8020 ранее~~ | — | `real_news_613` на диске | hackathon (stand.env) | true | **Не был запущен**, пока пользователь смотрел 5187 |

Безопасные флаги (без ключей):

- Vite на **5187**: `client.ts` содержит `8027`, не `8003`/`8020`.
- Vite на **5180**: `client.ts` содержит `8020`.
- `telegram_live/stand.env`: `ASSISTANT_PROVIDER=mock`, `TELEGRAM_LIVE_STAND=true`.
- `real_news_613/stand.env`: `ASSISTANT_PROVIDER=hackathon`, `ASSISTANT_AGENT_LOOP=true`, `COMPETITION_MODE=true`, bank storage → `jury_63b/storage`.
- Root `.env` содержит `ASSISTANT_PROVIDER=hackathon` и `HACKATHON_API_KEY` (present) — **но открытый 5187 к нему не был привязан**.

### Почему были «три demo-новости»

Открытый сайт **5187 → 8027 → telegram_live.db**, собранный через `seed_demo` для Telegram:

| id | суть |
|----|------|
| `evt_china_export_001` | демо-экспорт |
| `evt_rate_hike_001` | демо-ставка |
| `evt_market_opp_001` | демо-рынок |

В БД **3** события, **0** bank_fragments.  
Стенд **real_news_613** (14 live-событий, 28 fragments) на диске был, но порты **5180/8020 были свободны** — пользователь его не открывал.

---

## 2. Чат: «Демо-объяснение»

| Вопрос | Ответ |
|--------|--------|
| Это только старая история? | На **5187/8027** provider процесса = **mock**. Новые ответы тоже идут в mock. |
| Как устроена метка | `explanation_basis(provider=mock)` → `demo_explain` → UI «Демо-объяснение». |
| История в telegram_live | Таблицы assistant есть; колонки сообщений **без** `answer_basis` (метка на conversation/ответе API). Дефолт UI тоже `demo_explain`. |
| Переименование mock→AI | **Не** делалось. |

На копии real_news_613 при `ASSISTANT_PROVIDER=hackathon` старт conversation даёт `answer_basis=ai_explain_hackathon` (без отправки сообщения в LLM).

---

## 3. Новый пользователь на копии стенда

Копия: `data/competition_stand/new_user_runtime_verify/stand.db`  
(backup `real_news_613`, исходник не трогали). Отчёт JSON: `…/verification.json`.

| Проверка | Результат |
|----------|-----------|
| Регистрация / verify / login | 200 |
| Компаний сразу после регистрации | **0** (нет чужой membership / Severprom) |
| Авто-SYNTHETIC_U | **нет** |
| Публичная лента `/api/v1/public/news` | **14** items, `evt_live_*`, **без** `evt_china_export_001` |
| Создание своей компании | 200, новый id ≠ Severprom |
| «Для вас» (dashboard) | **empty** до профиля/цепочки — честный empty, не чужие impacts |
| Обсуждение | старт conversation **200**, `ai_explain_hackathon` (сообщение в LLM не слали) |
| Case-блок | всегда отдаётся; для новой компании статус связи кейса — **not_linked** / нет подмены профилем Severprom (`context_mentions_severprom=false`) |

Автопривязка к SYNTHETIC_U по имени/ИНН **не** обнаружена.

---

## 4. Фраза «Ограничение связано с не знаю → большая»

### Откуда

В `telegram_live.db` у пользовательской компании узлы:

- component **«не знаю»**
- production_line **«большая»** с `output_share_percent=24` (дефолт формы onboarding)

Impact собрал путь и текст:

`Ограничение связано с не знаю → большая.`  
(`app/services/impact.py`, join имён узлов пути)

Это **не** demo-seed Severprom (у Severprom нормальные имена).  
Кнопка UI «Не знаю» в финансах только очищает поля; в цепочку пользовательские строки попали как **имена узлов** и стали «подтверждённой» долей выпуска.

### Исправление (без правки строк в БД пользователя)

1. `app/services/graph_names.py` — маркеры явного «неизвестно» (не hardcode одной фразы).
2. `impact.py` — пути с такими именами **не** дают supply-chain reason.
3. API create/patch node — **422** на unconfirmed name.
4. Onboarding: пустой `lineShare` по умолчанию; валидация имён на save chain.
5. Тесты: `tests/test_unconfirmed_node_names.py`, `tests/test_impact_skips_unconfirmed_names.py`.

Существующие узлы в БД **не** удалялись. После выката кода и recompute reason перестанет утверждать цепочку через «не знаю».

---

## 5. Согласованный адрес для дальнейшей проверки

**Открывать:** http://127.0.0.1:5180  

| Слой | Значение |
|------|----------|
| Frontend | Vite `:5180` → API `:8020` |
| API | `127.0.0.1:8020` |
| БД | `data/competition_stand/real_news_613/stand.db` |
| Provider | hackathon + agent-loop |
| Новости | публичные `evt_live_*` |
| Банк | fragments в стенде, storage `jury_63b` |
| PID/stop | `data/competition_stand/real_news_613/new_user_coherent_pids.json`, `COHERENT_STOP.txt` |

Запуск (уже использован): env из `real_news_613/stand.env` + `HACKATHON_API_KEY` из root `.env` (только в process), без переписи root `.env` / без остановки 5187.

Старые стенды сохранены. Telegram **5187** оставлен как есть (demo+mock+polling).

Live вопрос в чат пользователь отправит **отдельно** на **5180**.

---

## Простыми словами

1. **Какой сайт открывать сейчас:** http://127.0.0.1:5180 — реальные новости и hackathon.  
2. **Почему раньше были demo:** был открыт другой адрес — **5187**, это Telegram-стенд с тремя демо-событиями и mock-чатом.  
3. **Что увидит новый аккаунт на 5180:** общая лента с live-новостями; своей компании нет, пока не создаст; «Для вас» пустое, пока нет своей модели; чат помечается как hackathon-AI, не «Демо-объяснение»; чужой Severprom / SYNTHETIC_U сам не прилипает.

## Актуальный адрес стенда (primary news)

| | |
|--|--|
| **Открывать** | http://127.0.0.1:5180 → API http://127.0.0.1:8020 |
| БД | `data/competition_stand/real_news_613/stand.db` |
| provider / loop | hackathon + agent-loop |
| Primary news | см. `PRIMARY_NEWS_MAIN_STAND.md` |
| Не основной UI | `:5187`/`:8027` telegram_live; `business_news_coverage` — копия для политики источников |

Не поднимать ещё один frontend/API на новых портах для этой проверки.
