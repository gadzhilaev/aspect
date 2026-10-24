# Competition Docker stack (этап 6.5)

Дата: **2026-10-23**  
Назначение: воспроизводимый **конкурсный** compose (frontend + API + one-shot bootstrap)  
с постоянным SQLite/PDF storage. **Не** заменяет `docker-compose.yml` (Postgres demo).

---

## 0. Статус на этой машине (честно)

Актуализация **этап 6.14** — см. `docs/COMPETITION_DOCKER_VERIFICATION.md`.

| Утверждение | Статус |
|-------------|--------|
| Конфигурация существует | **Да** |
| Docker CLI / Compose / Engine | **Да** (CLI/Server 29.9.2, Compose v5.6.1, Linux/WSL2 x86_64) |
| Build images (API + web) | **PASS** (`kontur_comp_smoke_614`) |
| Установка Linux deps из `requirements-linux.lock` | **PASS** (после pin `uvloop==0.23.0`) |
| Контейнерный smoke на fixtures | **PASS** (ports 18080/18019) |
| Restart + сохранность volume | **PASS** |
| Полный реальный импорт в Docker | **Не пройден** (отдельный уровень) |
| Live LLM в Docker | **Не вызывался** |

---

## 1. Файлы

| Путь | Роль |
|------|------|
| `docker-compose.competition.yml` | api + web + profile `bootstrap` |
| `docker/competition/Dockerfile.api` | Python 3.12.10-slim-bookworm + hashed Linux lock |
| `docker/competition/Dockerfile.web` | Node 24.19.0 build → nginx 1.27.5-alpine |
| `docker/competition/nginx.conf` | same-origin `/api`, SPA fallback, proxy 120s |
| `docker/competition/entrypoint-api.sh` | читает `/stand`, **без** import/seed |
| `docker/competition/entrypoint-bootstrap.sh` | one-shot preflight/bootstrap |
| `.dockerignore` | исключает `.env`, data/, venv, node_modules, `*.db`… |
| `.env.competition.example` | шаблон runtime env (не ключ в image) |
| `requirements-linux.lock` | manylinux2014_x86_64 / cp312 hashed lock |
| `scripts/materialize_competition_docker_smoke_inputs.py` | tiny inputs для smoke |
| `scripts/verify_competition_docker_static.py` | static gate без Docker |

Базовые теги зафиксированы; **digest/immutability не утверждается**.

---

## 2. Linux lock vs Windows lock

| | `requirements.lock` | `requirements-linux.lock` |
|--|---------------------|---------------------------|
| Источник pins | `requirements.in` | тот же `requirements.in` |
| Compile | Windows host (6.4) | Windows host + `--platform manylinux2014_x86_64 … --only-binary=:all:` (6.5) |
| Версии прямых пакетов | fastapi 0.115.6, pypdf 5.4.0, … | те же |
| Hashes | multi-file / multi-platform | Linux wheels (+ `--only-binary :all:`) |
| Install verified | Windows venv | **да** в Docker API image (6.14; + pin `uvloop`) |

Windows lock **не** считается проверенным для Linux.  
Массового bump пакетов не было; hash-проверка сохранена (`pip install --require-hashes`).

Frontend: `npm ci` из `web/package-lock.json`, затем `npm run build` (не Vite dev).

---

## 3. Volume layout

```
volume competition_stand_data  →  /stand
  stand.db
  storage/          # PDF + OCR artifacts (loader keys)
  stand.env         # profile without HACKATHON_API_KEY
  stand_manifest.json
  stand_status.json
  demo_password.local
  reports/

host COMPETITION_INPUTS_DIR  →  /inputs:ro
  csv/
  pdf/
  ocr/
  qa/
```

Bootstrap и API используют **одни и те же** `/stand` пути.  
API **не** запускает импорт при рестарте (только uvicorn после проверки `stand_status=ready`).

---

## 4. Конфигурация / секреты

В runtime API:

- `COMPETITION_MODE=true`
- `ASSISTANT_PROVIDER=hackathon`
- `ASSISTANT_AGENT_LOOP=true`
- `HACKATHON_MODEL=deepseek/deepseek-v4.1-flash` (allow-list)
- `HACKATHON_API_KEY` — только compose/runtime env, **не** build-arg, **не** frontend, **не** image layers
- CASE slot / OCR run IDs / storage — из подготовленного `stand.env` (переписанного на `/stand/...`)

Браузер → `http://localhost:8080` → nginx `/api` → `api:8000`  
(не `http://api:8000` в JS). `VITE_API_BASE_URL` пустой (same-origin).

Proxy `proxy_read_timeout 120s` ≥ `ASSISTANT_LOOP_TIMEOUT_S=90`.

Healthcheck: `GET /health` / `/healthz` — без model HTTP.

---

## 5. Команды — маленький синтетический smoke

Требуется Docker Desktop / Engine + Compose plugin.  
На этой машине smoke fixtures прогнан в 6.14 (проект `kontur_comp_smoke_614`, порты 18080/18019).

```powershell
# 0) Host: синтетические входы (без полного CSV/PDF организаторов)
python scripts/materialize_competition_docker_smoke_inputs.py
copy .env.competition.example .env.competition
# правьте COMPETITION_INPUTS_DIR / UIDS; ключ можно не задавать для offline smoke

# 1) Build
$env:COMPOSE_PROJECT_NAME = "kontur_comp_smoke"
$env:COMPETITION_STAND_VOLUME = "kontur_comp_smoke_stand_data"
$env:COMPETITION_INPUTS_DIR = (Resolve-Path .\data\competition_docker_smoke\inputs).Path
$env:COMPETITION_EXTERNAL_UIDS = "U_900001 U_900002"
docker compose -f docker-compose.competition.yml --env-file .env.competition build

# 2) Preflight (понятная ошибка при пустых входах)
$env:COMPETITION_BOOTSTRAP_MODE = "preflight"
docker compose -f docker-compose.competition.yml --env-file .env.competition --profile bootstrap run --rm bootstrap

# 3) One-shot bootstrap → volume
$env:COMPETITION_BOOTSTRAP_MODE = "bootstrap"
docker compose -f docker-compose.competition.yml --env-file .env.competition --profile bootstrap run --rm bootstrap

# 4) Start api+web
docker compose -f docker-compose.competition.yml --env-file .env.competition up -d api web

# 5) Checks (no live LLM)
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8019/health
# login / context / bank / PDF — TestClient or curl with Bearer from demo_password.local in volume
# deep-link: curl -I http://127.0.0.1:8080/some/spa/route  → 200 + index.html

# 6) Restart without data loss
docker compose -f docker-compose.competition.yml --env-file .env.competition restart api web
# re-check DB/PDF still present

# 7) Re-bootstrap same inputs → no-op (no duplicates)
docker compose -f docker-compose.competition.yml --env-file .env.competition --profile bootstrap run --rm bootstrap

# 8) Stop smoke project ONLY (do NOT use -v if you need to keep volume; -v deletes named volume)
docker compose -f docker-compose.competition.yml --env-file .env.competition down
# optional explicit volume remove for smoke only:
# docker volume rm kontur_comp_smoke_stand_data
```

**Не** выполнять `docker compose down -v` над чужими/jury volumes.  
Проект smoke: `kontur_comp_smoke` — отдельное имя.

---

## 6. Команды — полный комплект организаторов

Не гонялись в 6.5. После появления Docker:

```powershell
$env:COMPOSE_PROJECT_NAME = "kontur_competition"
$env:COMPETITION_STAND_VOLUME = "kontur_competition_stand_data"
$env:COMPETITION_INPUTS_DIR = "<host path with csv/pdf/ocr/qa>"
$env:COMPETITION_EXTERNAL_UIDS = "U_264 U_92"
# HACKATHON_API_KEY only if live turns needed after UI is up
docker compose -f docker-compose.competition.yml --env-file .env.competition --profile bootstrap run --rm bootstrap
docker compose -f docker-compose.competition.yml --env-file .env.competition up -d api web
```

Полный case import (~1.38M payments) долгий — ожидайте как на native 6.3 (~17 мин на этой машине).  
Образы **не** содержат CSV/PDF/секреты.

---

## 7. Static verification (выполнено)

```text
python scripts/materialize_competition_docker_smoke_inputs.py  → ok
python scripts/verify_competition_docker_static.py           → STATIC_OK
```

---

## 8. Ограничения

- Нет автоматического «одного клика» без входов и (для live) ключа.  
- HTTP `/healthz` ≠ визуальная проверка UI.  
- Старый `docker-compose.yml` (Postgres+worker) **не** конкурсный стек.  
- Публикация образов / digests / multi-arch — вне 6.5.
