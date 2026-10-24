# Временный HTTPS для webhook (TG-3) — команды

Цель: снаружи доступен **только** webhook-only процесс на порту `8028`
(`app.telegram_webhook_only:app`), а не полный API (`8027`), не `/docs`, не сайт.

## Известный блокер на этой машине (2026-10-24)

- Системный DNS / `happ-xray` даёт NXDOMAIN на SRV `argotunnel.com`.
- DoH отвечает; TCP :7844 до edge открыт; **TLS handshake EOF** — quick tunnel не поднимается, пока VPN/фильтр мешает.
- Не вызывайте `setWebhook` на URL, который отдаёт Cloudflare **530**.
- При необходимости: `scripts/telegram_doh_dns_proxy.py` + Docker `cloudflare/cloudflared` с `--dns <proxy>` (см. отчёт).

## Маршруты, которые станут доступны извне после туннеля на 8028

| Метод | Путь | Назначение |
|-------|------|------------|
| `POST` | `/api/v1/telegram/webhook` | Telegram updates (secret header обязателен) |
| `GET` | `/health` | Минимальный health webhook-only приложения |

Не публикуются: `/docs`, `/redoc`, `/openapi.json`, auth, companies, test-send, сайт.

Полный API остаётся на `127.0.0.1:8027` для UI.

## Установка cloudflared (один раз)

```powershell
winget install --id Cloudflare.cloudflared -e --accept-package-agreements --accept-source-agreements
```

Проверка: `cloudflared --version`

## Поднять стенд (три процесса + туннель)

Из корня репозитория, **после** заполнения `data/telegram_live/.env.secrets`:

```powershell
# 1) API для UI
powershell -File scripts/run_telegram_live_api.ps1

# 2) Webhook-only (в другом терминале)
powershell -File scripts/run_telegram_live_webhook.ps1

# 3) Worker kind=test (в другом терминале)
powershell -File scripts/run_telegram_live_worker.ps1

# 4) Туннель ТОЛЬКО на webhook-порт
cloudflared tunnel --url http://127.0.0.1:8028
```

Скопируйте выданный `https://*.trycloudflare.com` и зарегистрируйте webhook
(**только после вашего согласия на публикацию**):

```powershell
python -m scripts.telegram_webhook_status
python -m scripts.telegram_set_webhook --dry-run --url "https://HOST/api/v1/telegram/webhook"
# если current_webhook пустой или совпадает — без --force:
python -m scripts.telegram_set_webhook --url "https://HOST/api/v1/telegram/webhook"
```

Если `conflict=true` — не перезаписывать молча; нужен явный `--force`.

## Остановка только этого стенда

1. Ctrl+C в процессах API / webhook-only / worker / cloudflared.
2. Снять webhook (не трогая чужие боты, если URL ваш):

```powershell
# через Bot API deleteWebhook — только если текущий URL ваш стендовый
python -c "from scripts.telegram_live_env import load_telegram_live_env; import os, httpx; load_telegram_live_env(); t=os.environ['TELEGRAM_BOT_TOKEN']; r=httpx.post(f'https://api.telegram.org/bot{t}/deleteWebhook', json={'drop_pending_updates': False}); print('ok', r.json().get('ok'))"
```

3. Каталог `data/telegram_live/` можно удалить целиком (gitignored).
   Root `.env` и другие стенды не затрагиваются.
