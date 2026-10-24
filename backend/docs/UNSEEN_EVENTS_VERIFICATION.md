# Проверка персонализации и банковских оснований на новых событиях (этап 6.8)

Дата: 2026-10-23  
Метод: независимая матрица **синтетических** событий + лексический retrieval + TestClient / mocked provider.  
**Live LLM / браузер / CDP / скриншоты / CSV-реимпорт / commit/push — нет.**  
Рабочая БД, root `.env`, `:8003`, исходный `jury_63b/stand.db` — **не** менялись.

Связанные: `COMPETITION_REQUIREMENTS_STATUS.md`, `BANK_EVIDENCE_EXPANSION.md`,
`BANK_FRAGMENT_RETRIEVAL.md`, `ASSISTANT_CASE_CONTEXT.md`,
`ASSISTANT_PERSONALIZATION_E2E.md`, `EVENT_DISCOVERABILITY.md`.

Машиночитаемый отчёт (без секретов):  
`data/bank_materials/verification/e2e68/unseen_events_report.json`  
Раннер: `scripts/run_unseen_events_verification_68.py`

**Итог прогона:** `overall_pass=true` (retrieval + paraphrases + personalization).  
Стабильность **live-модели не проверялась** и не заявляется.

---

## 1. Контур проверки

| | Значение |
|--|--|
| Источник БД (только чтение) | `data/bank_materials/verification/evidence_expansion_stand_copy.db` (QA 6.7) |
| Рабочая копия | `data/bank_materials/verification/e2e68/unseen_events_verification.db` |
| OCR scope | `BANK_MATERIALS_ALLOWED_OCR_RUN_IDS` из `data/competition_stand/jury_63b/stand.env` |
| Storage | `data/competition_stand/jury_63b/storage` |
| Provider | `ASSISTANT_PROVIDER=mock`, `model_http=0` |
| Case slot | `competition_default` |
| Компании | существующие стендовые A/B с U_264 / U_92 |

События помечены `[СИНТЕТИЧЕСКИЙ ТЕСТ 6.8]` и `attributes_json.not_real_news=true`.  
Это **не** реальные новости и не копии банковских заголовков/цитат.

---

## 2. Матрица ожиданий (до поиска)

Ожидания зафиксированы в раннере **до** вызова retrieval.

| Case | Тема | Допустимые документы | Пустой результат | Нельзя выводить из данных |
|------|------|----------------------|------------------|---------------------------|
| E68-INF-1 | инфляция / недельный ИПЦ | `Inflation_tracker_02` | нет | «актуальная инфляция на сегодня»; прогноз банка = факт события |
| E68-INF-1b | перефраз инфляции | `Inflation_tracker_02` | нет | пересказ = первичная статистика Росстата |
| E68-CON-1 | потребление / розница | `ALFA-consumption` | нет | forecast 4К26 = факт июня; кредит/депозит из новости |
| E68-CON-1b | перефраз потребления | `ALFA-consumption` | нет | смешение fact июня и forecast |
| E68-RATE-HOLD | сохранение ставки | Policy Rate 11Sep | нет | bank forecast = будущее решение ЦБ; сумма долга компании |
| E68-RATE-HIKE | гипотеза повышения | Policy Rate (тематически) | допустим | цитата «оставить неизменной» = подтверждение hike; прогноз = факт hike |
| E68-IRREL | сталь / металлургия | — | **обязателен** | пустая выдача ≠ «риска нет» |
| E68-DEMAND-OTHER | золото + общее «спрос» | — | **обязателен** | stem «спрос» = основание по потреблению |
| E68-ASOF-EARLY | инфляция до pub date банка | — | **обязателен** | материал 2026-09-02 как основание для as_of 2026-08-20 |

Дополнительно (после фикса, формулировки **не** использовались при диагностике):

| Id | Запрос | Ожидание |
|----|--------|----------|
| PARA-INF-fresh | недельное снижение цен / Росстат | ≥1 inflation key; не consumption peak / rate decision |
| PARA-CON-fresh | июньский оборот розницы | ≥ `consumption_retail_june`; не inflation week / rate decision |
| PARA-GOLD-fresh | инвестиционный спрос на золото | пусто |

---

## 3. Retrieval: expected vs actual

Score — **не** доказательство смысловой релевантности; ниже — отдельно expected и actual.

| Case | Status | Expected (кратко) | Actual |
|------|--------|-------------------|--------|
| E68-INF-1 | **PASS** | Inflation_tracker; keys infl_* | `infl_yoy` rev2, slug Inflation_tracker_02; status available |
| E68-INF-1b | **PASS** | то же | `infl_week_deflation`, `infl_yoy` rev2 |
| E68-CON-1 | **PASS** | ALFA-consumption | `consumption_retail_june`, `consumption_peak_forecast` rev2 |
| E68-CON-1b | **PASS** | ALFA-consumption | те же 2 ключа |
| E68-RATE-HOLD | **PASS** | Policy Rate keys | `policy_rate_cb_decision`, `rhetoric`, `bank_forecast` rev2; content_type fact/interpretation/forecast разделены |
| E68-RATE-HIKE | **PASS** | rate materials допустимы; не трактовать как hike | те же rate keys (hold-текст); запрет на «hike = confirmed» — в conclusions, не в выдаче |
| E68-IRREL | **PASS** | empty | `no_matching_evidence`, 0 hits |
| E68-DEMAND-OTHER | **PASS** | empty | 0 hits (MIN_EVIDENCE_SCORE=3.0 + dedupe «спрос») |
| E68-ASOF-EARLY | **PASS** | empty (as_of) | 0 hits при as_of 2026-08-20 |

Переформулировки: **PASS** (PARA-INF / PARA-CON / PARA-GOLD).

Наблюдение (не FAIL матрицы): PARA-CON может дополнительно поднимать `policy_rate_bank_forecast` по слабым общим токенам («год» и т.п.) при наличии нужного consumption-ключа. Это остаточное ограничение лексики, не semantic proof.

Проверено косвенно по hits: **latest revision=2**, OCR scope из stand.env, forecast не подменяет fact в `content_type`, as_of режет раннее событие.

---

## 4. Дефект и минимальный фикс

### Симптом (первый прогон)

| Case | Проблема |
|------|----------|
| E68-INF-1 | unexpected `ALFA-consumption` (`consumption_peak_forecast`) |
| E68-INF-1b | unexpected consumption + Policy Rate |

Мосты: одно exact-совпадение на ультра-общих токенах  
«выражении» (фраза «в годовом выражении»), «вырос», «без»  
давало score ровно `MIN_EVIDENCE_SCORE=3.0` без тематического сигнала.

### Фикс (общий, без hardcode ID/компании/тестовой строки)

В `app/services/bank_materials/retrieval.py` стоп-слова query:

- `без`
- `вырос` / `выросла` / `выросло` / `выросли`
- `выражение` / `выражения` / `выражении` / `выражением`

Регрессия: `tests/test_bank_fragment_retrieval.py::test_evidence_rejects_generic_exact_bridges_across_macro_themes`  
(доп. paraphrases, не из матрицы диагноза) + предыдущие тесты stem/спрос и synthetic brackets.  
`pytest tests/test_bank_fragment_retrieval.py` → **9 passed**.

Ранжирование персональной ленты **не** менялось.

---

## 5. Персонализация: лента vs контекст ассистента

Компании стенда (разные конкурсные профили из данных):

| | A | B |
|--|---|---|
| external_uid | U_264 | U_92 |
| LOA / DEP (sample) | true / false | false / true |
| case status | profile_available | profile_available |
| interpretation_limits | есть | есть |

| Проверка | Результат |
|----------|-----------|
| case UID / продукты различаются из данных | PASS |
| синтетика в public news | PASS (`synth_seen=true`) |
| синтетика **нет** в personal (`priority_events`) без Impact | PASS |
| ACL: B → context компании A | 403 |
| скрытого Impact / Scenario / Decision | нет (счётчики 0→0) |
| assistant `case_company_context` A≠B на одном synth-событии | PASS |
| bank_evidence в контексте (INF-1) | status available, **1** fragment у A и у B |

Одинаковая новость **не** обязана давать разный personal feed «ради демо»:  
различия case_context (U_ID, продукты) следуют из известных полей;  
неизвестное (сумма долга, остаток депозита, «платежи = поставки») **не** домысливается.

### Разрыв discoverability (зафиксирован, не чинился)

Персональная лента = только `EventImpact`.  
Синтетика 6.8 без Impact:

- есть в **общей** ленте;
- **нет** в «Для вас»;
- при этом **доступна** ассистенту (`case_company_context` + `bank_evidence`).

Это известный разрыв (`EVENT_DISCOVERABILITY.md`), не дефект ранжирования этапа 6.8.

Scripted/mocked ответ **не** считается доказательством качества реальной модели.

---

## 6. Ограничения

1. Только лексический retrieval; score ≠ semantic relevance.  
2. Live model / HTTP к провайдеру не вызывались (`model_http=0`).  
3. Синтетические события ≠ реальные новости.  
4. AI-evidence только у QA-elevated фрагментов (Policy Rate + inflation + consumption из 6.7).  
5. Personal feed остаётся impact-gated.  
6. Слабые общие токены всё ещё могут поднимать соседние macro-фрагменты рядом с релевантными (см. PARA-CON).  
7. Исходный конкурсный стенд и CSV не переимпортировались.

---

## 7. Как повторить

```powershell
$env:PYTHONPATH = (Get-Location).Path
python scripts/run_unseen_events_verification_68.py
pytest tests/test_bank_fragment_retrieval.py -q
```

Ожидание: `OVERALL True`, отчёт перезаписывается в `e2e68/unseen_events_report.json`.
