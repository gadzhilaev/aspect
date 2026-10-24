# Расширение проверенных банковских оснований (этап 6.7)

Дата: 2026-10-23  
Метод проверки: **AI vision** по локальным `pages/page_001.png` (не human manual QA).  
OCR повторно **не** запускался. Браузер / CDP / live LLM / commit/push — нет.  
Рабочая БД, исходный `jury_63b`, root `.env`, `:8003` — **не** менялись.  
Импорт 1,38 млн платежей — **не** запускался.

Связанные: `BANK_OCR_CORPUS.md`, `BANK_POLICY_RATE_QA.md`, `BANK_QA_REVISION_IMPORT.md`,
`BANK_FRAGMENT_RETRIEVAL.md`, `COMPETITION_STAND_BOOTSTRAP.md`.

---

## 1. Выбор документов

Из корпуса 9 PDF выбраны **два** с разной тематикой и читаемой prose на стр. 1
(не только по имени файла):

| Документ | Тема | Дата публикации | Почему |
|----------|------|-----------------|--------|
| `Inflation_tracker_02` | инфляция / Росстат (неделя) | 2026-09-02 | Связный текст «Что говорят данные Росстата»; чёткие числовые факты |
| `ALFA-consumption` | потребление / розница | 2026-08-05 | Lead-прогноз + факт по обороту розницы; отличная тема от Policy Rate |

**Policy Rate не изменялся.** Остальные 7 документов корпуса **не** заявляются
полностью проверенными (по-прежнему `partial_spot_check`).

По каждому документу подняты **2** существующих corpus-фрагмента (диапазон 2–3;
третьего `stable_key` в corpus не было — новые ключи без правок OCR/`fragments.json`
через QA-importer добавить нельзя).

---

## 2. Проверенные фрагменты

### Inflation_tracker_02 (стр. 1)

| stable_key | rev | content_type | Цитата (exact) | Период |
|------------|----:|--------------|----------------|--------|
| `infl_week_deflation` | 2 | **fact** | «За прошедшую неделю (25.08-31.08) Росстат зафиксировал дефляцию на 0,01% н/н» | неделя 25–31.08.2026 |
| `infl_yoy` | 2 | **fact** | «В годовом выражении инфляция выросла до 6,32%.» | на дату материала (31.08 в контексте недели) |

- PDF SHA: `09d5537f…129d0c`  
- OCR fingerprint: `710b916b…9d9fb1`  
- QA artifact: `data/bank_materials/verification/evidence_expansion_qa/Inflation_tracker_02__fragment_revisions_v1.json`  
- Не повышались: графики «Недельная инфляция…», правая колонка forecast/interpretation
  (нет prior stable_key), стр. 2–3.

### ALFA-consumption (стр. 1)

| stable_key | rev | content_type | Текст | Период |
|------------|----:|--------------|------|--------|
| `consumption_retail_june` | 2 | **fact** | exact: «Оборот розничной торговли вырос на 7,3% г/г в июне» | июнь 2026 |
| `consumption_peak_forecast` | 2 | **forecast** | exact (бывший summary): непрерывный lead про пик и ~0% г/г в 4К26 | outlook до 4К26; дата заметки 2026-08-05 |

- PDF SHA: `807ee992…a8ea1c6`  
- OCR fingerprint: `d2c8aa3b…5cd6b2`  
- QA artifact: `…/evidence_expansion_qa/ALFA-consumption__fragment_revisions_v1.json`  
- Не повышались: Рис.1–4, блоки про рынок труда без corpus-ключа, стр. 2–4.

Проверка каждой цитаты: непрерывный фрагмент на PNG; OCR — только подсказка;
таблицы/графики не elevated.

---

## 3. QA и импорт

Исходные OCR / corpus `fragments.json` / Policy Rate QA **не** перезаписывались.

Артефакты совместимы с `app.jobs.apply_bank_qa_revisions` и bootstrap `--qa-dir`.

Каталоги (gitignore `verification/`):

| Путь | Назначение |
|------|------------|
| `data/bank_materials/verification/evidence_expansion_qa/` | новые 2 JSON + отчёты apply/retrieval/api |
| `data/bank_materials/verification/competition_qa_expanded/` | Policy Rate + 2 новых (для одного `--qa-dir`) |
| `data/bank_materials/verification/evidence_expansion_stand_copy.db` | **копия** `jury_63b/stand.db` после apply |

Применение (только копия БД):

```powershell
$db = "sqlite:///data/bank_materials/verification/evidence_expansion_stand_copy.db"
$rep = "data/bank_materials/verification/evidence_expansion_qa/apply_reports"

python -m app.jobs.apply_bank_qa_revisions --apply `
  --qa-artifact data/bank_materials/verification/evidence_expansion_qa/Inflation_tracker_02__fragment_revisions_v1.json `
  --database-url $db --report-dir $rep

python -m app.jobs.apply_bank_qa_revisions --apply `
  --qa-artifact data/bank_materials/verification/evidence_expansion_qa/ALFA-consumption__fragment_revisions_v1.json `
  --database-url $db --report-dir $rep
```

Повторный apply тех же артефактов → `identical_skip`, прирост строк **0**.

Результат **не** завязан только на этой копии: те же JSON можно передать bootstrap:

```powershell
python scripts/bootstrap_competition_stand.py --preflight-only `
  --csv-dir data/case/raw `
  --pdf-dir data/bank_materials/raw `
  --ocr-dir data/bank_materials/ocr `
  --qa-dir data/bank_materials/verification/competition_qa_expanded `
  --external-uid U_264 --external-uid U_92
```

(Preflight на этой машине: OK, 3 QA-артефакта в отчёте.)

---

## 4. Числа latest (после apply на копии)

| Метрика | Было (Policy Rate QA only) | Стало |
|---------|---------------------------:|------:|
| logical fragments (latest) | 21 | **21** |
| historical fragment rows | 24 | **28** (+4) |
| eligible **search** | 21 | **21** |
| eligible **AI evidence** | 3 | **7** |
| eligible **exact quote** | 3 | **7** |

Состав AI/quote: 3 Policy Rate + 2 inflation + 2 consumption.

---

## 5. Проверки (без live LLM)

| Проверка | Результат |
|----------|-----------|
| Retrieval evidence: инфляция / потребление / Policy Rate | PASS (`retrieval_checks.json`) |
| fact / forecast / interpretation сохранены | PASS (inflation facts; consumption fact+forecast; Policy Rate fact/interpretation/forecast) |
| exact quote = verified transcript | PASS |
| latest rev=2, без fallback на rev1 | PASS (rev1 сохранены) |
| `as_of=2026-08-01` исключает Inflation (pub 2026-09-02) | PASS |
| нерелевантный gold-запрос → пустой evidence | PASS после фикса порога |
| API fragment + PDF `/files/{id}/content` в allowlist scope | PASS (`api_checks.json`) |
| deny вне allowlist | 404 |
| повторный QA-import | `identical_skip` |
| pytest retrieval + QA revisions + bank API | **22 passed** |

### Минимальный общий фикс retrieval (6.7)

Обнаружен ложный evidence-hit: запрос про золото матчил `consumption_peak_forecast`
только по stem «спрос» (score 2.0).

Фикс: в режиме `evidence` требуется `score >= MIN_EVIDENCE_SCORE` (3.0).  
Регрессия: `test_evidence_rejects_single_weak_stem_false_positive`.  
Док: `BANK_FRAGMENT_RETRIEVAL.md`.

---

## 6. Ограничения

1. Проверены **не** все 9 документов — только 2 + ранее Policy Rate.  
2. По выбранным PDF — только стр. 1 и перечисленные fragments; графики/таблицы не verified.  
3. Проверка — AI vision, не human QA.  
4. Новые `stable_key` без правки corpus не добавлялись (лимит QA supersede).  
5. Копия стенда использует storage `jury_63b/storage` только для read API smoke.  
6. Полный bootstrap нового стенда с expanded QA **не** прогонялся в этом этапе
   (достаточно артефактов + preflight + apply на копии).

---

## 7. Воспроизведение (кратко)

```powershell
# 1) Копия стендовой БД (не трогать jury_63b/stand.db)
copy data\competition_stand\jury_63b\stand.db data\bank_materials\verification\evidence_expansion_stand_copy.db

# 2) Apply QA (см. §3)

# 3) Тесты
python -m pytest tests/test_bank_fragment_retrieval.py tests/test_bank_qa_revisions.py tests/test_bank_materials_api.py -q

# 4) Preflight bootstrap с расширенным QA-dir (без импорта платежей)
python scripts/bootstrap_competition_stand.py --preflight-only `
  --csv-dir data/case/raw --pdf-dir data/bank_materials/raw `
  --ocr-dir data/bank_materials/ocr `
  --qa-dir data/bank_materials/verification/competition_qa_expanded `
  --external-uid U_264 --external-uid U_92
```

**Стоп этапа 6.7.**
