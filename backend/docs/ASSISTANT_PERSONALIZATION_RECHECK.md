# Assistant personalization — повтор B (этап 3.3.2)

Дата: 2026-10-21  
Ограниченный live-повтор **только компании B** после фикса диагностики (3.3.1).  
Полный прогон A/B **не** перезапускался. Ответ A **не** генерировался заново.

Рабочая БД, root `.env`, backend `:8003`, UI — **не** менялись.  
Браузер / CDP / OCR / скриншоты / commit/push не выполнялись.  
Ключи, Authorization, полный prompt и `reasoning_content` не печатались.

Машиночитаемый отчёт:  
`data/bank_materials/verification/e2e332/e2e332_report.json`  
Раннер: `scripts/run_assistant_personalization_recheck_332.py`

**Прежний FAIL этапа 3.3 сохранён** (см. `docs/ASSISTANT_PERSONALIZATION_E2E.md`).

**Итог 3.3.2:** Повтор B после 3.3.1 прошёл.

Один успешный повтор **не** доказывает стабильность модели.

---

## Путь новой БД

| | Путь |
|--|--|
| Источник (только чтение) | `data/bank_materials/verification/e2e33/assistant_personalization_e2e.db` |
| Копия (SQLite `backup` API) | `data/bank_materials/verification/e2e332/assistant_personalization_recheck_b.db` |
| Storage PDF (переиспользован) | `data/bank_materials/verification/e2e33/storage` |
| Отчёт 3.3 (A + seed) | `data/bank_materials/verification/e2e33/e2e33_report.json` |

Исходная БД 3.3 и её история **не** изменялись.

---

## Что переиспользовано из 3.3

- Снимок тестовой БД (backup → новая копия)
- Компания B / `U_302` / тот же snapshot `1f04e4b1-…` / `e2e33-synth-v1`
- То же событие `evt_synth_e2e33_policy_rate`
- Те же банковские фрагменты, revision **2**
- Тот же вопрос (строка без правок)
- Модель `deepseek/deepseek-v4.1-flash`, провайдер `hackathon`
- Сохранённый **`A_full_content`** из отчёта 3.3 (A не вызывалась)

### Изменения кода после 3.3, влияющие на этот прогон

Зафиксированы, **не** откатывались ради успеха:

1. Структурированный разбор completion + безопасные `PROVIDER_BAD_RESPONSE` details (3.3.1)
2. Общий бюджет orchestrator ≤1 доп. model HTTP (bad response **или** citation fix)
3. Сохранение `usage` при неуспешном разборе

Вопрос, модель, продукты, даты и банковские источники **не** менялись.

---

## Подготовка без LLM — PASS

| Проверка | Результат |
|----------|-----------|
| LOA / DEP компании B | **false** / **true** |
| Snapshot | `1f04e4b1-662c-4c22-9162-dc7dfd101207` (= 3.3) |
| Event | `evt_synth_e2e33_policy_rate` |
| impact | null; `calculation_unavailable` |
| Bank passed IDs | те же 3; все **rev 2** |
| История B после сбоя 3.3 | 1 сообщение (opening assistant); **0** user — скрытого вопроса нет |
| Повторная отправка | штатный open (reuse того же `conversation_id`) + новый `client_message_id` |
| Новый разговор | **не** создавался (причина: orphan user msg нет, opening на месте) |
| EventImpact / Scenario / Decision до live | 0 / 0 / 0 |
| Fragment API + PDF Bearer | 200 + SHA ok; без Bearer 401 |
| Model HTTP после open | 0 |

Контексты A (из 3.3) и B (этот prep) **сопоставимы**: один snapshot/event/bank set; различаются только продукты (A: LOA; B: DEP).

---

## Live только B

| | |
|--|--|
| Endpoint | `POST /api/v1/assistant/conversations/{id}/messages` |
| Лимит | ≤ **2** model HTTP |
| Факт | **1** (`changellenge.up.railway.app` `/v1/chat/completions`, status **200**) |
| Retry | 0 (citation/bad-response retry не понадобился) |
| Fallback | нет |
| usage | prompt **5777** / completion **4034** / total **9811** |
| post_status | **200** |

`finish_reason` на успешном пути в клиентский payload не пробрасывается; HTTP status completion = 200, parse/citation ok. Отдельных safe-diagnostics ошибок не было.

---

## Техническая оценка B — PASS

| Проверка | Результат |
|----------|-----------|
| parsed response | ok, `content_len` ≈ 5150 |
| passed → cited → validated | 3 → 3 → 3; `rejected=[]` |
| used ⊆ passed | да |
| pinned revisions | все used rev **2**; exact_quote ↔ transcript ok |
| `case_context_ref` в истории | snapshot `1f04e4b1-…`, `profile_available` |
| history | ≥ 3 сообщений после ответа |
| новые EventImpact / Scenario / Decision | **0** / **0** / **0** |
| записи только в новой копии | да (`e2e332/…recheck_b.db`) |
| provider context products | LOA=false, DEP=true, impact=null |

---

## Содержательное сравнение A (3.3) vs B (3.3.2)

Ответ A — из артефакта 3.3. Ответ B — этот прогон.

### Признаки (не «разные слова»)

| Признак | A (LOA=true) | B (DEP=true) |
|---------|--------------|--------------|
| Продуктовый маркер | Явно **LOA=true** + проверки кредитного портфеля, плавающая/пересматриваемая ставка, объём долга | Явно **DEP=true** + «действующие депозитные договоры», остатки/ставки по депозитам, ликвидность/стоимость денег |
| LOA=false | n/a | Не трактует false как «долгов нет вообще»; прямо: false «не доказывает отсутствие кредитов/вкладов во всех банках» |
| Сохранение ≠ повышение | Сохранил / без изменений | «оставить ставку неизменной», «сохранение ставки» — без подмены на hike |
| Факт vs прогноз банка | fact / forecast / interpretation разделены | То же: fact 14,0%; forecast пауза 23 окт / 14% до конца года; interpretation «риторика жестче» |
| Денежный расчёт | Нет персональных сумм потерь/доходности | Нет выдуманной доходности депозита; «суммы и ставки неизвестны» |
| impact null | unavailable ≠ 0; не «безопасно» | То же |

### Выдержки B (депозитный фокус)

> Продукты в источнике: RKO — true, **DEP — true**; LOA, GAR, LEA, ZPP — false… Флаг false … не доказывает отсутствие кредитов/вкладов во всех банках.

> Что стоит проверить… остатки по **депозитам** и ставки по ним… действующие **депозитные договоры** (продукт отмечен как присутствующий, но суммы и ставки неизвестны).

Различие формулировок само по себе **не** считалось доказательством; здесь контраст опирается на разные product-linked проверки (кредит у A vs депозит/ликвидность у B) при одинаковом вопросе и источниках.

---

## Вердикты 3.3.2 (отдельно от 3.3)

| Измерение | Статус |
|-----------|--------|
| Prep / сопоставимость контекста | **PASS** |
| Техническая проверка B | **PASS** |
| Содержательная оценка B (+ контраст с A) | **PASS** |
| Исходный этап 3.3 | **FAIL без изменений** |

Формулировка успеха: **«Повтор B после 3.3.1 прошёл»** — не «исходный прогон A/B прошёл без ошибок».

---

## Ограничения

- Не полный повтор A+B; A только из сохранённого текста.
- Один live HTTP; нестабильность модели не опровергнута и не доказана.
- `document_href` в fragment payload для проверки document API в этом стенде оказался пуст; fragment + PDF content с Bearer проверены.
- Эвристический content review, не экспертный аудит каждого claim.

**Стоп этапа 3.3.2.**
