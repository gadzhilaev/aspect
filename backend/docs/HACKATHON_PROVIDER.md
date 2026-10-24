# Hackathon AI provider

Дата: 2026-10-21  
Подключение OpenAI-compatible шлюза организаторов хакатона.  
Commit/push / OCR / браузер / CDP не выполнялись.  
`.env` в этом этапе проверки **не** менялся.

## Настройка (локальный root `.env`)

Добавьте **сами** (значения ключа сюда не копировать):

```env
ASSISTANT_PROVIDER=hackathon
HACKATHON_API_KEY=
HACKATHON_BASE_URL=https://changellenge.up.railway.app/v1
HACKATHON_MODEL=deepseek/deepseek-v4.1-flash
```

Разрешённые `HACKATHON_MODEL` (точный ID):

| Model ID |
|----------|
| `google/gemma-4-26b-a4b-it` |
| `z-ai/glm-5.3-flash` |
| `qwen/qwen3.6-35b-a3b` |
| `deepseek/deepseek-v4.1-flash` (начальная) |
| `qwen/qwen3-vl-30b-a3b-instruct` |
| `moonshotai/kimi-k2.6` |

Doctor: `.\scripts\demo_doctor.ps1` → `provider`, `hackathon_model`, `hackathon_base_url`, `key_configured` (без значения ключа).

## Поведение

- Транспорт: `POST {HACKATHON_BASE_URL}/chat/completions` + `Authorization: Bearer …`
- Без `response_format` / tools / JSON mode API — структурированный ответ разбирается как у GigaChat (JSON в тексте или проза).
- Нет fallback на `api.openai.com`, GigaChat или mock.
- Ключи OpenAI/GigaChat **не** подставляются вместо `HACKATHON_API_KEY`.
- Сохранены: контекст компании/события, `bank_evidence`, серверная проверка цитат, pinned revisions, ACL, запрет выдуманных финансов.
- Общий бюджет orchestrator: ≤1 доп. model HTTP на сообщение (retryable bad completion **или** citation fix — не оба). Детали: `docs/HACKATHON_RESPONSE_DIAGNOSTICS.md`.
- Provenance: `answer_basis=ai_explain_hackathon`, `answer_model=<фактическая модель>` — не «OpenAI».

## Ошибки

| Ситуация | Код | Повтор / fallback |
|----------|-----|-------------------|
| Нет ключа | `PROVIDER_UNAVAILABLE` | нет |
| Неразрешённая модель | `PROVIDER_MODEL_FORBIDDEN` | нет |
| Тело содержит `Budget has been exceeded` | `PROVIDER_BUDGET_EXCEEDED` | **нет** повторов и смены модели |
| 429 без budget-текста | `PROVIDER_RATE_LIMIT` | нет авто-retry |
| 401 | `PROVIDER_UNAUTHORIZED` | нет |
| Timeout / 5xx / сеть | `PROVIDER_UNAVAILABLE` | нет |
| Битый / пустой ответ | `PROVIDER_BAD_RESPONSE` | до 1 shared orchestrator retry (не budget/auth; см. RESPONSE_DIAGNOSTICS) |

Сообщение при бюджете: «Дневной бюджет команды исчерпан. Сброс — в 03:00 МСК».  
Стоимость / остаток рублей / token usage не выдумываются. Если API вернул `usage` — сохраняется в `ProviderResult.usage`; отсутствие ≠ ноль.

## LLM-пути в репозитории

| Путь | Покрыт hackathon? |
|------|-------------------|
| Assistant `get_provider()` → `HackathonProvider` | **Да** |
| OpenAI `LiveAssistantProvider` (`/responses`) | Нет — только `ASSISTANT_PROVIDER=openai` |
| `GigaChatProvider` | Нет — только `gigachat` |
| Ingestion `live_enrich` (OpenAI Responses) | **Заблокирован** при `hackathon` → `INGESTION_LIVE_BLOCKED`; heuristic (`--heuristic-enrich`) сохранён |
| Ingestion fetch (RSS/GDELT/CBR) | N/A (не LLM) |

Ingestion в этом этапе **не запускался**.

## Изменённые файлы

| Файл | Назначение |
|------|------------|
| `app/core/config.py` | `hackathon` + `HACKATHON_*` |
| `app/services/assistant/hackathon.py` | Провайдер |
| `app/services/assistant/provider.py` | wiring + `usage` |
| `app/services/assistant/orchestrator.py` | live + `answer_model` |
| `app/services/assistant/provenance.py` | `ai_explain_hackathon` |
| `app/schemas/assistant.py` | `answer_basis` / `answer_model` |
| `app/services/ingestion/enrich.py` | блок live при hackathon |
| `tests/test_hackathon_provider.py` | mocked HTTP |
| `.env.example`, `scripts/demo_doctor.ps1`, `README.md`, `docs/DEMO_RUNBOOK.md`, `docs/MOBILE_API.md` | docs/ops |
| `web/src/api/assistantTypes.ts`, `AssistantChat.tsx` | честная метка |

## Выполненные проверки

```bash
pytest tests/test_hackathon_provider.py -q
```

Без сети, подменённый `httpx` transport:

- base URL + model + Bearer only in Authorization
- успех + usage
- budget exceeded без повторов
- обычный 429 ≠ budget
- timeout / 401 / 5xx
- плохой payload
- bank citations через прежнюю валидацию
- missing key / forbidden model
- запрет base URL на openai/gigachat hosts
- ingestion live blocked; heuristic ok

### Live smoke (2026-10-21)

| Поле | Результат |
|------|-----------|
| Итог | **PASS** |
| Способ | `HackathonProvider.generate` (не обходной raw HTTP-клиент) |
| Модель | `deepseek/deepseek-v4.1-flash` |
| Host/path | `changellenge.up.railway.app` `/v1/chat/completions` |
| HTTP status | 200 |
| HTTP-попыток | **1** (без авто-повторов / без fallback) |
| Ответ | непустой; контракт `ProviderResult` соблюдён |
| usage | сервер вернул: prompt/completion/total tokens (стоимость/остаток бюджета **не** выводились и не вычислялись) |
| БД | записи assistant **не** создавались (messages/conversations count без изменений) |
| Backend :8003 | перезапущен нашим `uvicorn app.main:app`; `/health` = 200; runtime `provider=hackathon`, `key_configured=true` |

Запрос smoke: «Кратко объясни разницу между фактом события и прогнозом»  
(минимальный in-memory контекст; без чата API, без decisions, без ingestion).

**Ограничение smoke:** проверяет **подключение и контракт ответа** провайдера.  
**Не** подтверждает работу банковских цитат / `bank_evidence_list` в полном чате.

Операционная заметка: в среде агента process-env мог переопределять `ASSISTANT_PROVIDER`/`DATABASE_URL` поверх root `.env`. Для штатного процесса overrides сняты, чтобы pydantic читал root `.env`. Ключ и Authorization в логи не печатались.

Вспомогательный одноразовый скрипт: `scripts/_hackathon_live_smoke.py` (не часть pytest).

## Непроверенные возможности API

- tools / function calling на шлюзе
- `response_format` / JSON mode
- vision-модели (`qwen3-vl-…`) как multimodal input
- стриминг
- фактический расход бюджета и лимиты кроме текста ошибки
- все 6 моделей (по ТЗ не гонялись)
- банковские цитаты end-to-end в полном assistant chat

**Стоп проверки live-подключения.**
