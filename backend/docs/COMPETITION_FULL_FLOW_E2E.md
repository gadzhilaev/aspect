# Единый конкурсный путь E2E (этап 6.10)

Дата: 2026-10-23  
Метод: **TestClient** на изолированной SQLite-копии стенда.  
Браузер / CDP / скриншоты / live LLM / CSV-reimport / commit/push — **нет**.  
**UI E2E по TestClient не заявляется.**

Связанные: `COMPETITION_JURY_RUNBOOK.md`, `COMPETITION_STAND_BOOTSTRAP.md`,
`BANK_EVIDENCE_EXPANSION.md`, `CASE_PERSONALIZED_FEED_CONTRACT_FIX.md`,
`USER_TRIGGERED_FINANCE_SCENARIOS.md`, `FINANCE_SETUP_RATE_FX.md`,
`ASSISTANT_AGENT_API_INTEGRATION.md`.

Машинный отчёт:  
`data/bank_materials/verification/e2e610/competition_full_flow_report.json`  
Манифест копии:  
`data/bank_materials/verification/e2e610/stand_copy_manifest.json`  
Скрипт: `scripts/run_competition_full_flow_e2e_610.py`

---

## 1. Изолированный стенд

| | |
|--|--|
| Источник | `data/bank_materials/verification/evidence_expansion_stand_copy.db` (QA 6.7) |
| Копия | SQLite `Connection.backup` → `…/e2e610/competition_full_flow.db` |
| AI-eligible fragments | **7** (Policy Rate 3 + Inflation 2 + Consumption 2) |
| Storage / OCR allow-list | из `jury_63b/stand.env` → `jury_63b/storage` |
| Профиль | `COMPETITION_MODE=true`, `ASSISTANT_PROVIDER=hackathon`, agent loop ON |
| Не трогались | `jury_63b/stand.db`, root `.env`, рабочая БД, `:8003`, CSV |

На work-копии для проверки observed hold vs what-if к синтетическому событию добавлены
числовые `rate_decision_status=observed`, `rate_from=rate_to=16` (в seed была только
нарративная формулировка «сохранение»). Impact в БД **не** вставлялся вручную.

Секреты / пароль в отчёт **не** пишутся.

---

## 2. Путь без финансовых данных

1. Login `competition-demo-a` → `GET /users/me` → компания U_264.  
2. `GET …/companies/{id}/context` → `case_context.status=profile_available`.  
3. `GET …/companies/{id}/events` → карточка **`case_profile_match`** (не Impact), синтетика
   ставки; `impact_score=null` / `available=false`. ID **не** подставлялся вместо обнаружения.  
4. `GET …/impact` → 404; обсуждение → `calculation_unavailable`, без фиктивных нулей.  
5. Agent loop со **scripted** FakeTransport (`get_bank_evidence` → final + citations).  
   COMPETITION_MODE / hackathon **не** переключались на mock.  
6. История, fragment, PDF content + SHA.

Scripted-ответ доказывает связность API, **не** качество live-модели.

---

## 3. Переход к расчёту и решению

Синтетический ручной `PATCH …/finance`: долг, `RUB`, доля плавающей ставки — **не** из LOA /
выручки / платежей. Конкурсный case_context остаётся различим (`source_note` в optional_finance).

Явный путь usable Impact (после 6.10.1 — **без двойного пересчёта**):

1. `PATCH …/finance` — только сохранение (+ refresh **существующих** Impact).  
2. `POST …/recompute-impact` — **один** create/update для текущего события (UI после CTA).  
3. `POST …/compare-scenarios` — observed hold отдельно от `assumed_rate_change_pp`.  
4. Расчёт **без** model HTTP.  
5. Выбор сценария → draft (`confirm=false`) → **не** accepted.  
6. `confirm=true` → DecisionDetail; после повторного login — история и решение.

Контракт: `docs/FINANCE_RECOMPUTE_FLOW_FIX.md`.  
Синтетический hold **16%** ≠ цитата Policy Rate (~14%) — разные контексты.

---

## 4. Найденные разрывы и минимальные исправления

| Разрыв | Исправление |
|--------|-------------|
| UI без `?event=` / без recompute | `financeSetupPath` + один `recomputeImpact` → обсуждение |
| PATCH создавал Impact по всем matching + UI дублировал | PATCH снова только existing; create — только POST recompute |
| Пустые twin-узлы → всегда NOT_RELEVANT | rate/FX-контекст профиля (не только purchase_currencies) → `feature_match` |

LOA/DEP rules **не** расширялись.

---

## 5. Целостность (факт отчёта)

- Повтор compare с тем же `client_request_id` → `reused=true`, без дублей Scenario.  
- Другой payload с тем же id → **409**.  
- Повтор confirm → тот же `decision_id`, одна строка Decision.  
- Пользователь B → 403/404 на чужие conversation / compare / Decision.  
- GET events/impact/dashboard не создают Scenario/Decision.  
- После Impact — одна карточка события в ленте (без дубля profile+impact).  
- Pinned bank-сообщения не переписываются после смены finance.  
- **model HTTP live: 0** (scripted FakeTransport только на agent loop).

---

## 6. Что остаётся вручную

- Клики UI на портах жюри (finance CTA → save → compare → confirm).  
- Live hackathon-модель с реальным ключом (не scripted).  
- Визуальная вёрстка DecisionDetail / ForYou.

---

## 7. Запуск

```powershell
python scripts/run_competition_full_flow_e2e_610.py
```
