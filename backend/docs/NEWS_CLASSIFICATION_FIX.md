# Исправление классификации новостей (heuristic enrichment)

Дата: 2026-10-24

Связанные: `PRIMARY_SOURCE_PUBLICATION.md`, `ASSISTANT_MANUAL_CONTEXT_FIX.md`.

---

## 1. Диагноз `evt_live_57984a7413fbe2ec94f22f10`

| Поле | Было |
|------|------|
| category | `macro` |
| event_type | `risk` |
| severity | `60` |
| currencies | `RUB` |

**Источник:** не «официальность ФТС» и не данные RSS-полей severity, а **ложное срабатывание** `heuristic_enrich` в `app/services/ingestion/enrich.py`:

- подстрока **`ставк` внутри слова `выставки`** → ветка «ключевая ставка / macro / 60 / RUB»;
- дополнительно **`ес` как подстрока** («честь», «интерес»…) давала ложную страну «ЕС».

Официальный `publish_reason=official_source` только разрешает публикацию; **не задаёт** negativity / economic importance.

Повторная классификация `heuristic_v2` на том же тексте: `other` / `neutral` / `severity=null` (`cultural_or_ceremonial_notice`).

---

## 2. Общее правило (не патч заголовка)

Разделены:

1. **факт публикации** (источник, дата, текст);
2. **бизнес-тематика** (category, в т.ч. `other`);
3. **негативность / направление** (`event_type`: `risk` \| `opportunity` \| `market` \| **`neutral`**);
4. **значимость** (`severity: float | null` — `null` = не установлено, **не** фиктивный 0);
5. **релевантность компании** — отдельно (twin / impact), не из official flag.

Контракт (минимально):

- `EventCategory` + `other`;
- `EventType` + `neutral`;
- `events.severity` **nullable** (миграция `009_event_severity_nullable.py`);
- публичные labels: «Прочее», «Нейтрально», «Важность не определена»;
- impact: при `severity is None` вес severity **опускается**, не подставляется 0 как «известная серьёзность».

Маatching: границы слова + запрет префиксов (`вы`+`ставк`, `экс`+`порт`).

«Таможня» сама по себе ≠ risk; «ставка» в «выставке» ≠ key rate.

---

## 3. Fixtures (`tests/test_news_classification_heuristic.py`)

| Кейс | Ожидание |
|------|----------|
| Культурная публикация ФТС / выставки | other / neutral / null |
| Вступившее экспортное ограничение / санкции | geopolitics / risk / 75 |
| Расследование без меры (safeguard investigation) | neutral / null |
| Сохранение ключевой ставки ЦБ | macro / severity 60 |
| Нейтральная статистика (Росстат) | other / neutral / null |

Scripted-тесты **не** доказывают качество live-модели.

---

## 4. Ассистент

- В model projection события **убраны** category / event_type / severity / id (не для final.content).
- Правила: для очевидно нерелевантной новости — **короткий** ответ (вывод, основание по профилю, действие да/нет, источник); без лишних чувствительных запросов; без внутренних taxonomy/payload.
- Live LLM на этапе не вызывался.

---

## 5. Доля выпуска 24%

| | |
|--|--|
| Где | `company_nodes.output_share_percent = 24` у линии «Большая» (упк) |
| Происхождение | UI `CompanySetupPage` раньше подставлял default **`'24'`**, если доля не задана |
| Действие | Пользовательскую БД **не** переписывали. Default убран (`''`). В manual-context: `output_share_percent_provenance=stored_on_node_origin_unverified` + interpretation limit — не называть подтверждённым пользователем без доказательства |

---

## 6. Dry-run на копии БД

- Копия: `data/competition_stand/reclassify_dry_run/stand_reclassify_*.db`
- Отчёт: `data/competition_stand/reclassify_dry_run/reclassify_dry_run_report.json`
- На копии применено: **28** событий сменили класс (выставка → other/neutral/null).
- **Основной** `real_news_613/stand.db`: только миграция `009` (nullable severity); **классификации live-событий не менялись** в этом этапе; сообщения / решения / Telegram / mass impact — не трогались.

Скрипт: `scripts/dry_run_reclassify_events.py` (`--apply-on-copy` пишет только в копию).

---

## 7. Frontend

- Чипы risk только для `event_type=risk`; neutral без `chip-risk`.
- `npm run build` — успешно после правок Markdown types.

---

## 8. Применение к основному стенду

Выполнено **2026-10-24**: см. [`NEWS_RECLASSIFICATION_APPLIED.md`](NEWS_RECLASSIFICATION_APPLIED.md)  
(backup → 28 событий → heuristic_v2; Impact на изменённых не было; без Telegram / mass recompute / LLM).
