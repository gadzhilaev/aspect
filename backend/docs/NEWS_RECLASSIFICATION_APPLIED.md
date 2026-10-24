# Применение heuristic_v2 к live-новостям основного стенда

Дата: **2026-10-24**  
Стенд: UI `:5180` → API `:8020` → БД `data/competition_stand/real_news_613/stand.db`  
Предпосылка: [`NEWS_CLASSIFICATION_FIX.md`](NEWS_CLASSIFICATION_FIX.md), dry-run `data/competition_stand/reclassify_dry_run/reclassify_dry_run_report.json`

Скрипт: `scripts/apply_heuristic_v2_reclassify.py` (`--preview` / `--apply`).

---

## 1. Перед записью

| Проверка | Результат |
|----------|-----------|
| Фактический путь БД | `C:/Users/неважно/Desktop/kontur_back/data/competition_stand/real_news_613/stand.db` (~1.81 GB) |
| Alembic | **`009`** |
| `events.severity` nullable | **да** (`PRAGMA table_info`) |
| Backup (SQLite `.backup` API) | `data/competition_stand/real_news_613/backups/stand_pre_heuristic_v2_20261024T105316Z.db` |
| SHA-256 backup | `a7bec7ead94a2ea7d0c47c27fe017789f4a02b007f1b7a9fe8bb6a4447870199` |

Превью: **28** событий к изменению; locked/manual — **0**; без raw — **0**.

По каждому событию в отчёте: старые/новые `category`, `event_type`, `severity`, `countries`, `currencies`  
→ `data/competition_stand/reclassify_applied/apply_report_20261024T105328Z.json`.

Обновлялись **только** поля heuristic-классификации:

- `category`, `event_type`, `severity`
- `match_categories_json`, `match_countries_json`, `match_currencies_json`, `match_materials_json`
- `attributes_json.classification` (+ `reclassified_at` / `reclassified_version=heuristic_v2`)

**Не** трогались: title/summary, URL/источники, даты, `is_demo`, provenance источников, сообщения ассистента, Scenario, Decision, Telegram/outbox.

---

## 2. Применение

- Транзакция одним `commit` после цикла.
- Версия: `attributes.classification.basis = heuristic_v2`, `reclassified_version = heuristic_v2`.
- Ложные теги стран/валют пересчитаны эвристикой (не «дочищены» вручную по заголовку).

Пример выставки `evt_live_57984a7413fbe2ec94f22f10`:

| | До | После |
|--|----|--------|
| category | macro | **other** |
| event_type | risk | **neutral** |
| severity | 60 | **null** |
| countries | Россия, ЕС | **Россия** |
| currencies | RUB | **[]** |

Повторный `--apply`: **changes=0**, **unchanged=28** (no-op).  
Второй backup при повторном запуске: `stand_pre_heuristic_v2_20261024T105343Z.db` (снимок уже после первого apply).

Сверка с pre-apply backup: `assistant_messages` 21=21, `scenarios` 3=3, `decisions` 1=1, `notification_outbox` 0=0, `event_sources` 29=29; тексты/даты выставки идентичны.

---

## 3. Impact / stale

Механизма invalidation классификации событий в коде **не было**.

Минимальная мера в скрипте: при наличии `EventImpact` для изменённого события — пометить  
`score_breakdown_json.event_classification_stale=true` и note в `claims_json` **без** пересчёта score.

Факт на стенде: у **28** изменённых live-событий **0** связанных `event_impacts`  
(всего в БД 1 impact — на другое событие). Пометок stale: **0**.

Массовый `recompute` **не** запускался. Telegram/LLM **не** вызывались.

Предложение на будущее (не сделано): явный статус/флаг `classification_stale` в API ленты «для вас», чтобы UI не показывал устаревший score как актуальный; точечный recompute по кнопке/для одной компании.

---

## 4. Регрессии

| Проверка | Результат |
|----------|-----------|
| `pytest` heuristic + impact/finance/telegram/assistant-without-impact (чистый env) | **57 passed** |
| Frontend `npm run build` | **ok** |
| Повторный apply | no-op |
| null severity → не 50/60 | выставка и MIACR: `severity=null`, label «Важность не определена» |
| severity=0 | в БД нулей нет; контракт/тесты `test_rate_scenario_basis` (0 не становится 50) — pass |
| Сохранение ключевой ставки / FX | своп юань: `macro` / `market` / **60** (не risk) |
| Реальные меры / risk | среди 28 не было enacted export ban; investigation (Philippines pork) → `geopolitics` / **neutral** / null (мера не введена) |
| Live LLM | не вызывался |

---

## 5. HTTP API `:8020`

| Событие | category_label | event_type_label | severity_label |
|---------|----------------|------------------|----------------|
| Выставка ФТС (`…57984a74…`) | **Прочее** | **Нейтрально** | **Важность не определена** |
| Philippines safeguard investigation | Геополитика | Нейтрально | Важность не определена |
| Вмененная ставка FX-свопа | Макроэкономика | Рынок | Средняя важность |
| Ставки MIACR | Прочее | Нейтрально | Важность не определена |

Публичная карточка по-прежнему отдаёт `severity_label` без сырого числа (как и раньше); в БД у FX-свопа `severity=60.0`, у выставки `NULL`.

`/api/v1/public/trending` и `/api/v1/public/categories` — 200.

---

## 6. Итог

Live-классификация основного стенда приведена к **heuristic_v2**; backup сохранён; история сообщений/решений и Telegram не затронуты; повторный прогон безопасен.