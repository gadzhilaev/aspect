# Проверка реальной загрузки новостей (этап 6.13)

Дата: 2026-10-23  

Цель: внешний RSS → `RawNewsItem` → `Event` → публичная лента → профильная релевантность.
Выдуманные новости в ленту не добавлялись. Live LLM не вызывался.

Связанные: `CASE_PERSONALIZED_FEED.md`, `EVENT_DISCOVERABILITY.md`, `COMPETITION_UI_ACCEPTANCE.md`.

---

## 1. Изолированный стенд

| | |
|--|--|
| Копия | `data/competition_stand/real_news_613` |
| Источник | `data/competition_stand/ui_acceptance_611/stand.db` (sqlite backup) |
| SHA256 копии | `e5c40ee714c1b9bc…` |
| API / Web | `:8020` / `:5180` |
| Root `.env` / `:8003` / CSV | не трогались |

Перед записью проверен URL БД (без секретов):

```json
{
  "scheme": "sqlite",
  "relative_path": "data/competition_stand/real_news_613/stand.db",
  "exists": true,
  "size_bytes": 1811357696,
  "is_source_ui_stand": false,
  "is_real_news_613": true
}
```

Сохранены пользователи, решения, банковские материалы исходного UI-стенда.

---

## 2. Источники

Конфиг по умолчанию (`INGESTION_RSS_FEEDS`): CBR, Interfax, Vedomosti.
В прогоне использованы **1–2** доступных RSS:

- `https://www.cbr.ru/rss/RssNews` — HTTP 200 — OK
  - sample: 'Решения Банка России в отношении участников финансового рынка'
- `https://www.interfax.ru/rss.asp` — HTTP 200 — OK
  - sample: '"Яндекс" восстановил доступ более чем к 90% данных клиентов Yandex Cloud'

Лимит: `15` записей на ленту (суммарно ≤ 30).
Timeout: 20.0s, повторы: 2.
Исходные XML сохранены вне Git: `data/competition_stand/real_news_613/fixtures/rss/`.

---

## 3. Команда и безопасная конфигурация

```powershell
python scripts/verify_real_news_ingestion_613.py
```

Эквивалент ручного прогона в уже подготовленную копию:

```powershell
# Загрузить stand.env в процесс (DATABASE_URL → real_news_613), затем:
python -m app.jobs.ingest_news --heuristic-enrich
```

Важно: `--heuristic-enrich` → `prefer_live_enrich=False` → только `heuristic_enrich`
(без OpenAI / hackathon gateway). При `prefer_live=True` и `ASSISTANT_PROVIDER=hackathon`
`live_enrich` **блокируется** (`INGESTION_LIVE_BLOCKED`), а не тихо уходит на другого провайдера.

Запуск копии как отдельного UI-стенда (исходный `ui_acceptance_611` не переключается):

```powershell
.\scripts\run_competition_ui_backend.ps1 -StandDir data\competition_stand\real_news_613
.\scripts\run_competition_ui_frontend.ps1 -StandDir data\competition_stand\real_news_613
```

Сайт: http://127.0.0.1:5180  ·  API: http://127.0.0.1:8020/health

---

## 4. Счётчики загрузки и публикации

| Метрика | Значение |
|---------|----------|
| fetched | 30 |
| inserted | 28 |
| duplicates (1-й проход) | 2 |
| clusters | 28 |
| published Events | 13 |
| rejected clusters | 15 |
| provider errors | ['failing_probe:fetch:RuntimeError'] |

Отказы raw (причины):

```json
{
  "unverified_single_source": 15
}
```

Ожидаемо: коммерческий RSS с одним издателем → `unverified_single_source`;
официальный CBR (`is_official`) публикуется один.

Счётчики БД до → после: см. машинный отчёт `verification_report.json`.

---

## 5. Дедупликация

Повторная обработка тех же RSS:

| | |
|--|--|
| fetched | 30 |
| inserted | 0 |
| duplicates | 30 |
| Δ raw_news_items | 0 |
| Δ live events | 0 |

PASS, если `inserted≈0`, `duplicates≈fetched`, Δ raw/events = 0 (или только уже
обработанные pending без новых URL).

---

## 6. Примеры настоящих заголовков

- **Решения Банка России в отношении участников финансового рынка**
  - источник: Банк России
  - URL: https://cbr.ru/rbr/rbr_fr
  - дата публикации (occurred_at): `2026-10-23 14:21:56.000000`
  - fetched_at: `2026-10-23 14:55:53.595934`
  - occurred==fetched подмена: `False`
  - excerpt origin: `rss_description_or_title`

- **Вмененная ставка валютного свопа овернайт в юанях**
  - источник: Банк России
  - URL: https://cbr.ru/hd_base/impliedratecny
  - дата публикации (occurred_at): `2026-10-23 14:02:17.000000`
  - fetched_at: `2026-10-23 14:55:53.603768`
  - occurred==fetched подмена: `False`
  - excerpt origin: `rss_description_or_title`

- **Данные о поддельных денежных знаках, выявленных в банковской системе России в III квартале 2026 года**
  - источник: Банк России
  - URL: https://cbr.ru/statistics/cash_circulation
  - дата публикации (occurred_at): `2026-10-23 13:45:01.000000`
  - fetched_at: `2026-10-23 14:55:53.609774`
  - occurred==fetched подмена: `False`
  - excerpt origin: `rss_description_or_title`

- **«Вестник Банка России» № 37 (2626) от 23 октября 2026 года**
  - источник: Банк России
  - URL: https://cbr.ru/Queries/XsltBlock/File/131643/-1/2626
  - дата публикации (occurred_at): `2026-10-23 13:45:00.000000`
  - fetched_at: `2026-10-23 14:55:53.615775`
  - occurred==fetched подмена: `False`
  - excerpt origin: `rss_description_or_title`

- **Проекты нормативных документов Банка России для публичного обсуждения**
  - источник: Банк России
  - URL: https://cbr.ru/project_na?tab.current=t2
  - дата публикации (occurred_at): `2026-10-23 13:38:00.000000`
  - fetched_at: `2026-10-23 14:55:53.622248`
  - occurred==fetched подмена: `False`
  - excerpt origin: `rss_description_or_title`

- **Списки саморегулируемых организаций арбитражных управляющих**
  - источник: Банк России
  - URL: https://cbr.ru/registries/sro
  - дата публикации (occurred_at): `2026-10-23 12:13:53.000000`
  - fetched_at: `2026-10-23 14:55:53.627595`
  - occurred==fetched подмена: `False`
  - excerpt origin: `rss_description_or_title`

Heuristic summary/claims строятся из title/excerpt RSS; это не текст редакции банка
и не выдаётся как bank evidence.

---

## 7. Публичная и персональная лента

### Public

```json
{
  "status": 200,
  "total": 14,
  "live_count": 13,
  "demo_count": 1,
  "sample": [
    {
      "id": "evt_live_7eb191deac9177c059eebc63",
      "title": "Решения Банка России в отношении участников финансового рынка",
      "is_demo": false,
      "occurred_at": "2026-10-23T14:21:56",
      "primary_source_url": "https://cbr.ru/rbr/rbr_fr",
      "publisher": "Банк России"
    },
    {
      "id": "evt_live_1b750016bc79e76597e8b47c",
      "title": "Вмененная ставка валютного свопа овернайт в юанях",
      "is_demo": false,
      "occurred_at": "2026-10-23T14:02:17",
      "primary_source_url": "https://cbr.ru/hd_base/impliedratecny",
      "publisher": "Банк России"
    },
    {
      "id": "evt_live_5c942456ecd2d185eacb32ea",
      "title": "Данные о поддельных денежных знаках, выявленных в банковской системе России в III квартале 2026 года",
      "is_demo": false,
      "occurred_at": "2026-10-23T13:45:01",
      "primary_source_url": "https://cbr.ru/statistics/cash_circulation",
      "publisher": "Банк России"
    },
    {
      "id": "evt_live_91bdbcdc2e3694fb82aa76bf",
      "title": "«Вестник Банка России» № 37 (2626) от 23 октября 2026 года",
      "is_demo": false,
      "occurred_at": "2026-10-23T13:45:00",
      "primary_source_url": "https://cbr.ru/Queries/XsltBlock/File/131643/-1/2626",
      "publisher": "Банк России"
    },
    {
      "id": "evt_live_0b8dfa282d4d06a2a84a43f4",
      "title": "Проекты нормативных документов Банка России для публичного обсуждения",
      "is_demo": false,
      "occurred_at": "2026-10-23T13:38:00",
      "primary_source_url": "https://cbr.ru/project_na?tab.current=t2",
      "publisher": "Банк России"
    },
    {
      "id": "evt_comp_stand_policy_rate_32f5aef5",
      "title": "[ДЕМО] Сохранение ключевой ставки ЦБ (синтетическое событие стенда)",
      "is_demo": true,
      "occurred_at": "2026-09-20T12:00:00",
      "primary_source_url": null,
      "publisher": "Демонстрационный стенд (синтетика)"
    }
  ]
}
```

### Personal A / B

Правила узкие: `policy_rate` × LOA/DEP. Не каждая экономическая новость попадает в «Для вас».

```json
{
  "A": {
    "login_status": 200,
    "company_id": "07ebf2b6-1553-4765-962e-e807bb0dd1e2",
    "company_name": "Демо-компания A · U_264",
    "feed_status": 200,
    "dashboard_status": 200,
    "feed_total": 1,
    "profile_match_count": 1,
    "live_in_personal": 0,
    "profile_titles": [
      "[ДЕМО] Сохранение ключевой ставки ЦБ (синтетическое событие стенда)"
    ],
    "dashboard_priority_titles": [
      "[ДЕМО] Сохранение ключевой ставки ЦБ (синтетическое событие стенда)"
    ],
    "score_kinds": [
      "event_severity_signal"
    ]
  },
  "B": {
    "login_status": 200,
    "company_id": "d81efc06-d14d-4407-97d7-852c454c3f15",
    "company_name": "Демо-компания B · U_92",
    "feed_status": 200,
    "dashboard_status": 200,
    "feed_total": 1,
    "profile_match_count": 1,
    "live_in_personal": 0,
    "profile_titles": [
      "[ДЕМО] Сохранение ключевой ставки ЦБ (синтетическое событие стенда)"
    ],
    "dashboard_priority_titles": [
      "[ДЕМО] Сохранение ключевой ставки ЦБ (синтетическое событие стенда)"
    ],
    "score_kinds": [
      "case_profile_match"
    ]
  }
}
```

**Вывод по профилю:** Честно: в загруженном наборе нет новости, прошедшей узкое правило policy_rate×LOA/DEP для попадания в «Для вас» как case_profile_match (или совпадение только у прежней синтетики). Правила не ослаблялись.

### Синтетика

```json
{
  "count": 1,
  "events": [
    {
      "id": "evt_comp_stand_policy_rate_32f5aef5",
      "title": "[ДЕМО] Сохранение ключевой ставки ЦБ (синтетическое событие стенда)",
      "is_demo": true,
      "synthetic_demo_event": true
    }
  ]
}
```

---

## 8. Impact / Scenario / Decision

- Ingestion вызывает `recompute_event_for_ready_companies` после publish → Impact **может** создаваться для ready twins: Δ impacts = 0.
- Δ scenarios = 0 (ожидание 0).
- Δ decisions = 0 (ожидание 0).
- Скрытого создания Scenario/Decision / изменения сохранённых решений не обнаружено.

---

## 9. Live LLM

- `prefer_live_enrich`: false
- `OPENAI_API_KEY` в стенде: пустой
- `ASSISTANT_PROVIDER`: hackathon
- Зафиксированные model HTTP во время ingest: `[]`
- Вердикт: **PASS — model HTTP не зафиксированы**

Минимальный дефект исправлен: при отсутствии `published_at` публикация отклоняется
(`missing_publication_date`), а не подставляет `now()` / `fetched_at`. Регрессия:
`tests/test_ingestion.py::test_missing_publication_date_does_not_use_fetch_time`.

---

## 10. Ограничения и ошибки

- Только RSS whitelist; полный текст статей не скачивался.
- Interfax/Vedomosti без второго независимого издателя → unverified_single_source.
- GDELT/Cbr HTML-провайдеры в этот ограниченный прогон не включались.
- Банковский evidence не гарантирован для каждой новости (as_of / eligibility / scope).
- Ingestion после publish может создать EventImpact для ready companies — это существующее поведение.

Машинный отчёт (без секретов): `data/competition_stand/real_news_613/verification_report.json`

