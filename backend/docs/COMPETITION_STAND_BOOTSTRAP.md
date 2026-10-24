# Competition stand bootstrap (этап 6.3)

Дата: 2026-10-22  
Назначение: **новая** SQLite-стенд БД из явных файлов конкурса — без копирования verification/E2E DB, без переноса чужой AI-истории, без live LLM.

Этап проверяет **подготовку данных в текущей среде**, не clean-machine установку и не Docker.

---

## 1. Входной комплект

| Вход | Содержание | Пример локального пути |
|------|------------|------------------------|
| CSV dir | Ровно 3 роли: companies / payments / person_links | `data/case/raw/` |
| PDF dir | Исходные банковские PDF | `data/bank_materials/raw/` |
| OCR dir | Per-document `manifest.json`, pages, `fragments.json` | `data/bank_materials/ocr/` |
| QA dir | JSON `artifact_kind=bank_fragment_qa_revisions` | `data/bank_materials/verification/policy_rate_qa/` или расширенный набор `…/competition_qa_expanded/` (Policy Rate + инфляция + потребление, этап 6.7) |
| Output dir | **Новый** каталог стенда | `data/competition_stand/jury_63b/` |
| U_ID | 1–2 реальных `U_\d+` из companies CSV | `U_264`, `U_92` |

**Не** являются входами: `verification/e2e*/*.db`, `agent_demo.db`, сохранённые чаты, API keys.

Доступ к CSV/PDF **не** означает право публичного распространения. В Git они gitignored.

### Переносимый OCR/QA-пакет (опционально)

```powershell
python scripts/pack_competition_bank_artifacts.py `
  --ocr-dir data/bank_materials/ocr `
  --pdf-dir data/bank_materials/raw `
  --qa-dir data/bank_materials/verification/policy_rate_qa `
  --pack-dir data/competition_stand/packs/bank_ocr_qa_local `
  --slug ALFA-Macro_Insights-Policy_Rate_11Sep
```

Пакет: относительные пути + SHA в `pack_manifest.json`. Без БД/ключей/аккаунтов/логов.  
Verification statuses / цитаты / даты **не** меняются. Не публикуется автоматически.

---

## 2. Команды

### Preflight (без БД)

```powershell
python scripts/bootstrap_competition_stand.py --preflight-only `
  --csv-dir data/case/raw `
  --pdf-dir data/bank_materials/raw `
  --ocr-dir data/bank_materials/ocr `
  --qa-dir data/bank_materials/verification/policy_rate_qa `
  --external-uid U_264 --external-uid U_92
```

При нехватке файлов — список `MISSING` с kind/path/detail. Импорт не начинается.

### Полная подготовка

```powershell
python scripts/bootstrap_competition_stand.py `
  --csv-dir data/case/raw `
  --pdf-dir data/bank_materials/raw `
  --ocr-dir data/bank_materials/ocr `
  --qa-dir data/bank_materials/verification/policy_rate_qa `
  --output-dir data/competition_stand/jury_63b `
  --external-uid U_264 --external-uid U_92
```

Повтор с теми же входами и `stand_status=ready` → **no-op**.  
Занятый каталог с иным содержимым → отказ (выберите новый `--output-dir`).  
Автоматический repair/resume **нет**.

Пароль: только `demo_password.local` (gitignore). Значение **не** печатается и не попадает в manifest.

### Проверка без model HTTP

```powershell
python scripts/verify_competition_stand.py --stand-dir data/competition_stand/jury_63b
# опционально перенос каталога:
python scripts/verify_competition_stand.py `
  --stand-dir data/competition_stand/jury_63b `
  --relocate-to data/competition_stand/jury_63b_relocated
```

---

## 3. Что делает bootstrap (существующие сервисы)

1. Preflight входов + SHA PDF↔OCR↔QA fingerprint  
2. Новая SQLite + `alembic upgrade head`  
3. `run_case_import` → ready → `run_activation`  
4. `run_bank_materials_load` (storage_root = `output/storage`, staging **не** удаляется)  
5. `run_apply_qa_revisions` для QA-артефактов  
6. Demo User/Company/membership (`Демо-компания A · U_…`) + `run_link`  
7. Синтетическое событие Policy Rate route (`is_demo`, **без** EventImpact, **без** истории чата)  
8. `stand_manifest.json` / `stand.env` / `stand_status.json=ready` только после всех проверок  

Bank scope (`BANK_MATERIALS_ALLOWED_OCR_RUN_IDS`) и case slot берутся из **результата импорта**, не из UUID старого стенда.

---

## 4. Происхождение частей стенда

| Часть | Происхождение |
|-------|----------------|
| Каталог org / payments / links | Конкурсные CSV |
| Банковские PDF + OCR fragments | Конкурсные материалы + локальный OCR corpus |
| QA revisions (Policy Rate) | Явный QA artifact |
| Demo login / membership | Демо-настройка bootstrap |
| Company display name | `Демо-компания A · U_…` (не выдуманное юр. имя) |
| Событие | Синтетика для маршрута Policy Rate |
| AI chat history | **Нет** — первый live-ответ отдельным действием |
| Supply-chain twin | **Не** строится из платежей/ФТС |

Пометки: профиль/case — конкурсные данные; аккаунт/membership/событие — демонстрационные.

---

## 5. Фактический прогон (эта машина, 2026-10-22)

| | |
|--|--|
| Output | `data/competition_stand/jury_63b` |
| U_ID | `U_264`, `U_92` |
| Время | **~1019 s** (~17 мин): case_import ≈1007 s, bank ≈11 s, остальное <1 s |
| Статус | `ready` |
| Verify | `ok=true`, `model_http_attempts=0` |
| Relocate | `jury_63b_relocated` — storage keys без изменения, verify ok |
| e2e DB | **не** использовалась (`source_e2e_db_used=false`) |

Фикстурные тесты: `tests/test_competition_stand_bootstrap.py` — 7 passed.

### Исправление loader (6.3)

При `storage_root` loader больше **не** удаляет staged PDF/OCR после импорта (раньше cleanup ломал download). Для уже собранного `jury_63b` storage восстановлен `scripts/_repair_stand_storage.py` (разовый).

---

## 6. Ограничения

- Clean-env **на этой Windows** с install из lock — этап **6.4** (`docs/CLEAN_ENV_VERIFICATION.md`).  
- Competition Docker **конфиг** — этап **6.5** (`docs/COMPETITION_DOCKER.md`); build/smoke на этой машине не прогонялись (нет Docker CLI).  
- AI evidence в маршруте — Policy Rate (QA).  
- При `ASSISTANT_AGENT_LOOP=true` finance write-tools недоступны.  
- Частичный каталог `jury_63` (прерванный/занятый) **не** перезаписывался — использован новый `jury_63b`.  
- Доказательство storage 6.4 — fixture bootstrap **без** `_repair_stand_storage.py` (repair остаётся разовым для старого `jury_63b`).
