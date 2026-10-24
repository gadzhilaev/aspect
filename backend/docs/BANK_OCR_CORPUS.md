# Bank OCR corpus (Этап 2.3)

Дата: 2026-10-20  
Источник PDF: `data/bank_materials/raw/` (не изменялись)  
Результаты OCR: `data/bank_materials/ocr/` (вне Git)  
Импорт / RAG / БД / API / frontend / LLM / внешний OCR **не** делались. Стенд 1.14 не трогался.

## Команда

```bash
# из корня репозитория; нужны local Tesseract + tools/tessdata/{eng,rus}.traineddata + configs/
python scripts/ocr_bank_materials_batch.py \
  --input-dir data/bank_materials/raw \
  --output-dir data/bank_materials/ocr \
  --tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe" \
  --tessdata-dir tools/tessdata

# визуальная QA / identity / fragments (без повторного OCR):
python scripts/bank_ocr_apply_qa.py

# пересобрать каталог корпуса из существующих manifest.json:
python scripts/ocr_bank_materials_batch.py --corpus-only
```

Пилотный `scripts/ocr_policy_rate_pilot.py` сохранён для истории; **тиражирование** — только через batch-скрипт.

Параметры распознавания: `-l rus+eng --psm 3` (при пустом результате — fallback PSM 6, затем 11), `-c preserve_interword_spaces=1`, timeout 180 с на вызов, проверка exit code и непустых TXT/TSV/слов.

**Resume:** страница пропускается только при совпадении SHA PDF, версии Tesseract, hashes `eng`/`rus.traineddata`, параметров OCR и наличии ожидаемых файлов со `processing_status=ok`. Policy Rate **не** перераспознавался (resume match). При смене параметров старые артефакты уходят в `archive/`, фрагменты помечаются `needs_reverification`.

## Инструмент

| Компонент | Значение |
|-----------|----------|
| Tesseract | v5.4.0.20240606 (UB-Mannheim), абсолютный путь |
| Языки | `rus` + `eng` в `tools/tessdata/` |
| Извлечение страниц | pypdf Image XObject → PNG (без апскейла), по одной странице |
| Схема | `schema_version: 2` (`page_*_meta.json`, `manifest.json`, `fragments.json`) |

Каталог корпуса: `data/bank_materials/ocr/_corpus_manifest.json`.

## Результаты по документам

Все **9/9** документов: `processing_status=complete`.  
`document_visual_status` везде **`partial_spot_check`** (не full verified).

| Документ | Стр. | OCR | Название (confirmed) | Дата (из содержимого) | Темы | Visual |
|----------|-----:|-----|----------------------|---------------------|------|--------|
| Policy Rate 11Sep | 4 | ok (resume) | Ключевая ставка ЦБ РФ | 2026-09-11 | ставка, ДКП | spot p.1–4 (таблицы/графики unreliable) |
| ALFA-7M26 | 4 | ok | Макростатистика 7М26 | 2026-09-07 | макро, труд, ритейл | spot p.1 |
| ALFA-consumption | 4 | ok | Потребление на пике | 2026-08-05 | потребление | spot p.1 |
| ALFA-macro_stat1H26 | 5 | ok | Макростатистика 1П26 | 2026-07-31 | ВВП, макро | spot p.1 |
| Russian Steels | 4 | ok | Российская сталь | **2021-04-15** | сталь | spot p.1; **устарело** |
| FI Strategy 3Q26 | 27 | ok (p.4 через PSM fallback) | Тактический взгляд на 3К26… | 2026-07-22 | ОФЗ, FI | spot p.1,3,4 |
| Gold digest Aug26 | 8 | ok | Обзор рынка золота | 2026-08 (месяц) | золото | spot p.1–2 |
| Inflation tracker 02 | 3 | ok | Инфляция 25–31 августа… | 2026-09-02 | инфляция | spot p.1 |
| Бонд Бриф | 5 | ok | Бонд Бриф: Итоги недели | 2026-09-14 | ОФЗ, ставка | spot p.1 |

Полные SHA-256 и списки `pages_ok` / `pages_failed` / visually checked — в `_corpus_manifest.json` и per-doc `manifest.json`.

### Замечания по обработке

- **FI Strategy p.4:** красный разделитель «Итоги 1-го полугодия 2026 г.» — PSM 3 дал пустой OCR → документ помечен `incomplete` → после fallback PSM страница OK; документ снова `complete`.
- **Обложки** (FI p.1, Gold p.1): мало слов — ожидаемо; дата/название сверены с изображением.
- Дата публикации **не** бралась из PDF `/CreationDate` (экспорт ~2026-09-28). Имя файла — только подсказка.
- **Russian Steels:** дата **15 April 2021** подтверждена по содержимому страницы; не выдавать за текущую позицию банка.

## Формат страницы и цитат

На страницу: номер PDF (с 1), размеры изображения, raw/cleaned, TSV + `words.json` с координатами, mean/median confidence, `processing_status`, отдельный `visual_verification_status`, `content_regions` (`prose` / `table` / `chart` / `contacts_disclaimer` / `mixed` / `unverified`).

Очистка — только пробелы/переносы. Confidence ≠ подтверждение фактов.

Фрагменты (`fragments.json`):

- `exact_quote` — проверенная транскрипция; при правке OCR хранятся `ocr_text` и `exact_quote` (+ `ocr_correction`);
- `summary` — пересказ без статуса точной цитаты;
- `content_type`: `fact` | `forecast` | `interpretation`;
- несколько разнесённых кусков → несколько `regions`, не один bbox на весь текст;
- факт о решении ЦБ из материала банка → источник = этот материал (ссылка ЦБ как первоисточник **не** добавлялась).

## Ограничения для будущего поиска / цитирования

1. Spot-check заголовка и одного абзаца **не** делает документ `verified`.
2. Таблицы и графики: подписи ≠ корректное извлечение рядов/ячеек; области остаются `verified_unreliable` / `unverified`.
3. Непроверенные страницы явно `unverified` в манифестах.
4. OCR-шум кириллицы (`He`/`no`/`Ha`/`cTana`) не «чинится» эвристиками в cleaned; правки только в проверенных `exact_quote`.
5. Старый материал (стали 2021) помечен `staleness_note`.
6. Большие тексты, PNG страниц и `*.traineddata` — вне Git (`.gitignore`).

## Готовность к следующему этапу

| Готово | Не готово |
|--------|-----------|
| Локальный OCR всех 9 PDF в единой схеме | Поиск / RAG / embeddings |
| Resume + corpus manifest | Импорт в БД / API / frontend |
| Spot-check identity + примеры fragments | Полная постраничная верификация |
| Документация пилота (2.2) и корпуса (2.3) | Автоисправление OCR, внешние AI-сервисы |

Следующий этап может опираться на `ocr/*/manifest.json`, `fragments.json` и `_corpus_manifest.json` при явных правилах цитирования выше.

**Стоп этапа 2.3.**
