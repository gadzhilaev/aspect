# Bank materials import dry-run (Этап 2.6 / 2.6.1)

Дата: 2026-10-21  
Запись в БД, поиск, RAG, API, UI и повторный OCR **не** делались.  
Рабочая БД и стенд 1.14 не трогались.

Исправление доверия (2.6.1): см. [BANK_FRAGMENT_TRUST_FIX.md](BANK_FRAGMENT_TRUST_FIX.md).

## Команда

```bash
python -m app.jobs.import_bank_materials --dry-run \
  --input-dir data/bank_materials/ocr \
  --pdf-dir data/bank_materials/raw \
  --report-dir data/bank_materials/reports
```

Без `--dry-run` процесс завершается с кодом 2 и понятным отказом (load ещё не реализован); подключений к БД нет.

Отчёты: `data/bank_materials/reports/` (в `.gitignore`).  
Код: `app/jobs/import_bank_materials.py`, `app/services/bank_materials/{dry_run,normalize,fingerprint,paths,eligibility}.py`.

## Что проверяется

| Область | Поведение |
|---------|-----------|
| PDF | существование под `--pdf-dir`, SHA-256 vs `manifest.source_sha256`, число страниц |
| Страницы | уникальные номера ≥1, заявленные артефакты, размеры >0 |
| Fingerprint | канонизация **без** абсолютных `tesseract_binary` / `tessdata_dir`; учёт `page_psm_used` / fallback |
| Пути | relative paths не выходят за `input-dir` / `pdf-dir`; tool paths не исполняются |
| Даты | day / month / unknown; month не превращается в 1-е число; period отдельно |
| Фрагменты | `stable_key`(+revision), regions, bbox all-or-nothing / в пределах страницы |
| Доверие | только `compute_fragment_eligibility` (+ `region_count`); confidence / spot-check страницы не повышают допуск |

**Хранение vs использование (2.6.1):** отсутствующие `primary_region_type` / `content_type_status` → warning + `unverified` / `unknown`. Корпус остаётся `ok` для будущего импорта, но AI evidence / exact quote закрыты до явного подтверждения в артефакте. Отдельных правил eligibility в dry-run нет.

## Результаты синтетических тестов

```bash
python -m pytest tests/test_bank_import_dry_run.py tests/test_bank_schema.py -q
```

**Dry-run / eligibility:** 21 passed (в т.ч. регрессии trust 2.6.1).  
**Schema + alembic smoke:** 29 passed, 1 skipped.

Сценарии dry-run:

- корректный корпус без trust-полей → search only, не AI/quote;
- явно подтверждённый prose (`primary_region_type=prose`, `content_type_status=confirmed`) → AI + quote;
- неверный SHA / отсутствующий PDF;
- дубли страниц и `(stable_key, revision)`;
- некорректный месяц; month-only OK;
- bbox за страницей;
- fragment page ∉ OCR pages;
- summary, размеченный как exact_quote;
- verified без regions;
- needs_reverification → search only;
- path escape;
- fingerprint без host paths;
- CLI `--dry-run` пишет report;
- trust: verified + missing region type / content_type_status; high OCR confidence; page spot-check; blocked region types; normalize не повышает статусы.

## Результаты реального dry-run (9 документов) — после 2.6.1

Прогон: 2026-10-21T092454Z (`bank_import_dry_run_20261021T092454Z.*`).

| Метрика | До 2.6.1 | После 2.6.1 |
|---------|----------|-------------|
| ok | True | **True** (exit 0) |
| documents | 9 | 9 |
| pages | 64 | 64 |
| fragments | 21 | 21 |
| eligible_search | 21 | **21** (search candidate; insufficient trust marked) |
| eligible_ai_evidence | 21 | **0** |
| eligible_exact_quote | 18 | **0** |
| blocking errors | 0 | **0** |
| warnings | 171 | 171 |

Причина смены счётчиков: normalize больше не выводит `prose` / `confirmed` из отсутствия полей. Все 21 QA-фрагмента корпуса опускают оба поля → `unverified` + `unknown` → eligibility закрывает AI/quote. `verification_status=verified` сохранён (сверка текста), но не повышает классификацию.

Распределение (как в артефактах): kinds ≈ exact_quote 18 / summary 3; verification verified на всех; content_type fact 11 / interpretation 6 / forecast 4 — **без** `content_type_status=confirmed`.

### По документам

| Документ | pages | frags | publication | заметка |
|----------|------:|------|-------------|---------|
| Policy Rate | 4 | 4 | day 2026-09-11 | bbox заполнены; trust всё равно missing |
| ALFA-7M26 | 4 | 2 | day 2026-09-07 | regions без bbox (допустимо) |
| consumption | 4 | 2 | day 2026-08-05 | |
| macro_stat1H26 | 5 | 2 | day 2026-07-31 | |
| Russian Steels | 4 | 2 | day 2021-04-15 | warning `historical_material_note` |
| FI Strategy | 27 | 3 | day 2026-07-22 | page 4 PSM fallback учтён в fingerprint |
| Gold digest | 8 | 2 | **month** 2026-08 | `publication_date=null` |
| Inflation tracker | 3 | 2 | day 2026-09-02 | |
| Бонд Бриф | 5 | 2 | day 2026-09-14 | |

### Типичные warnings (не blocking)

| code | Смысл |
|------|--------|
| `primary_region_type_missing_treated_as_unverified` | нет типа области → `unverified`, без AI/quote |
| `content_type_status_missing_treated_as_unknown` | нет статуса классификации → `unknown`, без AI |
| `absolute_tool_path_ignored` | в fingerprint был абсолютный путь Tesseract — не исполняется |
| `historical_material_note` | Steels 2021 — ожидаемое ограничение корпуса |

Устаревшие коды `primary_region_type_provisional_prose` / `content_type_status_inferred_confirmed` **сняты**.

### Regions / bbox

Непустой `regions` ≠ проверенный prose. NULL bbox сам по себе не ошибка (цитата может быть проверена по странице без подсветки), но без явного `primary_region_type=prose` и `content_type_status=confirmed` quote/AI недоступны. Фиктивные координаты не создаются.

## Разбор 21 фрагмента (trust)

У всех: исходный `verification_status=verified`; отсутствуют `primary_region_type` и `content_type_status`; вычислено `primary_region_type=unverified`, `content_type_status=unknown`; `suitable_for_storage=true`; search=yes, ai=no, quote=no; deny=`region_type_unverified` (первичный гейт; при наличии prose всё равно блокировал бы `content_type_status_not_confirmed:unknown`). Явного подтверждения в QA-артефактах для переноса **нет**.

| document | stable_key | kind | content_type | null_bbox | deny |
|----------|------------|------|--------------|----------:|------|
| ALFA-7M26 | 7m26_lead | exact_quote | interpretation | 1 | region_type_unverified |
| ALFA-7M26 | 7m26_retail_july | exact_quote | fact | 1 | region_type_unverified |
| ALFA-consumption | consumption_peak_forecast | summary | forecast | 1 | region_type_unverified |
| ALFA-consumption | consumption_retail_june | exact_quote | fact | 1 | region_type_unverified |
| ALFA-Macro_Insights-Policy_Rate_11Sep | policy_rate_cb_decision | exact_quote | fact | 0 | region_type_unverified |
| ALFA-Macro_Insights-Policy_Rate_11Sep | policy_rate_rhetoric | exact_quote | interpretation | 0 | region_type_unverified |
| ALFA-Macro_Insights-Policy_Rate_11Sep | policy_rate_bank_forecast | exact_quote | forecast | 0 | region_type_unverified |
| ALFA-Macro_Insights-Policy_Rate_11Sep | policy_rate_credit_monitoring | summary | interpretation | 0 | region_type_unverified |
| ALFA-macro_stat1H26 | macro1h26_title | exact_quote | fact | 1 | region_type_unverified |
| ALFA-macro_stat1H26 | macro1h26_gdp_forecast | exact_quote | forecast | 1 | region_type_unverified |
| ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021 | steels_date_2021 | exact_quote | fact | 1 | region_type_unverified |
| ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021 | steels_subtitle | exact_quote | forecast | 1 | region_type_unverified |
| FI_Strategy_3Q26_22072026 | fi_cover_title | exact_quote | fact | 2 | region_type_unverified |
| FI_Strategy_3Q26_22072026 | fi_section_1h26 | exact_quote | fact | 1 | region_type_unverified |
| FI_Strategy_3Q26_22072026 | fi_risk_thesis | summary | interpretation | 1 | region_type_unverified |
| Gold_digest_August26 | gold_cover | exact_quote | fact | 2 | region_type_unverified |
| Gold_digest_August26 | gold_august_lead | exact_quote | interpretation | 1 | region_type_unverified |
| Inflation_tracker_02 | infl_week_deflation | exact_quote | fact | 1 | region_type_unverified |
| Inflation_tracker_02 | infl_yoy | exact_quote | fact | 1 | region_type_unverified |
| Бонд_Бриф_14092026 | bond_cb_pause | exact_quote | fact | 1 | region_type_unverified |
| Бонд_Бриф_14092026 | bond_market_reaction | exact_quote | interpretation | 1 | region_type_unverified |

Нулевое число AI-фрагментов **ожидаемо**: подтверждений типа области и классификации в корпусе 2.3 недостаточно.

## Несовместимости / пробелы для загрузчика

1. **Явно записать** в `fragments.json` `primary_region_type` и `content_type_status` после отдельной сверки (не из `verification_status`).
2. У многих фрагментов **bbox=null** при непустом `regions` — допустимо для хранения; highlight опционален.
3. Канонический **fingerprint_hash** считать после strip host paths.
4. Учитывать **page_psm_used** (fallback) в params_json OCR run.
5. `stable_key` = `fragments[].id`; `revision` default 1.
6. Не брать publication из PDF CreationDate.
7. Исторический Steels: `is_current_stance=false` + `staleness_note` при INSERT.
8. Load path (`--load`) ещё не реализован — только dry-run.

## Exit codes

| Code | Значение |
|------|----------|
| 0 | нет blocking errors |
| 1 | есть blocking errors |
| 2 | нет `--dry-run` / отказ от нереализованного load |

**Стоп этапа 2.6.1.**
