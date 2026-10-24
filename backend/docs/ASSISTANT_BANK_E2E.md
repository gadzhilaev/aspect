# Assistant × bank evidence E2E (Этап 2.16)

Дата: 2026-10-21  
Сквозная проверка через **API приложения** (TestClient), не через браузер.  
Визуальная готовность UI **не** заявляется.

Рабочая БД, root `.env`, backend на `:8003` **не** менялись.  
Ingestion / OCR / CDP / скриншоты / commit/push не выполнялись.  
Ключи и Authorization не печатались.

Машиночитаемый отчёт прогона:  
`data/bank_materials/verification/e2e216/e2e216_report.json`  
Раннер: `scripts/run_assistant_bank_e2e_216.py`

## Тестовая БД и синтетика

| | Путь / значение |
|--|--|
| Источник (только чтение) | `data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db` |
| Копия (SQLite backup API) | `data/bank_materials/verification/e2e216/assistant_bank_e2e.db` |
| Storage root (только тест) | `data/bank_materials/verification/e2e216/storage` |
| OCR scope | `7d64e39e-0ff5-450c-8a01-c44f678da871` (Policy Rate run) |
| PDF | копия raw Policy Rate под `storage_key`; SHA `92a96805…` совпал |

**Синтетическое** (только в копии): user, Company, membership, событие  
`evt_synth_e2e216_policy_rate` с явным префиксом «[СИНТЕТИЧЕСКИЙ ТЕСТ 2.16]»,  
`occurred_at=2026-09-20` (**после** публикации материала `2026-09-11`), stub source,  
impact через `recompute_company_impact`.  
Дата/текст банковского документа **не** менялись.  
Тестовая новость **не** представляется реальной публикацией.

Подтверждено: `connected_to_e2e_db=true` (Session override → копия E2E).

## API-шаги

1. Login + membership  
2. GET event  
3. GET `/events/{id}/bank-evidence`  
4. Fragment / document / PDF (+ 401 без Bearer)  
5. Построение `build_conversation_context` (факт + прогноз в passed)  
6. POST open conversation (`answer_basis=ai_explain_hackathon`, **0** model HTTP)  
7. POST message (обычный поток orchestrator → `HackathonProvider`)  
8. GET messages (история)  
9. Повторный GET fragment/document/PDF по ID из `used`

## Model HTTP

| | |
|--|--|
| Бюджет этапа | ≤ 2 |
| Факт | **1** (`changellenge.up.railway.app` `/v1/chat/completions`, status 200) |
| Citation retry | не понадобился |
| Fallback OpenAI/GigaChat/mock | нет |
| usage (если вернул сервер) | prompt 5084 / completion 2207 / total 7291 |

Стоимость и остаток бюджета **не** вычислялись.

## Результаты

### Техническая проверка — PASS

| Проверка | Результат |
|----------|-----------|
| provider / model | `hackathon` / `deepseek/deepseek-v4.1-flash` |
| bank-evidence | status `available`, 3× rev2, types fact+forecast+interpretation |
| as_of | `2026-09-20` (дата новости, не «сегодня») |
| PDF Bearer | 200, `application/pdf`, SHA ok; без Bearer → 401 |
| qa_method | `ai_vision_over_local_page_png` (не human QA) |
| retrieved → passed → cited → validated | 3 → 3 → 3 → 3; rejected 0 |
| used ⊆ passed | да |
| revision pinned | все `revision=2` |
| exact quote = transcript | 3/3 ok |
| history used | 3; revision match при повторном GET |
| записи только в E2E БД | conversations=1, messages=3 |

### Содержательная проверка — PASS (ограниченно)

Отдельно от валидации ID (корректная ссылка **не** доказывает, что каждое утверждение поддержано источником):

| Эвристика | |
|-----------|--|
| Источники использованы (`used`>0) | да (3) |
| Факт / прогноз в ответе разделены по маркерам | да |
| Нет выдуманных «расходов компании» / % выручки | да |
| Банк не выдан за прямой источник ЦБ (грубый запрет формулировок) | да |
| Старый материал не назван «текущей позицией» | да |
| QA не названа человеческой проверкой | да |

### Обезличенный фрагмент ответа

> Разделяю по типам данных. • Факты из новости (источник события) Источник: «Синтетический стенд 2.16»… Текст карточки прямо помечен как синтетическая тестовая новость… Тема: сохранение ключевой ставки и ожидания по траектории…

Полный текст в БД E2E / блоке сообщения; в отчёт не копируется целиком.

## Overall

| Звено | Статус |
|-------|--------|
| Pre-LLM (auth, evidence, context, PDF) | **PASS** |
| Live transport + provenance label | **PASS** |
| Citations technical | **PASS** |
| Sources used | **PASS** |
| Content basic safety | **PASS** |
| History + pinned open | **PASS** |
| **UI / визуал** | **не проверялось** |
| **Семантическая поддержка каждого claim источником** | **не доказана** (только ID/quote match + эвристики) |

`full_chain_pass` в JSON = true для **проверенных** звеньев API-цепочки выше.  
Это **не** заявление о визуальной готовности `BANK_MATERIALS_UI`.

## Ограничения

- Нет браузерной проверки карточек / экрана фрагмента.  
- Один live-сценарий, одна модель, один вопрос.  
- Содержательная оценка — эвристическая, не экспертный аудит.  
- Process-env агента мог переопределять provider/DB; раннер очищает overrides и читает ключ из root `.env` без вывода.  
- Дефектов, требующих минимального фикса + регрессии, **не** выявлено.

**Стоп этапа 2.16.**
