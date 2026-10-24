# Первичные публикации на основном стенде

Дата: 2026-10-24

Перенос 15 проверенных первичных публикаций (WTO / ФТС / EC presscorner) на основной стенд без затирания пользователей и истории.

Связанные: `PRIMARY_SOURCE_PUBLICATION.md`, `BUSINESS_NEWS_COVERAGE.md`.

---

## 1. Связка сайта

| | |
|--|--|
| Сайт | http://127.0.0.1:5180 |
| API | http://127.0.0.1:8020 |
| БД | `data/competition_stand/real_news_613/stand.db` |
| provider | hackathon |
| agent-loop | True |
| competition_mode | True |
| backup | `data/competition_stand/real_news_613/backups/stand_pre_primary_20261024T100748Z.db` |
| backup sha256 | `465cca822d1d396f…` |

Другие стенды (не основной UI):

- `5187` / `8027` — telegram_live (mock), отдельно;
- `business_news_coverage` — рабочая копия для политики источников;
- не поднимать новый frontend/API на других портах для этой проверки.

---

## 2. Dry-run

Кандидатов: **15** (insert=15, already-present=0).

Перенос через `store_article` (dedupe URL/external_id/hash) + `process_pending(personalize=False)` + `reprocess_rejected` при необходимости. Целиком тестовая БД поверх основной **не** копировалась.

---

## 3. Apply

| | |
|--|--|
| raw inserted | 15 |
| raw duplicates | 0 |
| Events published | 15 |
| rejected | 0 |
| idempotent published | 0 |
| Δ users | 0 |
| Δ companies | 0 |
| Δ scenarios | 0 |
| Δ decisions | 0 |
| Δ outbox | 0 |
| Δ telegram_subs | 0 |
| decisions unchanged | True |

Telegram / live LLM / пересчёт всех компаний: **не запускались** (`personalize=False`).

### Опубликованные примеры

- **Talks kick off for Timor-Leste's accession to government procurement pact** (`evt_live_7186d75def3d8806cd9c8e2b`)
  - occurred_at=2026-10-14T00:00:00, reason=official_source, official=['wto']
  - World Trade Organization — Latest news: https://wto.org/english/news_e/news26_e/gpro_14oct26_515_e.htm (published_at=2026-10-14T00:00:00)
- **Import Licensing Committee addresses notifications, trade concerns, transparency efforts** (`evt_live_d95d431d422eba9face81e66`)
  - occurred_at=2026-10-15T00:00:00, reason=official_source, official=['wto']
  - World Trade Organization — Latest news: https://wto.org/english/news_e/news26_e/impl_15oct26_518_e.htm (published_at=2026-10-15T00:00:00)
- **WTO and multilateral partners review progress on supply chain finance initiative** (`evt_live_71359a4382035593ade084a2`)
  - occurred_at=2026-10-16T00:00:00, reason=official_source, official=['wto']
  - World Trade Organization — Latest news: https://wto.org/english/news_e/news26_e/trfin_16oct26_517_e.htm (published_at=2026-10-16T00:00:00)
- **The Philippines launches safeguard investigation on pork** (`evt_live_b63360b461136c95fa461436`)
  - occurred_at=2026-10-21T00:00:00, reason=official_source, official=['wto']
  - World Trade Organization — Latest news: https://wto.org/english/news_e/news26_e/safe_phl_21oct26_520_e.htm (published_at=2026-10-21T00:00:00)
- **Trade Facilitation Committee advances TFA review and discusses implementation support** (`evt_live_462a8ca908ca4c6b02a60165`)
  - occurred_at=2026-10-21T00:00:00, reason=official_source, official=['wto']
  - World Trade Organization — Latest news: https://wto.org/english/news_e/news26_e/fac_21oct26_522_e.htm (published_at=2026-10-21T00:00:00)
- **В центральном аппарате ФТС России будет воздвигнут мемориал таможенникам – участникам специальной военной операции** (`evt_live_b2e647f12caffbe7af9546db`)
  - occurred_at=2026-10-23T09:06:00, reason=official_source, official=['fts_ru']
  - Федеральная таможенная служба: https://customs.gov.ru/press/federal/document/714058 (published_at=2026-10-23T09:06:00)
- **EU Civil Protection Mechanism turns 25** (`evt_live_1230212dfea4b3e257d05f5e`)
  - occurred_at=2026-10-23T09:09:38, reason=official_source, official=['ec_presscorner']
  - Press releases - RSS: https://ec.europa.eu/commission/presscorner/detail/en/ip_26_2248 (published_at=2026-10-23T09:09:38)
- **Состоялось торжественное открытие памятника Михаилу Дмитриевичу Поспелову** (`evt_live_035d236ad31e13feb508f46e`)
  - occurred_at=2026-10-23T09:23:00, reason=official_source, official=['fts_ru']
  - Федеральная таможенная служба: https://customs.gov.ru/press/federal/document/714064 (published_at=2026-10-23T09:23:00)
- **Daily News 23 / 10 / 2026** (`evt_live_1c2c99ee516ea6aee077d171`)
  - occurred_at=2026-10-23T09:37:47, reason=official_source, official=['ec_presscorner']
  - Press releases - RSS: https://ec.europa.eu/commission/presscorner/detail/en/mex_26_2249 (published_at=2026-10-23T09:37:47)
- **Commission proposes stronger recognition of European heritage sites*** (`evt_live_d4247dfa07e0653c21068500`)
  - occurred_at=2026-10-23T09:39:39, reason=official_source, official=['ec_presscorner']
  - Press releases - RSS: https://ec.europa.eu/commission/presscorner/detail/en/ip_26_2250 (published_at=2026-10-23T09:39:39)
- **Speech by President von der Leyen to the Hungarian National Assembly on the occasion of the 70th anniversary of the Hungarian Revolution of 1956** (`evt_live_7e87b9a60c03f355aa0077e4`)
  - occurred_at=2026-10-23T09:40:50, reason=official_source, official=['ec_presscorner']
  - Press releases - RSS: https://ec.europa.eu/commission/presscorner/detail/en/speech_26_2251 (published_at=2026-10-23T09:40:50)
- **История и искусство: в ФТС России открылись тематические экспозиции** (`evt_live_57984a7413fbe2ec94f22f10`)
  - occurred_at=2026-10-23T11:48:00, reason=official_source, official=['fts_ru']
  - Федеральная таможенная служба: https://customs.gov.ru/press/federal/document/714107 (published_at=2026-10-23T11:48:00)
- **В ФТС России состоялась встреча Валерия Пикалёва и Алексея Сазанова** (`evt_live_f6340b729c7f0e5feb30bd37`)
  - occurred_at=2026-10-23T12:05:00, reason=official_source, official=['fts_ru']
  - Федеральная таможенная служба: https://customs.gov.ru/press/federal/document/714148 (published_at=2026-10-23T12:05:00)
- **ФТС России продолжит укреплять свое лидерство за счет командной работы** (`evt_live_69d71b10217f994a843d526f`)
  - occurred_at=2026-10-23T13:45:00, reason=official_source, official=['fts_ru']
  - Федеральная таможенная служба: https://customs.gov.ru/press/federal/document/714229 (published_at=2026-10-23T13:45:00)
- **Remarks by Commissioner Šefčovič at the press conference following the informal Foreign Affairs Council (Trade)** (`evt_live_ae5d0a5f26482bb2ce292cf9`)
  - occurred_at=2026-10-23T14:54:52, reason=official_source, official=['ec_presscorner']
  - Press releases - RSS: https://ec.europa.eu/commission/presscorner/detail/en/speech_26_2252 (published_at=2026-10-23T14:54:52)

---

## 4. API-проверка

| Проверка | Результат |
|----------|-----------|
| Сайт :5180 | 200 |
| API :8020 /health | 200 |
| Vite inject VITE_API_BASE_URL | http://127.0.0.1:8020 |
| Proxy :5180 → /api/v1/public/news | 200, те же live-события |
| /api/v1/public/news?limit=50 | 29 карточек; **15/15** новых id в ленте |
| Деталь WTO pork | дата 2026-10-21, publisher WTO, URL сохранён; совпадает с БД |
| Дубли source URL (active) | 0 |
| decisions | count=1, набор id не менялся |
| Повторный transfer | published=0, inserted=0 |
| hackathon + agent-loop | сохранены в stand.env / process (ASSISTANT_PROVIDER=hackathon, ASSISTANT_AGENT_LOOP=true) |

На диске web/.env может указывать на :8003; **запущенный** Vite на :5180 инжектит :8020 (согласованный стенд). Новый frontend/API на других портах не поднимался.

## 5. Ручная проверка live-вопроса (без отправки)

- Новость: **The Philippines launches safeguard investigation on pork**
- ID: `evt_live_b63360b461136c95fa461436`
- URL: http://127.0.0.1:5180/news/evt_live_b63360b461136c95fa461436
- Открыть http://127.0.0.1:5180/news/evt_live_b63360b461136c95fa461436 → обсуждение; live-вопрос модели не отправлять на этом этапе.

---

## 6. Ограничения

- Профиль «упк» не изменялся; карточки «Для вас» не форсились.
- EC presscorner официален как первоисточник EC, не как trade-only лента.
- Секреты в отчёт не выводились.

Машинный отчёт: `data/competition_stand/real_news_613/primary_news_main_stand_report.json`
