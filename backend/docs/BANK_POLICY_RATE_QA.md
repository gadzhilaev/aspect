# Policy Rate fragment QA (Этап 2.9)

Дата: 2026-10-21  
Документ: `ALFA-Macro_Insights-Policy_Rate_11Sep.pdf`  
БД (рабочая / 2.8), API, UI, ассистент, поиск/RAG **не** трогались.  
Исходные PDF / OCR / `fragments.json` **не** переписывались. OCR повторно не запускался.  
Браузер / CDP / Selenium / скриншоты сайта **не** использовались.

## Что реально просмотрено

| Объект | Проверка |
|--------|----------|
| PDF SHA | `92a96805f2b720f76bd0c52d2491044812b38401ab62d0f4a9157b4ca81c49bb` (= манифест) |
| OCR fingerprint_hash | `773a8047695ccaafd59fd63dba57f608e0933cb91c0cbe39a04ddb8c813c1942` |
| Страница 1 PNG | `ocr/.../pages/page_001.png` |
| Происхождение PNG | PDF page 0 XObject `/Im1` (FlateDecode raw RGB 1357×1920) **pixel-equal** PNG |
| Фрагменты | `policy_rate_cb_decision`, `policy_rate_rhetoric`, `policy_rate_bank_forecast` |
| Метод | **AI vision** по локальному PNG и bbox-crops (Cursor agent). **Не** ручная проверка человеком. |

Не просматривались: стр. 2–4; `policy_rate_credit_monitoring` (summary); остальные документы корпуса.

## Что подтверждено / что неизвестно

| Тема | Статус |
|------|--------|
| Решение о ставке 14,0% (как сообщение банка о решении ЦБ) | Подтверждено на стр. 1 (bold lead + тело) → **fact** в материале банка от **2026-09-11** |
| «риторика стала жестче» | Подтверждено в подзаголовке → **interpretation** |
| Прогноз банка (пауза 23 окт.; 14,0% до конца 2026; 12,0% конец 2027) | Подтверждён **непрерывный** абзац на стр. 1 → **forecast** банка, не факт будущего |
| Актуальность решения «на сегодня» | **Не** утверждается |
| Summary `policy_rate_credit_monitoring` | **Не** переподтверждался |
| Типы областей table/chart на странице | Вне scope |

OCR-подсказки (`page_001_cleaned.txt`, старые quotes) использовались только как наводка; текст сверен по изображению.

## Таблица stable_key / revision / content_type / eligibility

Предшественники корпуса = revision **1** (без `primary_region_type` / `content_type_status` → после normalize: unverified/unknown → search only).  
Новые QA-ревизии = revision **2** с `supersedes_revision=1`.

| stable_key | rev | content_type | search | AI | exact quote | reasons (rev2) |
|------------|----:|--------------|:------:|:--:|:-----------:|----------------|
| policy_rate_cb_decision | 1→**2** | fact | ✅ | ✅ | ✅ | `verified_exact_quote` |
| policy_rate_rhetoric | 1→**2** | interpretation | ✅ | ✅ | ✅ | `verified_exact_quote` |
| policy_rate_bank_forecast | 1→**2** | forecast | ✅ | ✅ | ✅ | `verified_exact_quote` |
| policy_rate_credit_monitoring | 1 (без изменений) | interpretation | ✅* | ❌ | ❌ | по-прежнему unverified/unknown trust |

\* search для неподтверждённого prose-кандидата по политике 2.6.1.

Предшественник forecast с ellipsis-склейкой **не** принят как continuous exact quote: rev2 цитирует полный непрерывный абзац с 4 region-строками.

Проверка структуры: `map_fragment` без errors; eligibility — `compute_fragment_eligibility`  
(`data/bank_materials/verification/policy_rate_qa/eligibility_check.json`).

## Расположение QA-артефакта

Игнорируемый каталог данных (не для Git):

```
data/bank_materials/verification/policy_rate_qa/
  ALFA-Macro_Insights-Policy_Rate_11Sep__fragment_revisions_v1.json
  eligibility_check.json
  validate_revisions.py
```

Вспомогательные crops: `data/bank_materials/verification/policy_rate_qa_crops/` (gitignore через `verification/`).

Артефакт привязан к **PDF SHA + OCR fingerprint**. При несовпадении применять нельзя. Новый OCR run **не** создавался.

## Происхождение проверки и ограничения

- Исполнитель: AI-агент по локальному изображению страницы; в артефакте явно `method=ai_vision_over_local_page_png`.
- Человеческая ручная QA **не** заявлялась.
- Доверие не повышалось «заполнением полей без сверки»: region type / content_type_status выставлены только для трёх фрагментов после просмотра изображения и классификации по смыслу на странице.
- Документ датирован **11 сентября 2026**; содержание не выдаётся за текущее решение ЦБ на дату проверки.

## Что нужно для импорта новых ревизий (следующий этап)

1. Загрузчик / оркестратор, умеющий читать **отдельный** QA-файл ревизий (не затирая corpus `fragments.json`).
2. Проверка `source_pdf.sha256` + `ocr_binding.fingerprint_hash` против уже загруженного file/run.
3. Insert только `revision=2` с `supersedes` → rev1; тексты rev1 сохранить.
4. Тот же `ocr_run` (без нового fingerprint).
5. Повторный dry-run/eligibility после load; непроверенные фрагменты других документов не менять.
6. На этапе 2.9 запись в БД **не** выполнялась.

**Стоп этапа 2.9.**
