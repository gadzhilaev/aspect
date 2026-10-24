# Проверка конкурсного Docker-запуска (этап 6.14)

Дата: **2026-10-24**  
Цель: фактически прогнать существующий `docker-compose.competition.yml`  
(build → smoke fixtures → bootstrap → HTTP → restart). Новая инфраструктура не создавалась.

Связанные: `COMPETITION_DOCKER.md`, `COMPETITION_JURY_RUNBOOK.md`, `CLEAN_ENV_VERIFICATION.md`.

---

## 1. Среда и версии

| | |
|--|--|
| OS host | Windows 10/11 (build 10.0.26200), win_amd64 |
| Docker CLI | **29.9.2** |
| Compose plugin | **v5.6.1** |
| Engine / Server | **29.9.2** (Docker Desktop, Linux/WSL2, x86_64) |
| Context | `desktop-linux` |
| Smoke project | `kontur_comp_smoke_614` |
| Volume | `kontur_comp_smoke_614_stand_data` |
| Ports | web **18080**, api **18019** |
| Images | `kontur-competition-api:local` (~350MB), `kontur-competition-web:local` (~74.5MB) |

```powershell
docker info --format "Server={{.ServerVersion}} OS={{.OperatingSystem}} Arch={{.Architecture}}"
# → Server=29.9.2 OS=Docker Desktop Arch=x86_64
```

Первая попытка 6.14 (2026-10-23) остановилась на `Docker Desktop is unable to start`.  
После запуска Engine проверка продолжена.

---

## 2. Точные команды (выполнены)

```powershell
python scripts/materialize_competition_docker_smoke_inputs.py
# .env.competition (gitignored): project/volume/ports/UIDs; HACKATHON_API_KEY пустой

$env:COMPOSE_PROJECT_NAME = "kontur_comp_smoke_614"
$env:COMPETITION_STAND_VOLUME = "kontur_comp_smoke_614_stand_data"
$env:COMPETITION_INPUTS_DIR = (Resolve-Path .\data\competition_docker_smoke\inputs).Path
$env:COMPETITION_EXTERNAL_UIDS = "U_900001 U_900002"
$env:COMPETITION_WEB_HOST_PORT = "18080"
$env:COMPETITION_API_HOST_PORT = "18019"
$env:COMPETITION_BOOTSTRAP_MODE = "bootstrap"

docker compose -f docker-compose.competition.yml --env-file .env.competition config --quiet
docker compose -f docker-compose.competition.yml --env-file .env.competition build
docker compose -f docker-compose.competition.yml --env-file .env.competition --profile bootstrap run --rm bootstrap
docker compose -f docker-compose.competition.yml --env-file .env.competition up -d api web

python scripts/verify_competition_docker_smoke_614.py
# → ok=true

docker compose -f docker-compose.competition.yml --env-file .env.competition restart api web
python scripts/verify_competition_docker_smoke_614.py
# → ok=true; counts/PDF SHA без изменений
```

Остановка smoke-проекта (**без** `-v`, volume сохраняется):

```powershell
docker compose -f docker-compose.competition.yml --env-file .env.competition down
# опционально только этот volume: docker volume rm kontur_comp_smoke_614_stand_data
```

---

## 3. Результат build

| | |
|--|--|
| API image | **PASS** — `pip install --require-hashes -r requirements-linux.lock` + `pip check` |
| Web image | **PASS** — `npm ci` + `npm run build` → nginx |
| Linux deps в образе | **PASS** (в т.ч. после фикса `uvloop`) |

### Исправление lock (необходимо для build)

Первый build API упал:

```text
ERROR: In --require-hashes mode, all requirements must have their versions pinned with ==.
    uvloop!=0.15.0,!=0.15.1,>=0.14.0  (from uvicorn[standard])
```

Причина: `requirements-linux.lock` не содержал pinned `uvloop` (Linux-only transitive  
`uvicorn[standard]`; Windows-lock его не видит).

Исправлено:

- `requirements-linux.lock` — добавлен `uvloop==0.23.0` + sha256 wheel manylinux;
- `requirements.in` — явный `uvloop==0.23.0; sys_platform != "win32"` для будущих compile.

Повторный `docker compose … build` — **успех**.

---

## 4. Результат container smoke (fixtures)

Входы: `data/competition_docker_smoke/inputs` (tiny CSV U_900001/U_900002 + синтетический Policy Rate PDF/OCR/QA).  
**Не** полный конкурсный CSV. **Не** live LLM (`HACKATHON_API_KEY` пустой, provider=hackathon).

Bootstrap: `status=ready`, `noop=false`, ~1.8s (case+bank+demo seed).

HTTP (same-origin через nginx `:18080` + прямой API `:18019`), отчёт  
`data/competition_docker_smoke/smoke_614_report.json` (gitignore):

| Проверка | Результат |
|----------|-----------|
| `GET /healthz` (web) | PASS |
| `GET /health` (api + proxied) | PASS |
| Frontend `/` | PASS |
| SPA deep-link `/news/for-you` | PASS |
| same-origin `/api/v1/public/news` | PASS (1 item) |
| login + `/users/me` ACL | PASS |
| foreign company denied | PASS |
| company context (U_90000*) | PASS |
| personal feed + dashboard | PASS |
| bank fragment + document | PASS |
| PDF Bearer + SHA match | PASS (`6d6a56fd…622ce1`) |
| PDF без auth → 401/403 | PASS |
| event bank-evidence | 200/404 OK |
| Live model HTTP | не вызывался |

Скрипт: `scripts/verify_competition_docker_smoke_614.py`  
(`httpx` с `trust_env=False` — иначе системный proxy на Windows перехватывает `127.0.0.1` → 503).

---

## 5. Перезапуск и сохранность данных

```text
BEFORE/AFTER restart api+web (одинаково):
  users=2 companies=2 events=1 bank_fragments=6 bank_document_files=1
  pdf_n=1 pdf0_sha=6d6a56fd6753c0b6a729a916005f643ca11208a2f3074f4391cd3abfaa622ce1
  stand_status=ready
```

Повторный HTTP smoke после restart — **PASS**.  
Импорт при restart **не** запускался (entrypoint-api только uvicorn).

---

## 6. Найденные исправления

| Проблема | Исправление |
|----------|-------------|
| `uvloop` unpinned в Linux lock → API build fail | pin `uvloop==0.23.0` в `requirements-linux.lock` + marker в `requirements.in` |
| Windows system proxy → httpx 503 на localhost | `trust_env=False` в smoke-скрипте |
| `docker run api-image …` без `--entrypoint` зависал на uvicorn | smoke читает SQLite только с `--entrypoint python` |

Compose / nginx / entrypoints менять не потребовалось.

---

## 7. Что не проверено (разделение уровней)

| Уровень | Статус |
|---------|--------|
| Static config (6.5) | Ранее STATIC_OK |
| **Container smoke на fixtures** | **PASS (этот этап)** |
| Полный импорт реальных CSV/PDF организаторов в Docker | **Не** выполнялся |
| Live AI / hackathon gateway HTTP | **Не** вызывался |
| Публикация образов / digests / multi-arch | вне scope |
| Локальные native стенды (`ui_acceptance_611`, `real_news_613`) | не переключались |

Root `.env`, исходные БД, чужие Docker volumes / `docker system prune` — **не** трогались.
