# Agent loop — история и повторы (Этап 4.5.1)

Дата: 2026-10-22  
Статус: точечные правки поверх 4.5; архитектура loop не переписывалась.  
Без live LLM / браузера / CDP / OCR / commit/push. Root `.env` не включал флаг.

---

## Что подтвердилось

- User commit до model HTTP; SQLite write-lock не держится на сети.
- `client_message_id` + unique constraint дают один user row на id.
- Incomplete stop персистится как `missing_data` / `loop_incomplete` / `not_ai_final`.
- UI не делает автоматический повтор после timeout (только кнопка «Повторить»).
- Проверка `ASSISTANT_MESSAGE_IN_PROGRESS` при user без reply — **не** полноценный тест одновременных запросов (TestClient portal небезопасен для двух потоков). Моделируется окно гонки: уже есть user, ответа ещё нет → 409 без HTTP.

---

## Что исправлено

| Тема | Было | Стало |
|------|------|--------|
| История | whole messages **и** char-slice до 2000 с `…` | только целые сообщения в `MAX_HISTORY_MESSAGES` + `MAX_HISTORY_TOTAL_CHARS`; длинные **опускаются целиком**; `history_incomplete` / `history_omitted_count` |
| Текущий вопрос | мог пострадать от `[:4000]` / packing | `user_question` восстанавливается после pack; не mid-cut |
| Replay incomplete | `200` + `reused=true` (выглядело как success) | тот же `ASSISTANT_LOOP_*` error + `details.reused=true`, `not_ai_final`; без нового HTTP |
| Тот же ID + другой текст | возвращался чужой ответ | `ASSISTANT_MESSAGE_ID_CONFLICT` (409), без HTTP |
| Нормализация текста | неявный `.strip()` | `normalize_message_text`: strip + unify `\r\n` → `\n`, без сжатия внутренних пробелов |
| Internal reply-link | утекал в `GET …/messages` | фильтр в `_msg_out` |
| UI retry | всегда новый id | `isRetry`: terminal → новый id; transient / IN_PROGRESS → тот же id; обычный send → всегда новый |

---

## Тесты

- Backend: `tests/test_assistant_agent_api_integration.py` (в т.ч. history omit, conflict, terminal replays, new id after failure).
- Frontend unit: `web/scripts/assistant-retry.test.mjs` (`assistantRetry.ts`).
- Связанные protocol / runtime / adapter — без регрессий ожидаются.

---

## Ограничения

- Падение процесса после commit user и до commit assistant оставляет **IN_PROGRESS навсегда** для этого `client_message_id` (нет TTL / фоновой очереди / unsafe auto-retry). Новая попытка — **новый** id (кнопка после terminal или новый ввод).
- External hackathon API по-прежнему не exactly-once.
- Concurrent duplicate на уровне реальных параллельных HTTP в TestClient **не** гонялся.
- Write-tools / live LLM / включение флага в root `.env` — вне этапа.
