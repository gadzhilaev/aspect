# Bank materials model (Этап 2.4 → уточнения 2.5)

Дата: 2026-10-21 (уточнения схемы: 2026-10-21, этап 2.5)  
Статус документации: согласована со схемой БД этапа 2.5.  
Импортёр, поиск, RAG, API и UI **не** входят в 2.5.

Опирается на:

- `docs/BANK_OCR_CORPUS.md`, `docs/BANK_OCR_PILOT.md`;
- фактические `data/bank_materials/ocr/_corpus_manifest.json`, per-doc `manifest.json`, `page_*_meta.json`, `fragments.json`;
- существующие источники новостей: `raw_news_items`, `event_sources` (отдельный контур; не смешивать с bank materials).

---

## 1. Минимальная схема (6 таблиц)

Цель: логический документ → неизменяемый PDF → версия OCR → страницы/области → фрагменты для поиска/цитирования.  
Не универсальный DMS и не дублирование `events` / `raw_news_items`.

Связь с новостями в будущем — опциональная ссылка «этот фрагмент использован как evidence для event/impact», **не** публикация PDF в `EventSource.url` и не попадание в public/news.

```
bank_documents
    └── bank_document_files          (immutable PDF by SHA-256)
            └── bank_ocr_runs        (one OCR fingerprint / params version)
                    └── bank_ocr_pages
                    └── bank_fragments
                            └── bank_fragment_regions
```

Хранение байтов — по `storage_key` (объектное/файловое хранилище). В API — только opaque id / signed URL, **не** абсолютные пути диска.

### 1.1. `bank_documents`

Логический документ (серия/«этот note»), без байтов PDF.

| Поле | Тип | Nullable | Описание |
|------|-----|----------|----------|
| `id` | `UUID` / `CHAR(36)` | NO | PK |
| `slug` | `VARCHAR(255)` | NO | Стабильный ключ каталога, напр. stem файла; **не** ключ идемпотентности содержимого |
| `title` | `VARCHAR(1024)` | YES | Подтверждённое или рабочее название |
| `title_status` | `VARCHAR(32)` | NO | `confirmed` \| `unknown` \| `filename_hint` |
| `publication_date` | `DATE` | YES | Только при `publication_date_precision = day` |
| `publication_year` | `SMALLINT` | YES | При `day` или `month` |
| `publication_month` | `SMALLINT` | YES | 1–12; при `month` (и можно при `day`) |
| `publication_date_precision` | `VARCHAR(16)` | NO | `day` \| `month` \| `unknown` |
| `publication_date_display` | `VARCHAR(255)` | YES | Как на странице, напр. «АВГУСТ 2026», «11 сентября 2026 г.» |
| `period_covered` | `TEXT` | YES | Рассматриваемый период **отдельно** от даты публикации |
| `period_covered_status` | `VARCHAR(32)` | NO | `confirmed` \| `unknown` |
| `topics_json` | `JSON` | NO | Список строк; default `[]` |
| `topics_status` | `VARCHAR(32)` | NO | `confirmed` \| `unknown` |
| `staleness_note` | `TEXT` | YES | Напр. материал 2021 ≠ текущая позиция |
| `is_current_stance` | `BOOLEAN` | NO | Default `false`; выставлять только явно, не по давности автоматом |
| `document_visual_status` | `VARCHAR(32)` | NO | Как в корпусе: `unverified` \| `partial_spot_check` \| … |
| `created_at` | `TIMESTAMPTZ` | NO | |
| `updated_at` | `TIMESTAMPTZ` | NO | |

**Unique / indexes**

- `UNIQUE (slug)`
- `INDEX (publication_year, publication_month)`
- `INDEX (document_visual_status)`

**Правила дат**

- `precision = day` → обязательны `publication_date`, year, month; день из содержимого страницы, не из PDF metadata.
- `precision = month` → `publication_date` **NULL**; заполнены year+month. **Запрещено** писать «1 августа» для «август 2026».
- `precision = unknown` → date/year/month NULL (или year без month только если когда-нибудь явно подтвердят год без месяца — в MVP не использовать без подтверждения).
- `PDF CreationDate` / `/ModDate` **не** мапятся в эти поля (в корпусе ~2026-09-28 — дата экспорта).

Документы **не** сливаются по похожему `title` / `slug`. Похожие названия = разные `bank_documents`, пока не доказано иное человеком.

### 1.2. `bank_document_files`

Неизменяемая версия исходного PDF.

| Поле | Тип | Nullable | Описание |
|------|-----|----------|----------|
| `id` | `UUID` | NO | PK |
| `document_id` | `UUID` | NO | FK → `bank_documents.id` |
| `sha256` | `CHAR(64)` | NO | Хеш содержимого PDF |
| `original_filename` | `VARCHAR(512)` | NO | Имя файла при загрузке (подсказка) |
| `page_count` | `INT` | NO | |
| `byte_size` | `BIGINT` | NO | |
| `storage_key` | `VARCHAR(1024)` | NO | Ключ в storage (не filesystem path для API) |
| `pdf_producer` | `VARCHAR(255)` | YES | Metadata producer, информационно |
| `pdf_creation_date` | `TIMESTAMPTZ` | YES | Metadata only; **не** publication |
| `revision_label` | `VARCHAR(128)` | YES | Человеческая метка редакции, если известна |
| `supersedes_file_id` | `UUID` | YES | FK → `bank_document_files.id` предыдущей редакции |
| `imported_at` | `TIMESTAMPTZ` | NO | |

**Unique / indexes**

- `UNIQUE (sha256)` — повторная загрузка тех же байтов не создаёт строку
- `INDEX (document_id)`
- `INDEX (supersedes_file_id)`

**Новая редакция документа**

1. Новый PDF с **другим** `sha256` → новая строка `bank_document_files`.
2. Обычно тот же `document_id` (логическая серия), если редакция того же note; иначе новый `bank_documents`.
3. `supersedes_file_id` указывает на предыдущий file; старый file и его OCR/фрагменты **остаются**.
4. «Активная» редакция для UI — отдельное поле на `bank_documents` (опционально позже: `active_file_id`) или выбор max(`imported_at`) с явным флагом; в MVP достаточно `supersedes` + явный `active_file_id` при появлении API.
5. Похожее имя файла / title **не** достаточно для привязки к тому же `document_id`.

### 1.3. `bank_ocr_runs`

Результат конкретной версии OCR над одним file.

| Поле | Тип | Nullable | Описание |
|------|-----|----------|----------|
| `id` | `UUID` | NO | PK |
| `document_file_id` | `UUID` | NO | FK → `bank_document_files.id` |
| `fingerprint_hash` | `CHAR(64)` | NO | SHA-256 канонического JSON fingerprint |
| `schema_version` | `INT` | NO | Как в манифесте (сейчас 2) |
| `tesseract_version_line` | `VARCHAR(128)` | NO | |
| `lang` | `VARCHAR(32)` | NO | напр. `rus+eng` |
| `psm_default` | `SMALLINT` | NO | Primary PSM (3) |
| `preserve_interword_spaces` | `BOOLEAN` | NO | |
| `eng_traineddata_sha256` | `CHAR(64)` | NO | |
| `rus_traineddata_sha256` | `CHAR(64)` | NO | |
| `params_json` | `JSON` | NO | Полный fingerprint без абсолютных путей host |
| `processing_status` | `VARCHAR(32)` | NO | `complete` \| `incomplete` |
| `pages_ok_json` | `JSON` | NO | |
| `pages_failed_json` | `JSON` | NO | |
| `artifact_root_key` | `VARCHAR(1024)` | NO | Storage prefix для page PNG/txt/tsv (не API path) |
| `created_at` | `TIMESTAMPTZ` | NO | |

**Unique / indexes**

- `UNIQUE (document_file_id, fingerprint_hash)` — тот же PDF + те же OCR-параметры → один run
- `INDEX (processing_status)`

Канонический fingerprint (для hash) включает: `source_sha256`, version line, lang, psm, preserve flag, eng/rus traineddata hashes, schema_version. **Не** включать абсолютный `tesseract_binary` / host `tessdata_dir` (в текущих артефактах они есть — при импорте нормализовать).

Новый OCR (другие params / языки) → **новый** `bank_ocr_runs`. Старый run и его фрагменты не удаляются и не переписываются.

### 1.4. `bank_ocr_pages`

Страница PDF в рамках одного OCR run.

| Поле | Тип | Nullable | Описание |
|------|-----|----------|----------|
| `id` | `UUID` | NO | PK |
| `ocr_run_id` | `UUID` | NO | FK → `bank_ocr_runs.id` |
| `page_number` | `INT` | NO | 1-based PDF page |
| `processing_status` | `VARCHAR(32)` | NO | `ok` \| `failed` \| … |
| `width` | `INT` | YES | px изображения OCR |
| `height` | `INT` | YES | |
| `image_storage_key` | `VARCHAR(1024)` | YES | PNG страницы |
| `raw_text_storage_key` | `VARCHAR(1024)` | YES | |
| `cleaned_text_storage_key` | `VARCHAR(1024)` | YES | |
| `tsv_storage_key` | `VARCHAR(1024)` | YES | |
| `words_storage_key` | `VARCHAR(1024)` | YES | |
| `word_count` | `INT` | YES | |
| `mean_confidence` | `FLOAT` | YES | Технический OCR conf |
| `median_confidence` | `FLOAT` | YES | |
| `psm_used` | `SMALLINT` | YES | Фактический PSM (fallback) |
| `visual_verification_status` | `VARCHAR(32)` | NO | `unverified` \| `verified_spot_check` \| … |
| `content_regions_json` | `JSON` | NO | Типы областей: prose/table/chart/contacts_disclaimer/mixed/unverified + status |
| `visual_checks_json` | `JSON` | NO | title/date/period/takeaway statuses |
| `error` | `TEXT` | YES | |

**Unique / indexes**

- `UNIQUE (ocr_run_id, page_number)`
- `INDEX (visual_verification_status)`
- `INDEX (processing_status)`

Тексты страниц **не** дублировать целиком в БД, если лежат в storage; для поиска MVP допустим отдельный индекс по фрагментам (см. ниже), не по всей странице.

`mean_confidence` **не** повышает eligibility цитаты.

Spot-check страницы (`verified_spot_check`) **не** подтверждает все фрагменты на странице.

### 1.5. `bank_fragments`

Единица поиска / evidence / цитирования. Одна логическая цитата или пересказ **в конкретной ревизии**.

| Поле | Тип | Nullable | Описание |
|------|-----|----------|----------|
| `id` | `UUID` | NO | PK; новый id на каждую ревизию |
| `ocr_run_id` | `UUID` | NO | FK → `bank_ocr_runs.id` |
| `document_file_id` | `UUID` | NO | Денормализация; composite FK с `document_id` и с run |
| `document_id` | `UUID` | NO | Денормализация; согласована с file через composite FK |
| `stable_key` | `VARCHAR(128)` | NO | Логический фрагмент **внутри OCR run** (напр. `policy_rate_cb_decision`) |
| `revision` | `INT` | NO | Версия текста ≥ 1; исправление → `revision+1`, новый `id` |
| `kind` | `VARCHAR(32)` | NO | `exact_quote` \| `summary` |
| `primary_region_type` | `VARCHAR(32)` | NO | `prose` \| `table` \| `chart` \| `contacts_disclaimer` \| `mixed` \| `unverified` — для eligibility |
| `content_type` | `VARCHAR(32)` | YES | `fact` \| `forecast` \| `interpretation`; NULL если не классифицирован |
| `content_type_status` | `VARCHAR(32)` | NO | `confirmed` \| `unconfirmed` \| `unknown` |
| `page_number` | `INT` | NO | Якорь; composite FK → `bank_ocr_pages(ocr_run_id, page_number)` |
| `ocr_text` | `TEXT` | YES | Raw/исходный OCR сниппет для этого фрагмента |
| `cleaned_text` | `TEXT` | YES | Safe whitespace cleanup, если отличается |
| `verified_transcript` | `TEXT` | YES | Проверенная транскрипция (для `exact_quote`) |
| `summary_text` | `TEXT` | YES | Пересказ (для `kind=summary`); **не** exact quote |
| `verification_status` | `VARCHAR(32)` | NO | `verified` \| `unverified` \| `needs_reverification` |
| `ocr_correction_json` | `JSON` | YES | `{from, to, basis}` при правке после visual QA |
| `source_role` | `VARCHAR(128)` | YES | напр. `bank_material_reporting_cb_decision` |
| `notes` | `TEXT` | YES | |
| `supersedes_fragment_id` | `UUID` | YES | Предыдущая ревизия того же `stable_key` в том же OCR run |
| `created_at` | `TIMESTAMPTZ` | NO | |

**Eligible flags не хранятся** в строке. Источник истины — чистая функция `compute_fragment_eligibility` (§4). Сохранение `eligible_*` запрещено, чтобы не расходиться с политикой.

**Unique / indexes**

- `UNIQUE (ocr_run_id, stable_key, revision)` — повтор той же версии не создаёт дубликат; новая ревизия — новая строка
- `UNIQUE (id, ocr_run_id, stable_key)` — для composite FK `supersedes`
- `INDEX (document_id)`
- `INDEX (verification_status)`
- `INDEX (document_file_id, page_number)`
- `INDEX (ocr_run_id, stable_key)`

**Версии фрагмента**

- `stable_key` = логический фрагмент внутри одного `ocr_run`.
- Исправление цитаты: **новый** `id`, `revision = N+1`, `supersedes_fragment_id` → предыдущая ревизия; старый текст **не** UPDATE.
- Повторный импорт той же `(ocr_run, stable_key, revision)` → no-op / upsert без дубликата.

**`supersedes_fragment_id` — что проверяет БД vs приложение**

| Проверка | Где |
|----------|-----|
| Целевой fragment существует | FK |
| Не self-reference (`id != supersedes_fragment_id`) | CHECK |
| Тот же `ocr_run_id` и тот же `stable_key` | composite FK `(supersedes_fragment_id, ocr_run_id, stable_key)` → `(id, ocr_run_id, stable_key)` |
| `revision` строго больше superseded; цепочка без циклов; монотонность | **прикладная логика** / импортёр |
| Не ссылаться на fragment другого документа/run | обеспечено composite FK (другой run не пройдёт) |

**Разделение текстов (обязательно)**

| Поле | Назначение |
|------|------------|
| `ocr_text` | Как распознал OCR |
| `cleaned_text` | Только безопасная нормализация пробелов |
| `verified_transcript` | После visual QA; может отличаться от OCR |
| `summary_text` | Пересказ; **никогда** не отдавать как точную цитату |

Не хранить PDF/PNG в строке фрагмента — только FK на file/run/page + regions.

**Исправление цитаты**

- Не `UPDATE` verified_transcript у фрагмента, на который уже ссылались ответы.
- Новая строка с новым `id`, `supersedes_fragment_id` → старый id; eligibility старого можно снять (`eligible_*=false`), но запись остаётся для аудита.

**`needs_reverification`**

- `verification_status = needs_reverification` → все `eligible_ai_evidence` / `eligible_exact_quote` = false; search — по политике MVP можно оставить true только как «наводку», либо false (рекомендация MVP: search true с пометкой «untrusted», AI/quote false).

### 1.6. `bank_fragment_regions`

Несколько разнесённых областей одного фрагмента.

| Поле | Тип | Nullable | Описание |
|------|-----|----------|----------|
| `id` | `UUID` | NO | PK |
| `fragment_id` | `UUID` | NO | FK → `bank_fragments.id` |
| `ocr_run_id` | `UUID` | NO | Денормализация; composite FK с fragment и со страницей |
| `page_number` | `INT` | NO | Должна существовать страница того же OCR run |
| `sort_order` | `INT` | NO | Порядок областей |
| `region_type` | `VARCHAR(32)` | NO | Тот же enum, что `primary_region_type` |
| `bbox_left` | `INT` | YES | px; NULL если область ещё не привязана |
| `bbox_top` | `INT` | YES | |
| `bbox_width` | `INT` | YES | |
| `bbox_height` | `INT` | YES | |
| `coord_space` | `VARCHAR(32)` | NO | Default `page_image_px` |
| `note` | `TEXT` | YES | |

**Unique / indexes**

- `UNIQUE (fragment_id, sort_order)`
- `INDEX (fragment_id)`
- composite FK `(fragment_id, ocr_run_id)` → `bank_fragments(id, ocr_run_id)`
- composite FK `(ocr_run_id, page_number)` → `bank_ocr_pages(ocr_run_id, page_number)`

**BBox CHECK (БД):** либо все четыре NULL, либо все NOT NULL; left/top ≥ 0; width/height > 0.  
**Попадание bbox в width/height страницы** CHECK другой таблицы не выражает — проверка **будущего валидатора импорта**, не заявлена как DB CHECK.

Запрещено склеивать несколько абзацев в один bbox «на весь текст» — несколько строк regions.

### 1.7. Согласованность происхождения (composite FK)

| Связь | Как |
|-------|-----|
| File принадлежит document | `bank_document_files.document_id` FK |
| `supersedes_file_id` только внутри того же document | composite FK `(document_id, supersedes_file_id)` → `(document_id, id)`; + CHECK не self |
| Run принадлежит file | `document_file_id` FK; `UNIQUE(id, document_file_id)` |
| Page принадлежит run | `UNIQUE(ocr_run_id, page_number)` |
| Fragment → page того же run | FK `(ocr_run_id, page_number)` → pages |
| Fragment → file/document той же цепочки | FK `(ocr_run_id, document_file_id)` → runs; FK `(document_file_id, document_id)` → files |
| Region → page того же run, что fragment | см. §1.6 |

`visual_verification_status` страницы **не** делает fragments страницы verified.

---

## 2. Версии, происхождение, идемпотентность

У каждого фрагмента восстанавливается цепочка:

`bank_fragments` → `ocr_run` (fingerprint) → `document_file` (`sha256`) → `document`  
+ `page_number` + `bank_fragment_regions` (координаты).

| Событие | Поведение |
|---------|-----------|
| Повторный импорт тех же PDF bytes + того же OCR fingerprint + тех же `(stable_key, revision)` | Upsert / no-op; дубликатов нет |
| Новый PDF (другой SHA) | Новый `bank_document_files`; старые ответы ссылаются на старый file id |
| Новый OCR fingerprint | Новый `bank_ocr_runs`; старые fragments остаются |
| Исправленная цитата | Новый fragment (`revision+1`) + `supersedes_fragment_id`; старый текст сохраняется |
| Смена params при OCR на диске | Как в 2.3: archive + `needs_reverification`; в БД — новый run или статус fragments |

Не объединять документы по похожему названию.  
Не считать `slug` из filename доказательством тождества редакций — только `sha256` файла и явная связь `supersedes_file_id` / один `document_id`.

Отличие от новостей:

| Контур | Идемпотентность сегодня |
|--------|-------------------------|
| `raw_news_items` | `(provider, external_id)`, `canonical_url` |
| Bank materials | `sha256` файла + `(ocr_run, stable_key, revision)` фрагмента |

Bank PDF **не** класть в `event_sources.url` как публичную ссылку на файл с диска.

---

## 3. Даты (сводка)

| Случай из корпуса | precision | Хранение |
|-------------------|-----------|----------|
| Policy Rate «11 сентября 2026 г.» | `day` | `publication_date=2026-09-11` |
| Gold «АВГУСТ 2026» | `month` | year=2026, month=8, `publication_date=NULL` |
| Нет даты на странице | `unknown` | всё NULL + display null |
| Steels «15 April 2021» | `day` | date=2021-04-15; `staleness_note` обязателен; `is_current_stance=false` |

`period_covered` всегда отдельно (напр. «прогнозы до конца 2026–2027» vs дата note).

Исторический документ может быть источником факта «банк писал X в 2021», но **не** автоматически «текущая позиция банка».

---

## 4. Правила использования текста (MVP, консервативно)

Три флага **вычисляются** функцией `app.services.bank_materials.eligibility.compute_fragment_eligibility` (без БД и без LLM). Колонок `eligible_*` в таблице **нет**.

| Флаг | Смысл |
|------|--------|
| `eligible_search` | Можно искать кандидатов (навести на страницу/область) |
| `eligible_ai_evidence` | Можно передать модели как основание ответа |
| `eligible_exact_quote` | Можно показать пользователю как точную цитату банка |

Вход функции опирается на поля фрагмента (`verification_status`, `kind`, `primary_region_type`, `content_type` / `content_type_status`, тексты).  
`page_visual_verification_status` и OCR confidence **игнорируются** (не повышают допуск). Spot-check страницы ≠ verified фрагменты.

### 4.1. Таблица eligibility

| Условие | search | AI evidence | exact quote |
|---------|:------:|:-----------:|:-----------:|
| `primary_region_type=prose`, `unverified` или `needs_reverification` | ✅ | ❌ | ❌ |
| `verified` + `prose` + `kind=exact_quote` + непустой `verified_transcript` + `content_type_status=confirmed` | ✅ | ✅ | ✅ |
| `verified` + `prose` + `kind=summary` + непустой `summary_text` + `content_type_status=confirmed` | ✅ | ✅ (только как пересказ) | ❌ |
| `table` / `chart` / `contacts_disclaimer` / `mixed` / неизвестный `primary_region_type` | ❌ | ❌ | ❌ |
| `content_type_status` ≠ `confirmed` (для AI/quote путей) | ✅* если prose+searchable status | ❌ | ❌ |
| Противоречивые kind/тексты (exact без transcript, summary без summary_text, оба kind-текста конфликтуют) | ✅* только если prose и status допускает search | ❌ | ❌ |
| Высокий OCR confidence / spot-check страницы | не влияет | не влияет | не влияет |

\* Search для prose-кандидатов при `unverified` / `needs_reverification` / неподтверждённом content_type — да; table/chart/disclaimer/mixed — нет.

**Если нет подходящего verified фрагмента:** ответ явно сообщает об отсутствии проверенной цитаты — **без** выдуманной позиции банка.

`document_visual_status=partial_spot_check` **не** делает все fragments eligible.

---

## 5. Цитата vs пересказ vs OCR

| Вид | Поля | UI / API |
|-----|------|----------|
| Raw OCR | `ocr_text` | Отладка / сверка; не «цитата банка» |
| Cleaned | `cleaned_text` | То же |
| Exact quote | `verified_transcript` + `kind=exact_quote` | Единственный текст для «цитата» |
| Summary | `summary_text` + `kind=summary` | Явная метка «пересказ» |

`fact` / `forecast` / `interpretation` — разные `content_type`; непроверенная классификация → `content_type_status=unconfirmed`, не выдавать как установленную.

Несколько областей → несколько `bank_fragment_regions`, не один bbox.

Происхождение исправления: `ocr_correction_json` + неизменный `ocr_text` + новый transcript; при смене transcript после публикации ответов — новая версия fragment (`supersedes`).

Факт о решении ЦБ, прочитанный в материале банка → `source_role` указывает bank material; не подставлять неоткрытую ссылку ЦБ как проверенный первоисточник (как в пилоте Policy Rate).

---

## 6. Доступ и выдача

### 6.1. Что не делать

- Не публиковать originals / OCR через `public/`, статику сайта или public news feed.
- Не отдавать в API абсолютные пути (`C:\…`, `/var/…`).
- Не дублировать PDF и page images в каждой строке fragment.

### 6.2. Будущая выдача (авторизованный пользователь)

1. Проверка сессии / membership / permission (конкретная RBAC — вне этого документа; минимум: authenticated + право `bank_materials:read`).
2. API возвращает: `document_id`, `file_id`, `fragment_id`, метаданные, eligibility, тексты по правилам §4–5.
3. Файл/изображение: `GET /api/.../files/{file_id}/content` или signed URL с `storage_key` резолвом на сервере.
4. Page image для сверки bbox — только авторизованно, по `ocr_page_id` / storage_key.
5. Хранение (`storage_key`) отделено от публичного URL (URL эфемерный или path-only API id).

Связь с `EventSource`: при необходимости — отдельная таблица связки `event_id` ↔ `fragment_id` позже; не переиспользовать `event_sources.url` под file:// или disk path.

---

## 7. Пример: Policy Rate (существующие артефакты)

Фактические данные корпуса (не выдуманы):

| Сущность | Значение |
|----------|----------|
| Logical doc slug | `ALFA-Macro_Insights-Policy_Rate_11Sep` |
| Title | «Ключевая ставка ЦБ РФ» (`confirmed`) |
| Publication | `day` → 2026-09-11; display «11 сентября 2026 г.» |
| Period | решение ЦБ на дату note; прогнозы банка до конца 2026–2027 |
| PDF SHA-256 | `92a96805f2b720f76bd0c52d2491044812b38401ab62d0f4a9157b4ca81c49bb` |
| Pages | 4; processing complete; visual `partial_spot_check` |
| OCR | Tesseract v5.4.0.20240606, rus+eng, schema 2 |

Фрагмент `policy_rate_cb_decision`:

| Поле | Значение |
|------|----------|
| kind | `exact_quote` |
| content_type | `fact` |
| page | 1 |
| region | bbox left=109, top=411, w=1155, h=47 |
| ocr_text / verified_transcript | «ЦБ РФ принял решение оставить ставку неизменной на уровне 14,0%» |
| verification | `verified` |
| MVP flags | search ✅, AI evidence ✅, exact quote ✅ |
| source_role | bank material reporting CB decision (не первичный URL ЦБ) |

Фрагмент `policy_rate_rhetoric`: OCR `cTana` → transcript `стала`; оба текста сохраняются; exact quote = transcript.

Фрагмент `policy_rate_credit_monitoring`: `kind=summary` → AI evidence как пересказ ✅, exact quote ❌.

Страницы 2–3: table/chart `verified_unreliable` → не AI evidence / не exact quote для числовых рядов.

---

## 8. Проверки будущего импортёра

Импортёр (ещё не писать) должен:

1. Считать SHA-256 PDF; upsert `bank_document_files` по `sha256`.
2. Не создавать второй file при том же hash.
3. Построить fingerprint OCR **без** host-absolute paths; upsert `bank_ocr_runs` по `(file_id, fingerprint_hash)`.
4. Для каждой страницы: требовать expected outputs; `processing_status!=ok` или пустой TSV → страница failed; run `incomplete` если есть failed.
5. Не ставить `publication_date` из PDF CreationDate.
6. Gold-like month-only → `precision=month`, `publication_date` NULL.
7. Не сливать документы по похожему title/filename.
8. Импорт `fragments.json`: upsert по `(ocr_run_id, stable_key, revision)`; не удалять superseded.
9. Не писать `eligible_*` в БД; при отдаче вызывать `compute_fragment_eligibility`; `needs_reverification` → не exact quote / не AI evidence.
10. Table/chart/contacts regions → fragments из них не создавать как analytic evidence без отдельной verified prose-цитаты.
11. Spot-check document ≠ все fragments verified.
12. Требовать хотя бы одну region-строку на fragment; NULL bbox допустим только с явным `note` (как в части QA 2.3) и **не** `eligible_exact_quote` до привязки координат (или quote allowed but UI without highlight — зафиксировать в импортёре; рекомендация MVP: exact quote допустим, highlight нет).
13. `content_type_status=unconfirmed`, если классификация не из verified QA.
14. `staleness_note` / `is_current_stance=false` для Steels 2021 и аналогов.
15. Писать только `storage_key`, не абсолютные пути в API-facing полях.
16. Не публиковать в static/public.
17. Идемпотентный повторный прогон на том же корпусе → 0 новых file/run/fragment rows (кроме обновления `updated_at` / no-op).
18. При новом OCR fingerprint — не UPDATE текстов старых fragments; создать новый run.
19. Отклонять импорт, если `kind=exact_quote` и пустой `verified_transcript`, или `kind=summary` и пустой `summary_text`.
20. Логировать gaps (§9), не заполнять выдуманными метаданными.

---

## 9. Чего не хватает в текущих артефактах

Для будущего импорта без догадок сейчас **недостаточно** или слабо:

| Пробел | Зачем |
|--------|--------|
| Стабильные UUID (только string `id` / stem) | Нужны `stable_key` + генерация UUID при первом импорте |
| У многих QA-фрагментов `bbox: null` | Нет highlight; точные области не зафиксированы |
| Нет явных `eligible_*` в JSON | Сейчас выводятся только правилами документа |
| Absolute paths в fingerprint (`tesseract_binary`, `tessdata_dir`) | Ломают переносимый fingerprint_hash |
| Нет hash PNG страницы | Смена raster при том же PDF/OCR трудно отследить |
| `content_type_status` не везде явен | Риск выдать классификацию за установленную |
| Нет ACL / permission model | Доступ «авторизованный + право» ещё не специфицирован в коде |
| Нет `active_file_id` / явной серии редакций | Пока по одному PDF на slug |
| Page `content_regions` не связаны id с fragment regions | Только параллельные структуры |
| Нет канонического storage layout / `storage_key` scheme | Сейчас относительные пути репозитория |
| Corpus не хранит eng/rus hashes на верхнем уровне документа отдельно от page fingerprint | Есть в page/manifest fingerprint — нормализовать при импорте |
| FI/Gold cover: мало OCR-слов | Eligibility cover-only fragments ограничена — ок, но нужен явный page role `cover` (сейчас нет поля) |

Не заполнять эти пробелы выдуманными значениями на этапе 2.4.

---

## 10. Граница этапов

| 2.4 | 2.5 | Не сделано |
|-----|-----|------------|
| Документ схемы и политик | SQLAlchemy models + Alembic `007` | Импортёр, поиск, RAG, API, UI |
| Пример Policy Rate | `compute_fragment_eligibility` + тесты на temp DB | Запись рабочих PDF/OCR в БД |

См. `docs/BANK_SCHEMA_IMPLEMENTATION.md`.
