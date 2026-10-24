# Assistant bank evidence (Этап 2.14)

Дата: 2026-10-21  
Проверенные банковские фрагменты в контексте и ответах ассистента.  
Без реальных LLM-вызовов, без смены UI/формул/провайдера, без OCR.

Рабочая БД, `.env`, запущенные сервисы **не** менялись. Commit/push не делались.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/services/assistant/bank_evidence_context.py` | Сбор + бюджет упаковки в контекст |
| `app/services/assistant/bank_evidence_citations.py` | Серверная валидация цитат модели |
| `app/services/assistant/context_builder.py` | `bank_evidence` после ACL/impact |
| `app/services/assistant/orchestrator.py` | Валидация → блок истории; 1 retry для live |
| `app/services/assistant/provider.py` / `gigachat.py` | `bank_evidence_citations` в `ProviderResult` |
| `app/services/assistant/prompts.py` | Правила разделения фактов / банка / вывода |
| `app/services/assistant/provenance.py` | label `bank_material` |
| `app/schemas/assistant.py` | блок `bank_evidence_list` |
| `contracts/openapi.json` | enum BlockType |
| `docs/MOBILE_API.md` | упоминание нового типа блока |
| `tests/test_assistant_bank_evidence.py` | тестовый provider, без платных LLM |
| `docs/ASSISTANT_BANK_EVIDENCE.md` | Этот отчёт |

## Как контекст передаётся

После существующих проверок доступа (`require_company_member` через conversation + наличие impact в `build_conversation_context`) вызывается `collect_event_bank_evidence` (этап 2.13).

В полный контекст и (для live) в `slim_live_context` попадает блок `bank_evidence`:

- `status` / `available`
- `event_occurred_at`, `as_of_date`, `as_of_date_basis`
- `fragments_passed_to_provider` — **фактически переданный** набор (лимит объёма)
- `use_limitations` — правила использования
- при сбое fetch: `status=fetch_error` + безопасный `fetch_error` (не маскируется под `no_matching_evidence`)

Не передаются: search candidates, raw OCR, storage keys, абсолютные пути.  
Повторный поиск в обход серверного OCR scope **не** выполняется.

### Бюджет

- ≤ 3 фрагмента; суммарный текст ≤ ~3200 символов; один фрагмент ≤ ~1400.
- Если фрагмент не помещается — **исключается целиком** (exact quote не обрезается молча).
- Текст оборачивается как DATA (`<<<BANK_FRAGMENT_DATA>>>`), не как инструкции.

## Правила для модели (system prompt)

Разделять: факт новости / факт из материала банка / прогноз·интерпретация банка / данные компании / вывод модели.  
Не утверждать, что банк комментировал именно эту новость.  
Прогноз ≠ факт будущего; старый материал ≠ текущая позиция; `qa_method` ≠ human QA.  
Материалы банка не меняют impact/confidence/симулятор.  
Цитировать только `fragment_id` из переданного набора.

## Проверка ссылок

Модель возвращает `bank_evidence_citations: [{fragment_id, revision?, quoted_text?, section_hint?}]`.

Сервер:

1. Сверяет ID с **переданным** набором (не со всеми retrieved).
2. Сверяет revision.
3. Для `exact_quote` — `quoted_text` должен совпасть с допустимым transcript; summary не оформляется как exact quote.
4. Метаданные/href подставляет **сервер**, не модель.
5. Неизвестные ID / битые цитаты **не** публикуются как подтверждённые.
6. Для live/GigaChat — **один** повтор с пометкой; без бесконечных циклов и без скрытого mock fallback.
7. Не добавляет автоматически все retrieved в «использованные».

**Ограничение:** успешная проверка ID подтверждает происхождение ссылки и снимок revision, **но не** доказывает, что источник поддерживает каждое утверждение модели. Это явно в `provenance_note` блока и в limitations.

## История сообщений

Новые assistant-сообщения получают блок `bank_evidence_list` в `blocks_json`:

```json
{
  "type": "bank_evidence_list",
  "title": "Материалы банка",
  "labels": ["bank_material"],
  "data": {
    "status": "available",
    "used": [{ "fragment_id": "…", "revision": 2, "text": "…", "…": "…" }],
    "diagnostics": {
      "retrieved_count": 2,
      "retrieved_ids": ["…"],
      "passed_to_provider_ids": ["…"],
      "cited_by_model": ["…"],
      "validated_ids": ["…"],
      "rejected": [{ "fragment_id": "…", "reason": "…" }]
    },
    "limitations": ["…"],
    "provenance_note": "…"
  }
}
```

- Сохраняются fragment ID + **revision** + текст/метаданные снимка — история не подменяется поздней revision.
- Старые сообщения **не** переписываются и не получают источники задним числом.
- Полный system prompt / секреты в историю не пишутся.

Диагностика: retrieved → passed_to_provider → cited_by_model → validated.

При `no_matching_evidence` / `integration_not_configured` / `event_date_unavailable` / `fetch_error` блок всё равно фиксирует статус (ассистент может отвечать по остальному контексту, но не заявляет использование аналитики банка).

## Внешний контракт

Добавлен тип блока `bank_evidence_list` (OpenAPI + `MOBILE_API.md`).  
Маршруты assistant без новых path; старые сообщения совместимы (клиент игнорирует неизвестные блоки).

## Выполненные проверки

```bash
python -m pytest tests/test_assistant_bank_evidence.py \
  tests/test_assistant.py tests/test_assistant_provenance.py \
  tests/test_event_bank_evidence.py -q
```

**38 passed.** Покрыто тестовым provider (не качеством live-генерации):

| Проверка | Результат |
|----------|-----------|
| Контекст без unverified / future / raw OCR | OK |
| Корректная ссылка на переданный fragment | OK |
| Отклонение выдуманного ID | OK |
| Отклонение изменённой exact quote | OK |
| fact/forecast в контексте + правила prompt | OK |
| Не все retrieved автоматически в used | OK |
| Пустые статусы + `fetch_error` ≠ no_matching | OK |
| Revision закреплена в истории | OK |
| Существующие assistant/provenance тесты | OK |

Не заявляется качество реальной генерации по результатам тестового provider.

## Ограничения

- UI не обновлён (клиент может пока игнорировать `bank_evidence_list`)
- Нет изменения профиля через чат
- Нет влияния на impact_score / simulator
- Live citation retry — один раз

**Стоп этапа 2.14.**
