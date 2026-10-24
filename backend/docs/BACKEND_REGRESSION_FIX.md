# Backend regression fix (pre-commit)

Дата: **2026-10-24**  
Цель: воспроизводимый зелёный `pytest` без новых функций, без skip/xfail и без отключения FK.  
Commit/push **не** делались.

Полный отчёт: `data/competition_stand/handoff_reports/pytest_regression_fix.txt` (gitignore).

---

## Итог полного прогона (чистый process env, `-ra`)

| Метрика | Значение |
|---------|----------|
| Result | **698 passed**, **4 skipped**, **0 failed** |
| Live LLM / live Telegram | не вызывались |
| Длительность | ~3m 51s |

### Skipped (все 4 — нет `ALEMBIC_POSTGRES_URL`)

| Node ID | Причина |
|---------|---------|
| `tests/test_alembic_smoke.py::test_alembic_upgrade_head_on_empty_postgres` | нужен disposable Postgres `*_test` |
| `tests/test_bank_schema.py::test_postgres_bank_schema_optional` | то же |
| `tests/test_case_schema.py::test_postgres_case_schema_optional` | то же |
| `tests/test_case_snapshot_activation.py::…` (concurrency) | то же |

---

## Failed node IDs до фикса (из handoff clean log)

1. `tests/test_acceptance.py::test_telegram_dedupe`
2. `tests/test_alembic_smoke.py::test_alembic_upgrade_head_on_empty_sqlite`
3. `tests/test_alembic_smoke.py::test_alembic_002_skips_existing_assistant_tables`
4. `tests/test_bank_schema.py::test_upgrade_head_from_scratch_sqlite`
5. `tests/test_bank_schema.py::test_upgrade_from_006_preserves_company_sqlite`
6. `tests/test_bank_schema.py::test_downgrade_007_then_reupgrade_sqlite`
7. `tests/test_case_schema.py::test_upgrade_head_from_scratch_sqlite`
8. `tests/test_case_schema.py::test_downgrade_006_then_reupgrade_sqlite`
9. `tests/test_frontend_routes_contract.py::test_decision_page_cancelled_ui_contract` (починен ранее в handoff)
10. `tests/test_hackathon_provider.py::test_no_openai_host_when_misconfigured_base`
11. `tests/test_impact_skips_unconfirmed_names.py::test_recompute_skips_unconfirmed_component`
12. `tests/test_manual_profile_feed.py::test_manual_profile_empty_feed_without_case_link`
13. `tests/test_manual_profile_feed.py::test_manual_profile_china_export_enters_feed`

После частичных фиксов в полном наборе всплыл ещё один (порядок/загрязнение):

14. `tests/test_personalization_ingestion.py::test_real_china_event_appears_in_dashboard_and_impact`  
    — только в полном наборе после того, как FK-фикстуры снова стали коммитить ready-компании.

---

## Дефекты и исправления

### 1. Alembic / SQLite

| Причина | Исправление |
|---------|-------------|
| Тесты ждали head `007`, факт `010` | `tests/_alembic_util.py`: `ALEMBIC_HEAD="010"` + проверка таблиц/колонок 008–010 (`subscription_id`/`kind`, nullable `severity`, `auto_notify_since`) |
| Windows `PermissionError` на temp `.db` | `NullPool` + `temp_sqlite_path` с `rmtree(..., ignore_errors=True)` после `dispose()` |
| Downgrade 008: `DROP COLUMN subscription_id` ломал FK/index на SQLite | `alembic/versions/008_…py`: batch alter — снять FK/index по inspector, затем колонки |
| Upgrade с нуля / с 005–006 с сохранением Company | обновлены bank/case migration-тесты на helper + `assert_head_schema` |

Рабочие БД / root `.env` не трогались.

### 2. Telegram dedupe (`count 0` вместо `1`)

| Причина | Исправление |
|---------|-------------|
| `TELEGRAM_NEWS_NOTIFICATIONS_ENABLED` по умолчанию false → enqueue 0 | тест включает флаг через monkeypatch |
| Seed `evt_china_export_001` — `is_demo=True` → `event_demo` | свежий non-demo risk event |
| Нет `auto_notify_since` → `watermark_missing` | `stamp_auto_notify_watermark` до публикации |
| Ожидание осталось `1` | два `recompute-impact` → одна `news` outbox; Impact score сохранён |

### 3. Provider misconfig codes

| Режим | Код |
|-------|-----|
| Normal (`require_competition_exact=False`) | `PROVIDER_MISCONFIGURED` |
| Competition exact / `COMPETITION_MODE` | `COMPETITION_MISCONFIGURED` |

HTTP на запрещённый host не выполняется. Добавлен отдельный competition-тест; обновлены loop/competition_profile asserts и `CLEAN_ENV_VERIFICATION.md`.

### 4. FK `company_edges`

| Причина | Исправление |
|---------|-------------|
| `Session.autoflush=False` + два FK на `company_nodes` → INSERT edges до nodes | явный `db.flush()` после nodes в impact/manual fixtures |
| Подтверждено изолированным скриптом (`FAIL without flush`) | FK остаются `PRAGMA foreign_keys=ON` |

### 5. Порядок тестов / personalization

После зелёных manual/impact ready-компании оставались в session DB → `recompute_event_for_ready_companies` матчил не только SeverProm → падал `all(...== COMPANY_ID)`.

Исправление: assert `COMPANY_ID in matched_ids`; cleanup компаний в impact/manual тестах.

---

## Ограничения (остаются)

- Код **не** закоммичен → не зафиксированный релиз.  
- Postgres alembic/concurrency — skipped без `ALEMBIC_POSTGRES_URL`.  
- Flutter E2E не прогонялся.  
- Compose без TG worker/polling (как в deployment handoff).  
- Публичный URL: будет задан после размещения.
