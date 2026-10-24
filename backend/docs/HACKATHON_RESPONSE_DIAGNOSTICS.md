# Hackathon response diagnostics (этап 3.3.1)

Дата: 2026-10-21  
Live LLM / смена модели / `.env` / рабочая БД / процессы / UI / commit — **не** выполнялись.  
Вердикт этапа 3.3 **не** переписывался (остаётся FAIL по компании B).

## 1. Установленная причина сбоя B (прогон 3.3)

### Что известно по артефактам `data/bank_materials/verification/e2e33/`

| Факт | Источник |
|------|----------|
| `post_message` B → HTTP **502** `PROVIDER_BAD_RESPONSE` | `e2e33_report.json` |
| Model HTTP для B: **1**, status **200** | тот же отчёт (`model_http_statuses`, `model_http_delta`) |
| Пользовательское сообщение: «Некорректный ответ модели хакатон-провайдера» | отчёт |
| `B_full_content` / сырое тело completion | **отсутствуют** |
| `usage` для B | **не** попал в `usage_items` (только A) |
| Лог/док: `KeyError` / empty content на этапе извлечения | `ASSISTANT_PERSONALIZATION_E2E.md` |

### Точка ошибки в коде (на момент прогона)

`HackathonProvider.generate` → прежний `extract_chat_completions_text` / разбор `choices[0].message.content`.  
Любой из путей (пустые `choices`, нет `message`, нет/`null`/пустой `content`, неподдерживаемый тип) сворачивался в **`KeyError`**, затем в `PROVIDER_BAD_RESPONSE`. Диагностика не разделяла подтипы; `usage` при parse-fail не сохранялся.

### Вердикт по причине

**Точная причина по имеющимся артефактам не установлена.**

Сырой JSON ответа B не сохранён. Нельзя честно отнести сбой к конкретному подтипу
(`empty_choices` / `missing_content` / `content_null` / `empty_content` /
`unsupported_content_type` / `truncated` / `refusal` / `upstream_error_in_body` /
ошибка контракта приложения) без домыслов. Upstream «сломался» без доказательств
не утверждается: HTTP 200 подтверждён, тело — нет.

Fixtures в тестах этапа 3.3.1 — **синтетические**, не обезличенный снимок live-B.

## 2. Изменения парсера и диагностики

Файл: `app/services/assistant/hackathon.py`.

- `inspect_chat_completions_body` — классификация без `str(...)` произвольных полей.
- Поддерживаемый текст: `str` или list parts с `type` ∈ `{text, output_text}` и строковым `text`.
- `reasoning_content` **никогда** не становится ответом пользователю (только флаг в диагностике).
- Пустой / `finish_reason=length` / `refusal` / `error` в теле при HTTP 200 → **не** успех.
- `extract_usage` вызывается даже при неуспешном разборе.
- В `AppError.details` — безопасные коды (`reason`, `http_status`, `request_id`,
  `choices_count`, `finish_reason`, `content_type`, `content_length`, флаги,
  `usage`). Полный body / prompt / reasoning в логи и клиентский `message` не пишутся.
- Пользовательский `message` остаётся общим: «Некорректный ответ модели хакатон-провайдера».

### Prose-fallback

`parse_hackathon_assistant_payload`: если из content извлечён непустой текст и JSON-объект
не разобрался — весь текст идёт как `content`, `bank_evidence_citations=[]`.  
Серверная валидация цитат **не** обходится: пустые citations → `used` пуст, выдуманные ID
по-прежнему reject. Fallback **не** применяется к пустым/усечённым/refusal/error телам
(они отсекаются до payload-parse).

## 3. Политика повторов

| Уровень | Поведение |
|---------|-----------|
| SDK | нет отдельного SDK retry |
| Транспорт (`httpx`) | один POST; timeout/сеть → `PROVIDER_UNAVAILABLE`, без цикла |
| Provider (`HackathonProvider`) | **без** внутреннего HTTP-retry; budget / 401 / rate-limit / 5xx — сразу |
| Orchestrator | **общий** бюджет: ≤ **1** дополнительный model HTTP на пользовательское сообщение |

Доп. HTTP допускается только для:

- retryable `PROVIDER_BAD_RESPONSE` (`empty_choices`, `missing_*`, `content_null`,
  `empty_content`, `truncated`, `unsupported_content_*`); **или**
- citation-fix после rejected bank citations —

**не оба**, если бюджет уже потрачен.  
`refusal` / `upstream_error_in_body` / `PROVIDER_BUDGET_EXCEEDED` / `PROVIDER_UNAUTHORIZED` —
**без** повтора. Нет fallback на другую модель / OpenAI / GigaChat / mock.

При финальной ошибке `db.commit` ассистента не выполняется → успешного assistant-ответа нет
(opening от `get_or_create` сохраняется отдельно).

## 4. Результаты тестов

```bash
pytest tests/test_hackathon_response_diagnostics.py tests/test_hackathon_provider.py -q
```

Покрытие (mocked HTTP):

- нормальный ответ + usage;
- `choices=[]`;
- отсутствующий / null / пустой content;
- неподдерживаемый тип / part type;
- `finish_reason=length` (не успех);
- refusal;
- `error` при HTTP 200;
- usage при неуспешном разборе;
- text parts;
- prose-fallback + пустые citations под валидацию;
- reasoning_content не как ответ;
- orchestrator: empty → ok с валидной цитатой (2 HTTP);
- общий лимит: empty + bad citation → **нет** 3-го HTTP;
- нет нового assistant-сообщения при финальном bad response;
- budget / 401 без повтора.

## 5. Что проверить одним следующим live-прогоном

1. Сохранить **обезличенную** структуру completion B при `PROVIDER_BAD_RESPONSE`
   (без Authorization, без полного prompt, без `reasoning_content` в пользовательский текст):
   `http_status`, `request_id`, `choices_count`, `finish_reason`, `content_type`,
   `content_length`, `error_code`, `usage`, флаги refusal/tool_calls.
2. Убедиться, что при retryable пустом теле уходит **не более одного** доп. HTTP,
   и что usage B появляется в артефактах даже при повторном fail.
3. Не менять вердикт 3.3 задним числом: новый прогон — отдельный отчёт.
4. Контраст A/B (LOA vs DEP) оценивать только если оба ответа успешно сохранены.

См. также: `docs/HACKATHON_PROVIDER.md`, `docs/ASSISTANT_PERSONALIZATION_E2E.md`.
