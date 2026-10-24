# Bank materials UI (Этап 2.15)

Дата: 2026-10-21  
UI банковских источников в чате ассистента и экран конкретного фрагмента.  
Bearer-загрузка оригинального PDF через Blob. Без браузерной/CDP/визуальной проверки, без реальных LLM, без commit/push.  
Рабочая БД, `.env` и бизнес-логика backend **не** менялись.

## Маршрут

| Путь | Доступ | Назначение |
|------|--------|------------|
| `/bank-materials/fragments/:fragmentId` | `ProtectedRoute` | Точный фрагмент + связанный document |

Query (навигация назад, без токенов): `?conversation=&event=&company=`

Ссылка из чата строится в `fragmentDetailPath()` → «Посмотреть материал».

## Изменённые / новые файлы

| Файл | Назначение |
|------|------------|
| `web/src/api/bankMaterialsTypes.ts` | Типы `bank_evidence_list` + API document/fragment |
| `web/src/api/assistantTypes.ts` | `bank_evidence_list` в `AssistantBlockType` |
| `web/src/api/client.ts` | `apiRequestBlob` (Bearer, отказ от JSON-как-PDF) |
| `web/src/api/endpoints.ts` | `bankMaterialsApi.document` / `.fragment` |
| `web/src/lib/bankMaterialsDisplay.ts` | Даты/precision, labels, empty copy, parse used |
| `web/src/lib/bankPdfDownload.ts` | Auth Blob download + revoke object URL |
| `web/src/components/assistant/BankEvidenceBlock.tsx` | Карточки только из `data.used` |
| `web/src/components/assistant/AssistantChat.tsx` | Рендер блока, label `bank_material`, раздельные источники |
| `web/src/pages/BankFragmentPage.tsx` | Экран фрагмента |
| `web/src/routes/AppRoutes.tsx` | Маршрут |
| `web/src/styles/bank-materials.css` | Светлая/тёмная тема через tokens, mobile |
| `web/src/App.tsx` | Импорт CSS |
| `web/scripts/bank-materials-ui.test.mjs` | Адаптерные / fixture-тесты |
| `docs/BANK_MATERIALS_UI.md` | Этот отчёт |

## Поведение в чате

- Карточки только из **`data.used`** (серверно валидированные).
- `retrieved` / `passed` / `cited` / diagnostics / enum / internal ID **не** показываются обычному пользователю.
- История использует **сохранённые** `text` + `revision` из блока сообщения; повторный fetch «последней» revision для карточек не делается.
- Источники новости (`source_list`) и материалы банка (`bank_evidence_list`) — **раздельные** блоки.
- Текст не называется рекомендацией для компании.
- Summary → подпись «Пересказ»; exact quote → «Точная цитата»; длинный текст — «Показать полностью» (без склейки кусков в «непрерывную» цитату).
- Старое сообщение **без** блока — прежнее отображение (блок просто отсутствует).
- Ответ ассистента не скрывается из‑за отсутствия банковских материалов.

### Пустые состояния (`used` пуст)

| status | UI |
|--------|-----|
| `available` | Ничего не рисуем (available ≠ использовано) |
| `fetch_error` | «Материалы банка временно недоступны» |
| `integration_not_configured` | Спокойный текст про неподключённый сервис |
| `event_date_unavailable` / `no_matching_evidence` | Краткое человеческое пояснение |
| отсутствует блок | Как раньше |

## Экран фрагмента

1. GET `/api/v1/bank-materials/fragments/{fragmentId}` — **точный** ID.
2. Затем GET document по `document_id` из ответа (дополнение; ошибка document не роняет страницу).
3. Не подменяется latest revision.

На странице: возврат к обсуждению, название/дата, тип утверждения, точный текст или пересказ / restricted без raw OCR, страница, «Об источнике», QA («Сверено AI по изображению документа» для AI vision), кнопка PDF.

`is_superseded`: «В этом ответе использована предыдущая версия фрагмента» — старый текст остаётся, история чата не обновляется.

### Состояния экрана

loading · 401 · 404 · 503 `BANK_MATERIALS_NOT_CONFIGURED` · ошибка загрузки · restricted · недоступный оригинал · `BANK_FILE_INTEGRITY` (при скачивании).

SHA / fingerprint на основной экран не выводятся.

## Загрузка PDF

1. `downloadBankPdf(content_href)` → path без query-токена.
2. `apiRequestBlob` с `Authorization: Bearer <access>`.
3. При JSON/`application/json` — ошибка, файл не сохраняется.
4. `URL.createObjectURL` → programmatic `<a download>` → `revokeObjectURL`.
5. **Не** `window.open(content_href)` (потеряет Bearer).

При logout `ProtectedRoute` уводит со страницы; эффект перезагрузки завязан на `user`, данные прошлой сессии не остаются на экране.

## Выполненные проверки

```bash
cd web
npm run test:bank-materials
npm run build
```

Стек: `node:test` + `--experimental-strip-types` (как и case-context — **без** React Testing Library / vitest).  
Поэтому: адаптеры, fixtures и wiring проверены кодом; **визуальный рендер в браузере не проводился** и не заявляется.

| Проверка | Как |
|----------|-----|
| Старое сообщение без блока | parse null + chat не требует блок |
| used exact + summary | fixture parse + labels |
| used пуст / available | empty copy = null |
| fetch_error | фиксированная фраза |
| superseded / restricted / QA | source contracts + `qaMethodUserCopy` |
| неизвестный content_type | fallback «Материал банка» |
| month-date без дня 1 | `formatPublicationDate` |
| PDF Bearer / не window.open / revoke | source contracts client + pdf helper |
| Маршрут | `AppRoutes` |
| Typecheck + bundle | `npm run build` |

## Ограничения

- Нет e2e / screenshot / CDP.
- Нет мобильного Flutter UI в этом этапе (только web).
- Backend не расширялся.
- Качество live-генерации цитат не оценивалось.

**Стоп этапа 2.15.**
