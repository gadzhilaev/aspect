# Bank QA revision import (Этап 2.10)

Дата: 2026-10-21  
Рабочая БД, стенд 1.14, `.env`, API/UI/ассистент **не** менялись.  
Исходная БД 2.8 **не** изменялась (работа только на SQLite-копии).  
OCR / браузер / CDP / commit/push не выполнялись.

## Изменения кода / схемы

| Файл | Назначение |
|------|------------|
| `app/services/bank_materials/apply_qa_revisions.py` | Применение QA-артефакта к существующему OCR run (Session-injected) |
| `app/services/bank_materials/fragment_revision.py` | Выбор **последней** revision по `(ocr_run_id, stable_key)` + eligibility |
| `app/jobs/apply_bank_qa_revisions.py` | CLI `--dry-run` / `--apply` + обязательный `--database-url` |
| `tests/test_bank_qa_revisions.py` | Синтетические регрессии на temp SQLite |

**Схема БД не менялась.** Provenance QA сохраняется аддитивно в существующем `bank_fragments.ocr_correction_json`:

- top-level `from` / `to` / `basis` — правка OCR;
- `qa_provenance` — `artifact_id`, `artifact_sha256`, `method`, `performed_by`, `performed_at`, `classification_basis`, `not_human_manual_qa=true`.

Дополнительно: `source_role=bank_material_qa_revision`, краткая пометка в `notes`.  
AI vision **не** маркируется как human QA.

## Команды

```bash
# CLI
python -m app.jobs.apply_bank_qa_revisions --dry-run \
  --qa-artifact data/bank_materials/verification/policy_rate_qa/ALFA-Macro_Insights-Policy_Rate_11Sep__fragment_revisions_v1.json \
  --database-url "sqlite:///data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db"

python -m app.jobs.apply_bank_qa_revisions --apply \
  --qa-artifact ... \
  --database-url "sqlite:///...__qa_revisions_copy.db" \
  --report-dir data/bank_materials/verification/qa_apply_reports
```

Копия БД 2.8 (SQLite backup API, источник только на чтение):

`data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db`

Источник (нетронут): `.../bank_real_import_20261021T124200.db`

## Синтетические тесты

```bash
python -m pytest tests/test_bank_qa_revisions.py -q
```

**9 passed.** Покрыто: атомарная вставка; identical_skip; конфликт содержимого; неверный SHA/fingerprint; нет предшественника; частичный набор; rollback; provenance; выбор latest; запрет fallback к старой AI-eligible при новой unverified; CLI dry-run без записи.

## Реальный прогон на копии

Отчёт: `data/bank_materials/verification/qa_revision_real_run.json` — **ALL_PASSED True**.

### Dry-run

`status=dry_run_ok` — would insert **3** fragments / **6** regions; строк в БД не изменилось.

### Apply

| | До | После |
|--|---:|------:|
| documents / files / runs / pages | 9 / 9 / 9 / 64 | **без изменений** |
| fragments (исторические строки) | 21 | **24** |
| regions | 23 | **29** (+6 по QA) |

- Три `revision=2` с `supersedes_fragment_id` → соответствующие rev1.
- Rev1 тексты/статусы/ID **не** изменены.
- `qa_provenance.method=ai_vision_over_local_page_png`.

### Eligibility (последние ревизии vs история)

| Метрика | Значение |
|---------|----------|
| Логических фрагментов (latest per key) | **21** |
| historical fragment rows | **24** |
| search (latest) | 21 |
| AI evidence (latest) | **3** |
| exact quote (latest) | **3** |

### Повторный apply

`identical_skip`; прирост строк **0**; ID/тексты/revisions без изменений.

### Integrity

`PRAGMA foreign_key_check` — пусто; `integrity_check` — `ok`.

## Ограничения

1. Импорт только по отдельному QA-артефакту; полный corpus re-load не используется.
2. Новый OCR run не создаётся; SHA/fingerprint должны совпасть с уже загруженной цепочкой.
3. Частично применённый набор → ошибка без auto-repair.
4. Выбор «текущего документа/run» по max(created_at) **не** реализован — только latest revision внутри заданного run.
5. Если latest revision не AI-eligible — fallback к старой eligible **запрещён**.
6. PostgreSQL в этом этапе не проверялся.

**Стоп этапа 2.10.**
