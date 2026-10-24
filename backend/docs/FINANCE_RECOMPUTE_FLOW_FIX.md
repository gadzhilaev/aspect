# Контракт сохранения финансов и пересчёта Impact (этап 6.10.1)

Дата: 2026-10-23  
Связанные: `COMPETITION_FULL_FLOW_E2E.md`, `FINANCE_SETUP_RATE_FX.md`,
`USER_TRIGGERED_FINANCE_SCENARIOS.md`, `CASE_PERSONALIZED_FEED_CONTRACT_FIX.md`.

Браузер / live LLM / root `.env` / `:8003` / commit — нет.  
Повтор серверного E2E 6.10: `scripts/run_competition_full_flow_e2e_610.py` → pass.

---

## 1. Один явный путь пересчёта

### Контракт API

| Шаг | Endpoint | Эффект |
|-----|----------|--------|
| Сохранение профиля | `PATCH /companies/{id}/finance` | Merge `optional_finance` + replace `purchase_currencies`. **Обновляет только уже существующие** macro/FX `EventImpact` (assessment_state). **Не** создаёт Impact для новых событий. **Не** сканирует весь корпус новостей. |
| Пересчёт текущего события | `POST /events/{id}/recompute-impact?company_id=` | Единственное место **создания** usable Impact для выбранного события (после gate `event_matches`). |
| Расчёт сценариев | `POST …/compare-scenarios` | Без LLM; не трогает старые Decision. |

`GET` dashboard / events / impact — **read-only** (без lazy recompute).

### Контракт UI (мастер финансов)

1. CTA → `/company/setup?step=finance&event={eventId}`.  
2. «Сохранить и пересчитать оценку» → `PATCH finance` → **один** `POST recompute-impact` → переход к обсуждению (`/events/{id}/assistant`).  
3. Частичный сбой (профиль сохранён, recompute 4xx/5xx): честное сообщение; кнопка **«Повторить пересчёт оценки»** без повторного `PATCH`; ссылка «Вернуться к обсуждению».

Двойного пересчёта одного события (PATCH-create + UI recompute) **нет**.

---

## 2. Финансовая релевантность без twin-узлов

`feature_match` для macro/FX **не** требует `purchase_currencies` для любого события.

| Профиль | Событие | Ожидание |
|---------|---------|----------|
| Кредит RUB + floating share, purchase=[] | rate / policy_rate (RUB) | `feature_match` (axis `finance_rate`) |
| FX payment CNY | FX-событие CNY | `feature_match` (`finance_fx`) |
| FX receipt CNY | FX-событие CNY | то же |
| FX payment CNY | событие USD | `not_relevant` |
| Неполный кредит (нет floating share) | rate | `not_relevant` |
| Пустой finance (только LOA/DEP) | rate | `not_relevant` для twin-gate; лента может показать `case_profile_match` отдельно |

`purchase_currencies ∩ event.match_currencies` по-прежнему открывает `feature_match` (axis `currency`).

**Не** является `company_calculated` (supply-chain).  
Профильная лента (LOA/DEP), готовность `finance_ready` / `finance_data_required` и основание события (observed / what-if) — **разные** понятия.

---

## 3. Синтетическая ставка 16% vs банк ~14%

В E2E observed hold события задан как **16→16** (синтетика).  
Pinned Policy Rate относится к материалу банка (контекст ~14%).  
Цитата банка **не** подтверждает синтетические 16% — разные событие и источник.

---

## 4. Регрессии (факт)

```powershell
pytest tests/test_finance_relevance_no_nodes.py `
  tests/test_finance_setup_rate_fx.py `
  tests/test_user_triggered_finance_scenarios.py `
  tests/test_personalization_proof.py -q

python scripts/run_competition_full_flow_e2e_610.py

cd web
npm run test:finance-recompute-cta
npm run build
```

Проверено: один путь → один create Impact; GET без записи; hold vs what-if; conflict/idempotency compare; ACL; история/pinned immutable; score_kind ≠ `company_calculated` для finance-only.
