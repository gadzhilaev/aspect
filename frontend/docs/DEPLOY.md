# Деплой web-фронта Аспект

## Что в архиве

React + Vite + nginx (`Dockerfile`). API проксируется same-origin: `/api` → backend.

Поддержка: страница `/support` (Настройки → «Чат поддержки»), API `/api/v1/support/*`.

## Минимальный продакшен-стек

1. **VPS** (1–2 vCPU, 2 GB RAM) — Hetzner / Timeweb / Selectel.
2. **Домен** → A-запись на IP сервера.
3. **Docker Compose**: сервис `api` (backend) + `web` (этот frontend).
4. **TLS**: Caddy или Traefik / nginx + Let’s Encrypt на `https://ваш-домен`.

В Docker-сборке `VITE_API_BASE_URL` пустой — браузер ходит на тот же хост `/api/...`.

Пример переменных API (не в git): `SECRET_KEY`, `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `SUPPORT_OPERATOR_CHAT_IDS`, `HACKATHON_API_KEY`, `CASE_CONTEXT_SLOT_KEY`.

## Локальная проверка перед выкладкой

```bash
cd frontend
cp .env.example .env   # VITE_API_BASE_URL=http://127.0.0.1:8020
npm ci
npm run build
npm run preview
```

Backend должен быть на порту из `.env` (стенд обычно `:8020`).

## DNS после покупки домена

| Запись | Значение |
|--------|----------|
| `@` A | IP VPS |
| `www` CNAME или A | тот же хост / IP |

Потом выпустить сертификат и открыть `https://домен`.
