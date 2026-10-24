# Assessment trust audit — достоверность оценок влияния

Дата: 2026-10-19 (дополнение: score_kind / demo override / null≠0)  
Область: backend impact/simulator + web ImpactPanel/assistant. Flutter-контракт сохранён (аддитивные поля).

## 1. Что реально означают метрики

| Метрика | Смысл | Единица / диапазон | Источник |
|---|---|---|---|
| `impact_score` + `score_kind` | См. виды ниже | 0…100 | Формула twin **или** triage от severity |
| `confidence` | **Качество данных** — эвристика | 0…1 | `0.55×source_quality + 0.45×edge_confidence` |
| `exposure` | **Доля выпуска, связанная с затронутым узлом** | % или `null` | `CompanyNode.output_share_percent` на конце пути |
| `stop_risk_percent` | **Модельная оценка риска остановки** | 0…100 (индекс) | `share × (0.35 + 0.65×uncovered/delay)` |
| Финансовые pressure / FX index | Модельные индексы давления | 0…100 | `financial_simulator` |

### Виды `score_kind`

| `score_kind` | Лейбл UI | Когда | Что это **не** |
|---|---|---|---|
| `company_calculated` | Индекс влияния | `supply_chain_ready` | % потерь, вероятность убытка |
| `event_severity_signal` | Сигнал события | finance_* / monitoring_only | Персональный расчёт по компании, финансовый эффект |
| `unavailable` | Оценка недоступна | (резерв) | Любое утверждение о влиянии |

**Совместимость:** поле `impact_score` сохранено для Flutter и сортировки ленты. Для `event_severity_signal` это triage-proxy от `severity` (×0.5 / ×0.55 / ×0.4), **не** рассчитанный индекс влияния. Клиенты должны читать `score_kind` / `metric_labels.impact_score`.

### Ранжирование ленты

`GET .../dashboard` и `.../events` сортируют по `impact_score DESC` **независимо от `score_kind`**.  
Правило: удобный triage (сначала более «громкие» числа), а **не** утверждение, что все значения одинаково обоснованы. Карточки с `event_severity_signal` помечены лейблом «Сигнал события» / статусом «Мониторинг» / «Нужны финансы».

### exposure: null vs 0

| Значение | Смысл |
|---|---|
| `null` | Доля неизвестна или неприменима (нет supply-chain расчёта) |
| `0` | Известная нулевая доля выпуска |
| `> 0` | Известная положительная доля |

`has_exposure` в `resolve_assessment_state` = «значение известно» (`is not None`), включая `0.0`. Проверка `> 0` для наличия данных **не** используется.

### confidence

Эвристика, не измеренная точность и не вероятность.  
Defaults при отсутствии источников: `source_quality=0.4`; при отсутствии рёбер: `edge_confidence=0.5` — фиксируются в `confidence_detail` (`*_defaulted=true`) и в тексте «Как рассчитано». Веса **не** менялись.

## 2. Найденные и исправленные дефекты

1. **Экспозиция как «потери»** — лейбл и path explanation уточнены.
2. **Уверенность как вероятность** — лейбл «Качество данных»; эвристика и defaults в explanation.
3. **Индекс как влияние/%** — лейблы + `score_kind`.
4. **stop_risk как вероятность** — `stop_risk_kind=model_index`.
5. **0 vs missing** — finance/monitoring хранят `exposure_value=None`; share `0.0` сохраняется как ноль; нет truthiness-проверок для наличия метрики.
6. **Формула в breakdown** — веса из config; убран soft-scale `×(100/24)`.
7. **Пустые paths → «цепочка найдена»** — mock provider.
8. **Согласованность объяснения** — `assessment_basis` + `assessment_explanation`.
9. **Finance/monitoring placeholder как «индекс влияния»** — `score_kind=event_severity_signal`, UI/assistant/«Как рассчитано» синхронизированы.
10. **Demo China ×3.5** — удалён; единая формула для demo и real. В basis: `demo_score_override.applied=false`.

## 3. Изменения формул

- Удалены: soft-normalize `exposure × (100/24)` и special-case `evt_china_export_001 × 3.5` (+ фиксированные dependency/proximity).
- Единая формула: `w_s×severity + w_e×min(100, share) + w_d×dependency + w_p×proximity`.
- Веса confidence без изменений.
- Версия модели: `impact-v1.1` (старые записи без пересчёта не переписываются; legacy explanation с `basis_available=false`).

Число для China demo после пересчёта **может отличаться от прежних ~87** — это ожидаемо.

## 4. Согласованность результата и объяснения

- Снимок `assessment_basis` содержит: `score_kind`, `confidence_detail`, `demo_score_override`, metrics, calculation, limitations.
- UI «Как рассчитано», ImpactPanel, ForYou-карточка, блоки ассистента и context используют тот же `score_kind` / лейблы.
- Старые сообщения ассистента и подтверждённые решения **не** переписываются.
- Legacy impact без basis: честное «основание неизвестно», без подстановки нового метода под старое число.

## 5. Совместимость API с Flutter

Аддитивные поля (старые клиенты игнорируют):

- `score_kind`, `score_kind_label` на `EventCardOut` / `ImpactOut` / `AssessmentExplanationOut`
- `assessment_explanation.confidence_detail`, `demo_score_override`
- `metric_labels` (лейбл `impact_score` зависит от kind)

Сохранены: `impact_score`, `confidence` 0…1, `exposure.value` (или отсутствие объекта).  
**Ограничение старого поля `impact_score`:** без `score_kind` нельзя отличить персональный индекс от triage-сигнала — мобильным клиентам рекомендуется читать новые поля.

## 6. Проверки и ограничения

### Проверки
- `tests/test_assessment_trust.py` — finance placeholder, demo override, exposure 0 vs null, confidence defaults, score_kind в API/assistant, ACL.
- Полный `pytest` + `npm run build` (web).

### Оставшиеся ограничения
- Лента по-прежнему сортирует смешанные `score_kind` одним числом (документировано).
- Финансовый `shock` — эвристический proxy severity (отдельный симулятор).
- Live LLM не покрыт unit-тестом.
- Старые impact-строки / сообщения чата без нового basis не пересчитываются массово.
- Маркетинговые статичные «87» на about/home не являются live-оценкой.
