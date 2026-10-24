# Case data model (Этап 1.2 / 1.2.1)

Дата: 2026-10-20  
Основание: `docs/CASE_DATA_DISCOVERY.md`  
Статус: **проект** (импортёр, миграции, рабочая БД, API и UI не менялись).

## 0. Принцип: один Company, слой кейса рядом

Конкурсные `U_*` / `F_*` / `GROUP_ID` — **внешний справочный слой** (`case_*`), а не вторая система компаний.

| Существующая сущность | Роль при кейс-данных |
|-----------------------|----------------------|
| `Company` | Единственный пользовательский профиль / цифровой двойник. Связь с `U_*` — **опциональная и явная** через `case_org_company_links` (не через поля snapshot). Импорт **не** создаёт `Company` для каждой строки справочника и **не** создаёт stub-`Company` для сирот. |
| `CompanyMembership` | Только ручное/сервисное назначение доступа. Импорт **никогда** не пишет membership. |
| `CompanyNode` / `CompanyEdge` | Граф **конкретного** двойника пользователя. Кейс-платежи и F–U **не** льются сюда пакетом 1.38 млн. Проекция — отдельный, ограниченный шаг (см. §6). |
| `CompanyProfileSettings` | Пользовательские настройки. Импорт может добавлять **предупреждения** (единицы неизвестны), но не подставляет выдуманные финансы. |

Продуктовые API читают case-данные **только** из активного snapshot (§1.0). Незавершённый импорт пишет в другой snapshot и **не** меняет видимый профиль, продукты, группы, связи и resolution.

---

## 1. Схема таблиц

### 1.0. Атомарное переключение набора (обязательная схема)

Выбрана **одна** политика: **immutable snapshots + указатель активного snapshot**.  
Старые данные и provenance **всегда сохраняются** (append-only). Удаление доменных строк при смене набора **запрещено**.

#### Роли

| Понятие | Смысл |
|---------|--------|
| `slot_key` | Независимое «место» кейса в продукте (например `competition_default`). Разные slot — **разные** datasets; совпадение `U_*` между slot **не** связывает identity. |
| `case_snapshots` | Полный неизменяемый снимок набора после загрузки (или failed/building-артефакт). |
| `case_active_snapshot` | Обязательный указатель: какой snapshot сейчас виден для данного `slot_key`. |

#### `case_active_snapshot` (обязательный указатель)

Ровно одна строка на `slot_key`.

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `slot_key` | VARCHAR(64) PK | no | например `competition_default` |
| `active_snapshot_id` | UUID FK → `case_snapshots.id` | **yes** | NULL = ещё нет видимого набора |
| `updated_at` | TIMESTAMPTZ | no | |

Ограничения:

- FK на `case_snapshots(id)`.
- CHECK / приложение: если `active_snapshot_id` NOT NULL, то целевой snapshot имеет `slot_key` тот же и `status = 'active'`.

#### `case_snapshots`

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `id` | UUID PK | no | |
| `slot_key` | VARCHAR(64) | no | семейство набора |
| `version_label` | VARCHAR(64) | no | человекочитаемая метка (`hack-raw-v1`) |
| `version_seq` | INT | no | монотонный номер внутри `slot_key` (1, 2, …) |
| `status` | VARCHAR(32) | no | см. ниже |
| `import_run_id` | UUID FK → `case_import_runs` | no | run, которым собран снимок |
| `built_at` | TIMESTAMPTZ | yes | когда стал `ready` |
| `activated_at` | TIMESTAMPTZ | yes | когда стал `active` |
| `retired_at` | TIMESTAMPTZ | yes | |
| `validation_report_json` | JSON | yes | результат полной проверки перед activate |
| `created_at` | TIMESTAMPTZ | no | |

`status`:

| Статус | Видимость продукту | Описание |
|--------|--------------------|----------|
| `building` | нет | идёт загрузка; пишет только этот snapshot |
| `ready` | нет | загрузка и проверки пройдены; ещё не переключён |
| `active` | **да** | единственный видимый набор слота |
| `retired` | нет | был active ранее; данные сохранены |
| `failed` | нет | импорт/валидация сорвались; данные и provenance сохранены; active не трогали |

Ограничения и индексы:

- UNIQUE `(slot_key, version_seq)`
- UNIQUE `(slot_key, version_label)`
- **Частичный UNIQUE:** не более одного `status = 'active'` на `slot_key`  
  (`UNIQUE (slot_key) WHERE status = 'active'`)
- Индекс `(slot_key, status)`

#### Жизненный цикл (единственная политика)

1. **Создать** `case_snapshots` со `status=building`, `version_seq = max+1`, новый `case_import_runs` с тем же `snapshot_id`.
2. **Загружать** все строки **только** с этим `snapshot_id`. Таблицы активного snapshot **не обновляются**.
3. По завершении загрузки — прогон проверок (§9) → `status=ready` + `validation_report_json`, либо `status=failed` (указатель active **без изменений**).
4. **Атомарное переключение** (одна транзакция):
   - проверить `new.status = 'ready'` и `new.slot_key = :slot`;
   - если есть старый active: `UPDATE … SET status='retired', retired_at=now() WHERE id = old`;
   - `UPDATE new SET status='active', activated_at=now()`;
   - `UPDATE case_active_snapshot SET active_snapshot_id = new.id WHERE slot_key = :slot`;
   - COMMIT.
5. При ошибке на шагах 2–3 или откате транзакции шага 4: **активным остаётся предыдущий** snapshot; новый остаётся `ready`/`failed`/`building` без смены указателя.
6. **Идентичный набор:** если SHA-256 всех трёх файлов нового run совпадают с файлами **текущего active** snapshot того же `slot_key` → `identical_skip`: новый snapshot не активируется, доменные строки **не создаются** (run завершается без смены active).

Прерванный импорт: resume только внутри того же `snapshot_id`/`import_run_id` (`building`). Невозможно продолжить → `failed`; active не меняется. Частично загруженные строки **остаются** как provenance failed-снимка.

#### Согласование всех доменных таблиц

Каждая доменная сущность кейса несёт обязательный `snapshot_id` FK → `case_snapshots` (ON DELETE RESTRICT).  
Чтение «текущего кейса»:

```text
JOIN case_active_snapshot a ON a.slot_key = :slot
JOIN … ON ….snapshot_id = a.active_snapshot_id
```

Список таблиц с `snapshot_id`:  
`case_org`, `case_org_catalog_rows`, `case_org_product_marks`, `case_org_field_resolution`, `case_org_groups`, `case_org_group_members`, `case_payments`, `case_persons`, `case_person_org_links`.  
`case_import_runs` / `case_import_files` также привязаны к `snapshot_id`.

Поля вроде `has_catalog_profile` / `profile_resolution` живут **на строках `case_org` данного snapshot** и пересчитываются только при сборке этого snapshot. Они **не** мутируют active-набор из чужого run.

#### Связь `U_*` ↔ `Company` (вне snapshot)

Таблица **`case_org_company_links`** — единственное место identity-map.  
Она **не** версионируется snapshot’ом и **не** копируется «по совпадению U_ID» между разными `slot_key`.

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `id` | UUID PK | no | |
| `slot_key` | VARCHAR(64) | no | тот же slot, что у snapshots |
| `external_uid` | VARCHAR(64) | no | `U_*` |
| `company_id` | UUID FK → `companies.id` | no | |
| `linked_at` | TIMESTAMPTZ | no | |
| `linked_by` | VARCHAR(64) | yes | оператор/процесс |

Ограничения:

- UNIQUE `(slot_key, external_uid)`
- UNIQUE `(slot_key, company_id)` — в одном slot одна Company ↔ один U
- FK `company_id` ON DELETE RESTRICT

Поведение при новой версии **того же** `slot_key`:

- Строки link **сохраняются**.
- Новый snapshot содержит свои `case_org` с тем же `external_uid`.
- Видимый join: `active case_org.external_uid = link.external_uid AND link.slot_key = slot`.
- Привязка **не теряется** при activate нового snapshot.

Запрещено:

- копировать `company_id` из slot A в slot B из-за одинакового `U_*`;
- писать `company_id` на `case_org` (поля нет — только link-таблица);
- автосоздавать link при импорте.

---

### Общие соглашения полей

- PK: `UUID` (`String(36)`), как в текущих моделях.
- Деньги: см. §3.4 (`NUMERIC(20, 1)` + raw + статус разбора).
- Булевы флаги из CSV (`0.0`/`1.0`): `BOOLEAN NULL` (NULL = пусто/не разобрано).
- `source_file`: имя файла; `source_row_number`: 1-based data-строка после заголовка.
- Время: `TIMESTAMPTZ`.

### 1.1. `case_import_runs` — запуск импорта

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `id` | UUID PK | no | |
| `snapshot_id` | UUID FK → `case_snapshots` | no | один run собирает один snapshot |
| `status` | VARCHAR(32) | no | `pending` \| `running` \| `completed` \| `failed` \| `cancelled` \| `identical_skip` |
| `started_at` | TIMESTAMPTZ | no | |
| `finished_at` | TIMESTAMPTZ | yes | |
| `triggered_by` | VARCHAR(64) | yes | |
| `notes` | TEXT | yes | |
| `error_summary` | TEXT | yes | |
| `resume_cursor_json` | JSON | yes | |

UNIQUE `(snapshot_id)` — один run на snapshot.  
Индексы: `(status)`.

### 1.2. `case_import_files` — файл внутри запуска

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `id` | UUID PK | no | |
| `import_run_id` | UUID FK → `case_import_runs` | no | ON DELETE RESTRICT |
| `source_file` | VARCHAR(255) | no | |
| `content_sha256` | CHAR(64) | no | хеш **сырых байт файла as-on-disk** |
| `byte_size` | BIGINT | no | |
| `row_count_declared` | INT | yes | |
| `row_count_loaded` | INT | no default 0 | |
| `status` | VARCHAR(32) | no | `pending` \| `loading` \| `completed` \| `failed` |
| `last_row_number` | INT | yes | |

UNIQUE `(import_run_id, source_file)`.  
Индекс `(content_sha256)`.

### 1.3. `case_org` — внешняя организация в snapshot

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `id` | UUID PK | no | |
| `snapshot_id` | UUID FK | no | |
| `external_uid` | VARCHAR(64) | no | |
| `has_catalog_profile` | BOOLEAN | no | |
| `profile_resolution` | VARCHAR(32) | no | `absent` \| `single` \| `consensus` \| `conflict` |
| `created_at` / `updated_at` | TIMESTAMPTZ | no | |

UNIQUE `(snapshot_id, external_uid)`.  
Индексы: `(snapshot_id, has_catalog_profile)`; `(snapshot_id, profile_resolution)`.

**Сирота** (только в building-snapshot): `has_catalog_profile=false`, `profile_resolution=absent`; без имени/отрасли/продуктов; без `Company` и membership.

Появление профиля в **этом же** building-snapshot (строки справочника дошли позже в том же run): обновить флаги org и resolution **этого** snapshot. Active не затрагивается.

### 1.4. `case_org_catalog_rows`

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `id` | UUID PK | no | |
| `snapshot_id` | UUID FK | no | |
| `import_run_id` | UUID FK | no | |
| `case_org_id` | UUID FK → `case_org` | no | |
| `source_file` | VARCHAR(255) | no | |
| `source_row_number` | INT | no | |
| `row_content_sha256` | CHAR(64) | no | |
| `org_type` … `region` | как ранее | yes | текстовые/булевы поля справочника |
| `revenue_raw` | VARCHAR(64) | no | **всегда** исходная строка |
| `revenue_amount` | NUMERIC(20, 1) | yes | только при `revenue_parse_status='ok'` |
| `revenue_parse_status` | VARCHAR(16) | no | `ok` \| `error` (никогда не подставлять 0 при ошибке) |
| `revenue_parse_error` | VARCHAR(255) | yes | причина при `error` |
| `revenue_unit` / `revenue_currency` | VARCHAR / CHAR(3) | yes | всегда NULL до подтверждения организаторами |
| `group_external_id` | VARCHAR(64) | yes | |
| `raw_json` | JSON | no | |

UNIQUE `(import_run_id, source_file, source_row_number)`.  
Индексы: `(snapshot_id, case_org_id)`; `(group_external_id)`.

### 1.5. `case_org_product_marks`

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `id` | UUID PK | no | |
| `snapshot_id` | UUID FK | no | денормализация для фильтра по snapshot |
| `catalog_row_id` | UUID FK → `case_org_catalog_rows` | no | ON DELETE RESTRICT |
| `product_code` | VARCHAR(32) | no | `RKO` \| `GAR` \| `LOA` \| `LEA` \| `DEP` \| `ZPP` |
| `mark` | BOOLEAN | yes | |

UNIQUE `(catalog_row_id, product_code)`.

### 1.6. `case_org_field_resolution`

Производная **внутри** snapshot; считается один раз при переходе snapshot → `ready`.

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `id` | UUID PK | no | |
| `snapshot_id` | UUID FK | no | |
| `case_org_id` | UUID FK | no | |
| `import_run_id` | UUID FK | no | |
| `consensus_json` | JSON | no | только **подтверждённые** значения (см. §3.2) |
| `conflict_json` | JSON | no | `{ field: { values: [...], reason } }` |
| `absent_json` | JSON | no | поля, где нет полного покрытия непустых значений |
| `variant_count` | INT | no | |
| `confirmed_field_count` | INT | no | | 

UNIQUE `(case_org_id)`; UNIQUE `(snapshot_id, case_org_id)`.

### 1.7. `case_org_groups` / `case_org_group_members`

Группы с `snapshot_id`. UNIQUE `(snapshot_id, external_group_id)`.  
Членства ссылаются на `case_org` того же snapshot. При конфликте GROUP_ID между вариантами UID — все заявленные членства с `is_conflicted_membership=true`; в `consensus_json` группа не попадает.

### 1.8. `case_payments`

| Поле | Тип | Null | Описание |
|------|-----|------|----------|
| `id` | UUID PK | no | |
| `snapshot_id` | UUID FK | no | |
| `import_run_id` | UUID FK | no | |
| `source_file` | VARCHAR(255) | no | |
| `source_row_number` | INT | no | |
| `row_content_sha256` | CHAR(64) | no | |
| `payer_org_id` / `beneficiary_org_id` | UUID FK → `case_org` | no | |
| `pay_amt_raw` | VARCHAR(64) | no | всегда |
| `pay_amt` | NUMERIC(20, 1) | yes | только при parse `ok` |
| `pay_amt_parse_status` | VARCHAR(16) | no | `ok` \| `error` |
| `pay_amt_parse_error` | VARCHAR(255) | yes | |
| `pay_cnt_raw` | VARCHAR(64) | no | |
| `pay_cnt` | INT | yes | NULL при ошибке разбора |
| `pay_cnt_parse_status` | VARCHAR(16) | no | `ok` \| `error` |
| `amount_unit` / `amount_currency` / `period_label` | | yes | NULL |
| `is_self_pay` | BOOLEAN | no | |
| `intra_file_dup_rank` | INT | no | 1 = первое вхождение content-hash в файле этого run; далее 2,3,… |
| `semantics_note` | VARCHAR(64) | no default `payment_aggregate_only` | |

UNIQUE `(import_run_id, source_file, source_row_number)`.  
Индексы: `(snapshot_id, payer_org_id)`; `(snapshot_id, beneficiary_org_id)`; `(import_run_id, row_content_sha256)`.

Денежные «итоги» — только по правилам §3.3 (не зашиты в схему как единственная истина).

### 1.9. `case_persons` / `case_person_org_links`

Оба с `snapshot_id`. UNIQUE person: `(snapshot_id, external_fid)`.  
Links: UNIQUE `(import_run_id, source_file, source_row_number)`; `relation_kind` default `unspecified`.

### 1.10. Что не храним отдельно

- Полный blob CSV на 1.38 млн строк.
- Параллельную CaseCompany.
- Impact/AI в импорте.
- `company_id` на `case_org` (только `case_org_company_links`).

### 1.11. Диаграмма

```
case_active_snapshot ──► case_snapshots (status=active)
                              ▲
case_import_runs ─────────────┘
  └── case_import_files

case_snapshots
  ├── case_org
  │     ├── case_org_catalog_rows → case_org_product_marks
  │     ├── case_org_field_resolution
  │     └── (payments / person links)
  ├── case_org_groups → case_org_group_members
  ├── case_payments
  ├── case_persons → case_person_org_links

case_org_company_links (slot_key + external_uid → companies)
  — вне snapshot; переживает смену active
```

---

## 2. Переиспользование vs новое

| Нужно различать | Где живёт |
|-----------------|-----------|
| Активный набор | `case_active_snapshot` + `case_snapshots` |
| Исходные записи + запуск | `case_import_runs`, `case_import_files`, provenance на строках |
| Компании справочника | `case_org` + `case_org_catalog_rows` (+ resolution) |
| Банковские продукты | `case_org_product_marks` |
| Платежные связи | `case_payments` |
| Связи людей | `case_persons` + `case_person_org_links` |
| Группы | `case_org_groups` + `case_org_group_members` |
| External → internal | **`case_org_company_links`** (по `slot_key`, не по snapshot) |

---

## 3. Правила проблемных данных

### 3.1. Отсутствующая компания (сирота)

1. Upsert `case_org` в **building** snapshot: `(snapshot_id, external_uid)`.
2. `has_catalog_profile=false`, `profile_resolution=absent`.
3. Сохранить платёж / F–U с FK на этот org.
4. Запрещено: имя, OKVED, продукты, `Company`, membership, запись в `case_org_company_links`.
5. Если в том же building-snapshot позже появляется catalog row — обновить флаги и resolution **только этого** snapshot.
6. Если Company уже связана через link того же `slot_key` — ручной профиль Company импорт не перезаписывает.

### 3.2. Конфликт UID и consensus (уточнение)

1. Все исходные варианты → `case_org_catalog_rows`.
2. Не выбирать первую/последнюю строку как истину.
3. Для **каждого поля** независимо:

| Условие | Куда писать |
|---------|-------------|
| Во **всех** вариантах значение **непустое** и **одинаковое** | `consensus_json` |
| Есть ≥2 различных непустых значения | `conflict_json` (не в consensus) |
| Хотя бы в одном варианте пусто/NULL, а в других одно и то же непустое | **не** consensus: в `absent_json` с пометкой `incomplete_coverage` (совпадение только заполненных **не** подтверждает поле для всех строк) |
| Во всех вариантах пусто | `absent_json`; **null не является подтверждённым значением** и не кладётся в consensus |

4. Конфликт **одного** поля не обнуляет остальные: пригодные поля остаются в `consensus_json`; `profile_resolution=conflict`, если `conflict_json` непустой; иначе при `variant_count>1` и только consensus/absent → `consensus`; при одной строке → `single`.
5. Продукты: per-row marks; в подтверждённый набор — только коды, у которых непустое `mark` совпадает **во всех** вариантах (incomplete coverage → не подтверждён).
6. Публичный слой: consensus + явные блоки conflicts/absent; conflict-поля не выдавать за факт.

### 3.3. Повторы платежей (неоднозначность)

Сохраняются **все** исходные строки и `intra_file_dup_rank`.

| Ситуация | Политика |
|----------|----------|
| Повторная загрузка **идентичных** файлов (те же SHA-256, что у **active** snapshot слота) | `identical_skip`; **0** новых доменных строк; active не меняется |
| Новая версия файлов | Новый snapshot (`building`→`ready`→atomic activate); старый → `retired`; строки старого **сохраняются** |
| Одинаковые строки внутри файла | Несколько rows; ranks 1..n; content-hash одинаковый |

**Пока семантика повторов неизвестна, запрещено объявлять подтверждённым оборотом:**

- сумму **всех** строк;
- сумму **только** строк с `intra_file_dup_rank = 1`;
- любую «дефолтную» денежную свёртку без имени политики.

**Допустимо без оговорок:**

- число строк платежей;
- число content-hash совпадений (`intra_file_dup_rank > 1`);
- число уникальных пар `(payer, beneficiary)`;
- число уникальных `row_content_sha256`.

**Технические суммы** (если нужны для отладки/QA) — только с **явным** `aggregation_policy`, например:

- `policy=sum_all_rows` — сумма всех `pay_amt` с `parse_status=ok` (может завышать при дублях);
- `policy=sum_rank1_only` — сумма только rank=1 (может занижать, если дубли — реальные отдельные агрегаты);
- `policy=none` — денежный итог не считается.

Каждый такой результат сопровождается `policy`, `limitations`, и флагом `is_confirmed_turnover=false` до ответа организаторов.

### 3.4. Числовая точность и неизвестные единицы

#### Наблюдения по исходным файлам (агрегат, без выгрузки записей)

| Поле | Строк | Неразборчивых | Макс. цифр до `.` | Макс. цифр после `.` | Ненулевая дробная часть |
|------|-------|---------------|-------------------|----------------------|-------------------------|
| `REVENUE_COMPANY` | 85 525 | 0 | 12 | 1 | 0 (везде вид `…0`) |
| `PAY_AMT` | 1 380 585 | 0 | 13 | 1 | 0 |

Диапазоны порядка: revenue max ≈ 1.06×10¹¹; pay_amt max ≈ 1.12×10¹² (13 целых цифр).

#### Выбор типа: `NUMERIC(20, 1)`

- **scale = 1** — в файлах ровно один десятичный знак; хранение без округления наблюдаемого формата.
- **precision = 20** — до 19 цифр целой части + 1 дробная; запас относительно 13 наблюдаемых целых (нет риска переполнения на текущем наборе; при появлении более длинного числа → `parse_status=error`, не silent truncate).

Правила разбора (Decimal):

1. Всегда сохранить `*_raw`.
2. Успех (`ok`): строка точно соответствует `^-?\d+(\.\d+)?$`, число целочисленных цифр ≤ 19, дробных ≤ 1, значение точно представимо в `NUMERIC(20,1)` **без округления**.
3. Иначе `parse_status=error`, `*_amount = NULL`, заполнить `*_parse_error` (например `overflow`, `too_many_fraction_digits`, `invalid_format`). **Запрещено** писать 0 как замену ошибки.
4. `unit` / `currency` / `period` = NULL; не подписывать «₽»; не применять порог 15 млрд ₽ к case-суммам.
5. Finance score / `has_finance_context` — только пользовательский twin.

### 3.5. Смысл связей

| Факт | Нельзя утверждать |
|------|-------------------|
| Платёж | Поставка / подряд |
| F–U | Владение / должность |
| FTS country raw | Направление торговли |
| Нет строки | Нет связи в реальности |

---

## 4. Повторная загрузка и масштаб

### 4.1. Идентичный файл / набор

Сверка SHA-256 трёх файлов с `case_import_files` **active** snapshot того же `slot_key` → `identical_skip`, без insert.

### 4.2. Изменённая версия

Новый `case_snapshots` (`version_seq+1`, `building`) → полная загрузка в него → `ready` → atomic activate (§1.0). Старый `retired`, строки на месте. Links по `slot_key` сохраняются.

### 4.3. Прерванный импорт

Resume в том же `building` snapshot. Иначе `failed`, active без изменений, данные failed-снимка сохранены.

### 4.4. Ручные данные Company

Импорт не трогает Company/nodes/edges/settings/memberships. Смена snapshot не overwrite ручных полей. Apply case→Company — отдельный явный шаг (не через чат).

### 4.5. Масштаб платежей

Stream чанками 5–10k; upsert `case_org` building-snapshot; bulk insert payments. Без LLM/impact. Peak RSS ≪ размера CSV.

### 4.6. Исходное vs производное

| Исходное | Производное |
|----------|-------------|
| catalog/product/payment/person rows, import meta | `case_org_field_resolution` (при `ready`), опциональные QA-метрики с именованной policy |
| | Опциональная узкая проекция в twin |

---

## 5. Права доступа

1. `U_*` / `F_*` / `GROUP_ID` ≠ авторизация.  
2. Membership только отдельно.  
3. Контрагент в платеже не даёт доступ к полному профилю другой Company.  
4. Сирота без link недоступна как «моя компания».  
5. Building/failed/retired snapshots не отдаются пользовательским API как «текущий кейс».

---

## 6. Отображение в company context

Только: `case_active_snapshot` + join `case_org_company_links` + **consensus** (и `single`) активного snapshot.

| Case (consensus) | Company / twin |
|------------------|----------------|
| OKVED | `industry` при безопасном маппинге; иначе attrs + warning |
| workers FNS | кандидат `size_band` |
| region / city | `hq_region` / attrs |
| revenue | не как рубли; warning «единицы неизвестны» |
| FTS raw | attrs `source=case_fts_raw`, не direction |
| Платежи | не массово в edges; при проекции — counts/pairs; денежные attrs только с `aggregation_policy` и `is_confirmed_turnover=false` |
| F–U | `person_ref`, `unspecified` |
| Products | read-only блок кейса |

Имя: placeholder `Кейс U_…` только при явной материализации; сироты по умолчанию не материализовать.

---

## 7. Будущие миграции (порядок фиксирован)

1. `case_snapshots` + `case_active_snapshot` + `case_import_runs` + `case_import_files`
2. `case_org` + `case_org_catalog_rows` + `case_org_product_marks` + `case_org_field_resolution`
3. `case_org_groups` + `case_org_group_members`
4. `case_payments`
5. `case_persons` + `case_person_org_links`
6. `case_org_company_links`

Все с FK на `snapshot_id` где применимо; partial unique на один `active` на slot.

---

## 8. Примеры (синтетика)

### 8.1. Сирота в building, active не меняется

```
active = snap_v1
building snap_v2: payment U_1→U_9
→ U_9 orphan только в snap_v2
API по-прежнему читает snap_v1
```

### 8.2. Consensus с пропуском и конфликтом

```
rowA: okved=46.90 city=Москва eco=""
rowB: okved=46.90 city=Казань eco=""
→ consensus: okved=46.90
→ conflict: city
→ absent: eco (все пустые — не подтверждённое значение)
→ profile_resolution=conflict; okved всё ещё можно показывать как confirmed
```

```
rowA: region=Москва
rowB: region=""
→ region НЕ в consensus (incomplete_coverage), несмотря на одно непустое значение
```

### 8.3. Одинаковые платежные строки

```
2 rows identical; ranks 1 и 2
→ row_count=2, duplicate_row_count=1, unique_pairs=1, unique_content_hashes=1
→ денежный «оборот» без policy не публикуется
→ tech sum только как {policy: sum_rank1_only|sum_all_rows, is_confirmed_turnover: false}
```

### 8.4. Identical skip

```
active files sha=AAA
new import sha=AAA → identical_skip, 0 inserts, active без изменений
```

### 8.5. Identity переживает activate

```
link(slot, U_5)→Company C
snap_v1 active → snap_v2 activate
→ link на месте; join к case_org U_5 в snap_v2
slot_other с U_5 → отдельный мир, link не копируется
```

---

## 9. Проверки будущего импортёра

1. UTF-8, `;`, заголовки трёх файлов.  
2. SHA-256 = raw bytes as-on-disk.  
3. `row_count_loaded` = число data-rows.  
4. Resume: UNIQUE `(run,file,row)`.  
5. Каждый payment endpoint → `case_org` того же snapshot.  
6. Сироты без products/Company/membership/link.  
7. `U_428697`: 12 rows; conflict/consensus/absent по §3.2.  
8. Intra-file dups: ranks; **нет** теста «денежный итог = rank1»; есть тесты на counts/pairs и запрет confirmed turnover.  
9. Identical → 0 inserts, active неизменен.  
10. Деньги: raw всегда; overflow/bad → `error` + NULL amount, не 0; unit/currency/period NULL; нет «₽».  
11. Нет assistant/impact в import path.  
12. F–U: `unspecified`.  
13. Activate атомарно; failed building не двигает `case_active_snapshot`.  
14. Building snapshot не виден product read API.  
15. Link сохраняется при смене snapshot того же slot; между slot по U_ID не переносится.  
16. Peak RSS ≪ размера payment CSV.

---

## 10. Вопросы к организаторам

1. Единицы/валюта `REVENUE_COMPANY` и `PAY_AMT`.  
2. Период агрегации `PAY_*`.  
3. Семантика одинаковых строк в payment-файле (дубль выгрузки vs отдельные агрегаты).  
4. Тип связи F–U и смысл `RC_NAME`.  
5. Канон multi-row UID, если есть у организаторов.  
6. `ECO_MARK_LABEL` / `CL_PRODUCT_*`.  
7. Публикация `U_*`/`F_*` в UI.

---

## 11. Краткий итог

**Таблицы:** `case_active_snapshot`, `case_snapshots`, `case_import_runs`, `case_import_files`, `case_org`, `case_org_catalog_rows`, `case_org_product_marks`, `case_org_field_resolution`, `case_org_groups`, `case_org_group_members`, `case_payments`, `case_persons`, `case_person_org_links`, `case_org_company_links`.

**Ключевые решения:** immutable snapshots + atomic pointer; identity в link по `slot_key`; платежные дубли хранить без «верной» денежной свёртки; `NUMERIC(20,1)` + raw + явный parse error.

**Неопределённости:** единицы/период денег, смысл дублей платежей и F–U — у организаторов.

---

## 12. Исправления этапа 1.2.1

1. Введена обязательная схема **immutable snapshot + `case_active_snapshot`**: building не меняет видимые данные; activate атомарно; при ошибке active прежний; данные append-only (`retired`/`failed` сохраняются). Убраны варианты «пометить или удалить» / «решим в миграции».
2. Все доменные таблицы привязаны к `snapshot_id`; resolution/профиль/продукты/группы/связи считаются и живут внутри snapshot.
3. Identity `U_*`↔`Company` вынесена в `case_org_company_links` по `slot_key`; переживает смену версии слота; перенос между независимыми datasets по совпадению U_ID запрещён; поля `company_id` на `case_org` нет.
4. Платежные повторы: counts/pairs допустимы; ни sum(all), ни sum(rank=1) не считаются подтверждённым оборотом; технические суммы только с именованной policy и `is_confirmed_turnover=false`.
5. Тесты/примеры импортёра приведены в соответствие (убран implicit «unique sum = one payment amount»).
6. По файлам обоснован `NUMERIC(20, 1)`; запрет silent round/overflow; raw всегда; ошибка разбора → status `error` и NULL, не ноль.
7. Consensus: null не confirmed; incomplete coverage при пропусках; конфликт поля не скрывает остальные consensus-поля; добавлен `absent_json`.
8. Список миграций начинается с snapshots/active pointer; `case_org_company_links` обязателен, не «опционально позже».
