# Assistant personalization E2E (Этап 3.3)

Дата: 2026-10-21  
Сквозная проверка через **API приложения** (TestClient) + **HackathonProvider**.  
Две синтетические компании **без** `EventImpact`.  
Визуальная готовность UI **не** заявляется.

Рабочая БД, root `.env`, backend `:8003` **не** менялись.  
Браузер / CDP / OCR / скриншоты / commit/push не выполнялись.  
Ключи и Authorization не печатались.

Машиночитаемый отчёт:  
`data/bank_materials/verification/e2e33/e2e33_report.json`  
Раннер: `scripts/run_assistant_personalization_e2e_33.py`

## Тестовая БД и синтетика

| | Путь / значение |
|--|--|
| Источник (только чтение) | `data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db` |
| Копия (SQLite backup API) | `data/bank_materials/verification/e2e33/assistant_personalization_e2e.db` |
| Storage root (только тест) | `data/bank_materials/verification/e2e33/storage` |
| OCR scope | `7d64e39e-0ff5-450c-8a01-c44f678da871` (Policy Rate) |
| PDF | копия raw Policy Rate; SHA `92a96805…` |
| Case slot | `competition_default` |
| Snapshot | `e2e33-synth-v1` (`1f04e4b1-…`) |

**Явно синтетическое (только в копии):**

| Элемент | Детали |
|---------|--------|
| Users / membership | A и B, `@example.com` |
| Companies | «Синтетика Альфа/Бета стенд 3.3» — **одинаковый** manual twin (industry/size/region/profile); различается только display name |
| Case orgs | `U_301` / `U_302` в synthetic snapshot (не импорт реального CSV) |
| Products A | LOA=**true**, DEP=**false** (+ RKO=true, остальные false) |
| Products B | LOA=**false**, DEP=**true** |
| Остальные каталожные поля | одинаковые (OKVED, город, workers, revenue_raw без единиц, ФТС «Китай», группа) |
| Неизвестны | сумма долга, тип ставки, даты пересмотра, суммы депозитов, единицы выручки |
| Event | `evt_synth_e2e33_policy_rate`, префикс «[СИНТЕТИЧЕСКИЙ ТЕСТ 3.3]», `occurred_at=2026-09-20` (**после** Policy Rate `2026-09-11`) |
| EventImpact | **отсутствует** для обеих; `recompute` **не** вызывался |

Дата/текст банковского документа **не** менялись.  
Тестовая новость **не** представляется реальной публикацией.

`connected_to_e2e_db=true` (Session override → копия E2E).

## API-шаги

1. Backup QA DB → seed case snapshot → activate → link U_301/U_302  
2. Pre-LLM: context A/B, isolation, bank evidence, PDF, open conversations  
3. Login A/B  
4. POST open conversation A и B (`calculation_unavailable`, **0** model HTTP)  
5. POST message A (тот же вопрос)  
6. POST message B (тот же вопрос)  
7. GET history / проверки citations / счётчики Impact/Scenario/Decision  

Вопрос (без подсказки кредит/депозит):

> Что эта новость означает для нашей компании? Используй доступные данные компании и материалы банка. Отдели подтверждённое от предположений, объясни, что стоит проверить и чего пока нельзя рассчитать. Укажи использованные банковские источники

## Model HTTP

| | |
|--|--|
| Бюджет этапа | ≤ 4 |
| Факт | **2** (`changellenge.up.railway.app` `/v1/chat/completions`, оба status 200) |
| A | 1 primary, citation retry не понадобился |
| B | 1 primary → HTTP 200, но тело не разобралось (`PROVIDER_BAD_RESPONSE` / `KeyError` empty content) |
| Fallback OpenAI/GigaChat/mock | **нет** |
| usage (A) | prompt 5783 / completion 2736 / total 8519 |
| usage (B) | не получено (parse fail до `ProviderResult`) |

Повторные live-вызовы сверх этого прогона **не** запускались (лимит/честность этапа).

## Pre-LLM — PASS

| Проверка | Результат |
|----------|-----------|
| EventImpact rows | 0 до и после open |
| case A/B `profile_available`, один snapshot | да |
| A LOA/DEP | true / false |
| B LOA/DEP | false / true |
| cross A→B case | access_denied |
| одинаковое событие + одинаковые bank fragment IDs | да (3 passed) |
| slim: products различаются, impact null, имя скрыто | да |
| open → `calculation_unavailable`, `has_impact_calculation=false` | да |
| model HTTP после open | 0 |
| PDF Bearer 200 + SHA; без Bearer 401 | да |

## Техническая часть live

| Проверка | A | B |
|----------|---|---|
| post_message | 200 | **502** `PROVIDER_BAD_RESPONSE` |
| case_context_ref → snapshot | ok | n/a |
| used ⊆ passed, rev pinned, exact quotes | 3/3 ok | n/a |
| history | 3 messages | только opening (ответ не сохранён) |
| EventImpact появился? | нет (0) | нет |
| Scenario / Decision | 0 / 0 | 0 / 0 |
| Provider context products | LOA=true DEP=false | LOA=false DEP=true (захвачен до ответа) |

**Итог source_technical: FAIL** — из‑за сбоя разбора ответа B (не из‑за citations A).

## Содержательная часть

### Компания A (есть полный ответ) — эвристика PASS для кредитного фокуса

Ответ явно:

- отделяет факт новости / forecast·interpretation банка / case vs manual twin;
- отмечает `calculation_unavailable`, `impact=null`, неизвестное ≠ 0;
- указывает **LOA=true** и формулирует проверки: структура кредитов, плавающая/пересматриваемая ставка, объём долга — **как вопросы**, без утверждения «расходы выросли из‑за сохранения ставки»;
- не выдаёт банковский материал за комментарий именно к этой новости;
- не считает отсутствие impact «безопасностью».

**Выдержка (кредитный признак):**

> …у которой в каталоге отмечен кредитный продукт (LOA=true)… Что стоит проверить: структуру кредитного портфеля: есть ли кредиты с плавающей/пересматриваемой ставкой, даты пересмотра, объём долга — в данных компании этого нет.

Признак: **case product LOA=true**.

### Компания B — содержательно не оценена (нет ответа)

Модель вернула HTTP 200, но payload не дал извлекаемого `choices[0].message.content` → оркестратор поднял `PROVIDER_BAD_RESPONSE`.  
Контраст депозитного внимания (**DEP=true**) на тексте ответа **не доказан** этим прогоном.

**Итог content_personalization: FAIL** (нужны оба ответа с различимым вниманием к LOA vs DEP).

Разные формулировки сами по себе не считались бы доказательством; здесь второй ответ отсутствует.

## Честные вердикты

| Измерение | Статус | Комментарий |
|-----------|--------|-------------|
| Доставка контекста | **PASS** | pre-LLM + captured provider contexts A/B с верными продуктами и `impact=null` |
| Техническая проверка источников | **FAIL** | A: citations/history/snapshot ok; B: parse fail |
| Содержательная персонализация | **FAIL** | A уместно про кредит; B нет текста для сравнения |
| UI / визуал | не проверялось | |
| Стабильность качества модели | **не доказана** | один прогон, один сбой B |

Дефектов кода, требующих минимального фикса + регрессии и повторного live в этом этапе, **не** выявлено: prose-fallback уже есть; сбой B — пустой/битый content upstream при HTTP 200.

## Ограничения

- Не импортировался реальный CSV; U_301/U_302 — синтетика в копии.  
- Нет браузерной проверки.  
- Нет повторных live-попыток B (бюджет оставался, но этап запрещает «добивать» ради красивого отчёта сверх честного прогона).  
- Содержательная оценка A — эвристическая, не экспертный аудит каждого claim.  
- Process-env overrides очищаются раннером; ключ читается из root `.env` без вывода.

**Стоп этапа 3.3.**
