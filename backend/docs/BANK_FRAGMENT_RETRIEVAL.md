# Bank fragment retrieval (Этап 2.11)

Дата: 2026-10-21  
Внутренний read-only поиск банковских фрагментов **без LLM**, без публичного API, без embeddings и без векторной инфраструктуры.

Рабочая БД, `.env`, API, UI, ассистент **не** менялись.  
OCR / браузер / CDP / скриншоты / commit/push не выполнялись.  
Smoke — только чтение копии БД этапа 2.10.

## Назначение

По тексту вопроса/события найти подходящие фрагменты и вернуть **проверяемые основания с источниками**.  
Сервис **не** генерирует ответ и **не** интегрируется с ассистентом/UI.

## Код

| Файл | Назначение |
|------|------------|
| `app/services/bank_materials/retrieval.py` | `retrieve_bank_fragments`, лексический score, даты, provenance |
| `app/services/bank_materials/fragment_revision.py` | latest revision per `(ocr_run_id, stable_key)` + eligibility |
| `app/services/bank_materials/eligibility.py` | `eligible_search` / `eligible_ai_evidence` / `eligible_exact_quote` |
| `tests/test_bank_fragment_retrieval.py` | синтетические регрессии |
| `data/bank_materials/verification/run_retrieval_smoke.py` | read-only smoke на копии 2.10 |
| `data/bank_materials/verification/retrieval_smoke.json` | зафиксированный отчёт smoke |

Экспорт: `retrieve_bank_fragments`, `FragmentHit`, `RetrievalResult` из `app.services.bank_materials`.

## Контракт сервиса

```python
retrieve_bank_fragments(
    session,                    # SQLAlchemy Session (read-only expectation)
    *,
    query: str,                 # ≤ 2000 символов
    ocr_run_ids: list[str],     # обязательный явный scope; пустой → RetrievalError
    mode: "candidates" | "evidence",
    limit: int = 10,            # верхняя граница MAX_LIMIT=50
    as_of_date: date | None = None,
) -> RetrievalResult
```

### Область поиска

- Набор `ocr_run_ids` задаёт **вызывающий код**, не конечный пользователь напрямую.
- Если scope не задан — **ошибка**; корпус целиком не открывается.
- Актуальная редакция **не** выбирается по `max(created_at)`.
- Для каждого `(ocr_run_id, stable_key)` берётся **последняя revision**, затем eligibility.
- Если последняя revision запрещена — **нет fallback** к старой разрешённой.

### Режимы

| | `candidates` | `evidence` |
|---|---|---|
| Eligibility | только `eligible_search` | только `eligible_ai_evidence` |
| Неподтверждённые | допускаются, `text_kind=untrusted_candidate`, `insufficient_verification=true` | **никогда** не попадают в выдачу |
| `exact_quote` | из transcript при допуске; иначе untrusted | только при `eligible_exact_quote` + `verified_transcript` |
| `summary` | summary как summary | summary как summary, **без** подмены цитаты |
| Пустой результат | норма | норма |

Пустая выдача **не** добивается нерелевантными материалами.

### Результат (`FragmentHit`)

- ID: `document_id`, `document_file_id`, `ocr_run_id`, `fragment_id`
- Версия: `stable_key`, `revision`
- Документ: `document_slug`, `document_title`, дата + `publication_date_precision`, `publication_date_display`
- Время/stance: `staleness_note`, `is_current_stance` **как в БД** (без повышения статуса)
- Страницы/области: `page_number`, `regions[]` (bbox, `region_type`, …)
- `content_type`: fact / forecast / interpretation (+ status)
- Текст: `text`, `text_kind` ∈ {`exact_quote`, `summary`, `untrusted_candidate`}, `kind`
- Eligibility + `eligibility_reasons`
- Provenance: `pdf_sha256`, `ocr_fingerprint_hash`
- Роль vs QA: `source_role`, `source_role_meaning`, `qa_method`, `qa_performed_by`, `qa_performed_at`
- Релевантность: `relevance_score` (**не** confidence), `match_reasons`, `date_gate_reasons`

**Не** возвращаются: абсолютные пути, storage keys, выдуманные публичные URL.

### source_role vs QA

После этапа 2.10 QA-правки пишут `source_role=bank_material_qa_revision`.  
Это **не** стирает смысл источника: сведения о решении ЦБ прочитаны **в материале банка**, а не получены напрямую от ЦБ.

В выдаче:

- `source_role` — как в БД (без молчаливой переписи);
- `source_role_meaning` — пояснение роли;
- `qa_method` — из `ocr_correction_json.qa_provenance.method` (если есть), отдельно от роли.

## Алгоритм поиска и ранжирования

Детерминированный лексический поиск для небольшого корпуса.

1. Нормализация query: lower, `ё→е`, токены `[0-9a-zа-яё]+`, стоп-слова.
2. Для каждого run → latest fragments → eligibility → date gate → lexical score.
3. Score > 0 обязателен; title-only match **не** квалифицирует фрагмент.
4. Режим `evidence`: дополнительно `score >= MIN_EVIDENCE_SCORE` (3.0 — минимум
   одно exact-token совпадение). Одиночный слабый stem (2.0) не становится AI-evidence
   (этап 6.7: ложный hit «спрос» gold↔consumption).
5. Сортировка стабильна: `(-score, stable_key, fragment_id)`.
6. Обрезка по `limit`.

### Веса (технические, не confidence)

| Сигнал | Примерный вклад |
|--------|-----------------|
| exact token в тексте фрагмента | +3 |
| stem-совпадение | +2 |
| synonym-группа (явный словарь) | +1.5 за токен |
| topic_overlap (≥2 терминов группы в тексте) | +1 … |
| title_support | +0.3× только если уже есть fragment signal |
| content_type boost | небольшой, только при score>0 |

### Явный словарь синонимов

`TOPIC_SYNONYMS` в `retrieval.py` — маленькие группы `key_rate` и `rate_forecast`.  
Ультра-общие токены (`банк`, `цб`) **не** используются как synonym-bridges.

### Ограничения простого поиска

Это **не** понимание смысла:

- нет семантики/эмбеддингов/LLM;
- морфология — лёгкий суффиксный trim, не полноценный стеммер;
- совпадение по «ставке» может подтянуть соседние фрагменты того же документа;
- синонимы тематические и неполные;
- порядок стабилен при одинаковых входах, но score — эвристика ранжирования, не вероятность правильности.

## Политика дат и версий

### `as_of_date`

- **day**: `publication_date ≤ as_of`; иначе отказ.
- **month**: если месяц целиком после `as_of` — отказ; если месяц **пересекает** `as_of` (день неизвестен) — **evidence отказ**, candidates с причиной `month_day_unknown_overlaps_as_of`.
- **unknown**: evidence отказ; candidates с `publication_date_unknown`.
- Публикации строго после `as_of` не возвращаются как evidence.

### Stance / freshness

- Старый материал **не** становится текущей позицией банка.
- Произвольный единый TTL по всем темам **не** применяется.
- Возвращаются `staleness_note` и `is_current_stance` из документа без повышения статуса.

### Версии

1. Latest revision per `(run, stable_key)`.
2. Eligibility на этой revision.
3. Нет fallback к старой eligible revision.

## Синтетические тесты

```bash
python -m pytest tests/test_bank_fragment_retrieval.py -q
```

**6 passed.** Покрыто:

- релевантный vs нерелевантный запрос;
- режимы `candidates` / `evidence`;
- запрет fallback к старой revision;
- отсутствие дублей ревизий одного `stable_key`;
- verified summary не становится `exact_quote`;
- публикация после `as_of_date`;
- month / unknown date gates;
- исторический материал не помечается текущим;
- сохранность provenance (PDF SHA, OCR fingerprint, QA method vs source_role);
- обязательный scope `ocr_run_ids` + `limit`;
- стабильность порядка;
- отсутствие записи в БД (count before/after).

## Реальный smoke (копия 2.10)

БД (только чтение):

`data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db`

```bash
python data/bank_materials/verification/run_retrieval_smoke.py
```

Отчёт: `data/bank_materials/verification/retrieval_smoke.json`.

- `ocr_run_ids`: 9 run ID, явно взятые из БД и переданные сервису.
- Policy Rate run: `7d64e39e-0ff5-450c-8a01-c44f678da871`.
- `as_of_date=2026-10-21`.
- `read_only_unchanged=true` (fragments=24, documents=9 до и после).

### Результаты (evidence)

| Запрос | Hits | Кратко |
|--------|------|--------|
| «Что банк пишет о сохранении ключевой ставки?» | 3 | Все из Policy Rate @ revision **2** (QA): `policy_rate_bank_forecast` (score 10.6), `policy_rate_cb_decision` (7.75), `policy_rate_rhetoric` (7.35). `source_role=bank_material_qa_revision`, `qa_method=ai_vision_over_local_page_png`, `is_current_stance=false`. |
| «Какой прогноз банка по ставке на конец 2027 года?» | 3 | Лидер — `policy_rate_bank_forecast` (13.8, topic_overlap key_rate + rate_forecast). Decision/rhetoric слабее (~4) — лексический хвост по «ставке», не отдельный «прогноз 2027». |
| «Какая погода в Антарктиде завтра?» | 0 | `empty_reason=no_matching_fragments_in_scope` |

Алгоритм **не** подгонялся под конкретные stable_key / demo-новости.  
Не ожидается автоматически ровно три фрагмента на любой вопрос.

### Candidates (тот же rate_keep)

6 hits: Policy Rate rev2 + навигационные untrusted из FI Strategy / Bond Brief (`insufficient_verification=true`). В evidence эти untrusted **не** попадают.

## Что намеренно не сделано

- генерация ответа / интеграция с ассистентом;
- публичный API / UI;
- embeddings / внешние search API / тяжёлые NLP-зависимости;
- запись в рабочую БД;
- выбор актуальной редакции по `created_at`;
- авто-scope на весь корпус без `ocr_run_ids`.

## Остановка

Этап **2.11** завершён. Следующие этапы — отдельно.
