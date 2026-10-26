# Аспект — Frontend

Публичный сайт (React + TypeScript + Vite).  
Прод: https://gadzhilaev.ru/aspekt/ (base path `/aspekt/`).

В этом репозитории рядом:

```text
aspect/
  lib/         ← Flutter
  backend/     ← FastAPI
  frontend/    ← этот каталог
```

Общий API: `/api/v1` (на проде — `https://gadzhilaev.ru/aspekt-api`).

## Локальный запуск

```bash
cp .env.example .env
# VITE_API_BASE_URL=http://127.0.0.1:8003
npm ci
npm run dev
```

Прод-сборка (как на сервере):

```bash
# VITE_API_BASE_URL=https://gadzhilaev.ru/aspekt-api
npm ci
npm run build
# артефакт: dist/ → раздаётся nginx с location /aspekt/
```

Секреты в `VITE_*` не кладём — только публичный base URL API.
