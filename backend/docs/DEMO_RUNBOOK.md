# Demo runbook (локально)

## Порты

- API: `http://127.0.0.1:8003` (официальный demo-порт)
- Web: `http://127.0.0.1:5173`
- `web/.env`: только `VITE_API_BASE_URL=http://127.0.0.1:8003`

## Старт

```powershell
# из корня репозитория
python -m scripts.ensure_demo
.\scripts\run_backend.ps1

# второй терминал
cd web
.\run_web.ps1
```

Demo login: `demo@kontur.app` / `DemoKontur1!`

## AI provider

Root `.env` only:

```env
ASSISTANT_PROVIDER=mock          # default offline
# ASSISTANT_PROVIDER=openai
# OPENAI_API_KEY=
# ASSISTANT_PROVIDER=gigachat
# GIGACHAT_AUTH_KEY=
# GIGACHAT_SCOPE=GIGACHAT_API_PERS
# GIGACHAT_MODEL=GigaChat
```

`ASSISTANT_PROVIDER=live` — deprecated alias for `openai`.

`mock` работает без ключей. Real AI (openai/gigachat) требует ключ в root `.env`; без ключа live-запрос не выполняется.

Never put `GIGACHAT_AUTH_KEY` / `OPENAI_API_KEY` / `HACKATHON_API_KEY` into `web/.env`, Git, OpenAPI, screenshots or docs.

### Hackathon gateway (optional)

```env
ASSISTANT_PROVIDER=hackathon
HACKATHON_API_KEY=
HACKATHON_BASE_URL=https://changellenge.up.railway.app/v1
HACKATHON_MODEL=deepseek/deepseek-v4.1-flash
```

Doctor shows `provider`, `hackathon_model`, `hackathon_base_url`, `key_configured` — never the key.  
See `docs/HACKATHON_PROVIDER.md`. Live smoke is manual only when the key is already set.

## Готовность

```powershell
.\scripts\demo_doctor.ps1
pytest -q
cd web; npm run build
```

Doctor prints only: `provider`, `key_configured` (true/false), health — never key values.

## Маршрут демо

1. Войти → лента «Для вас»
2. Событие (supply-chain или ключевая ставка) → влияние
3. Аспект: кратко о влиянии → источники (`Источник новости`) → сценарии
4. Метка текста: `Демо-объяснение` / `AI-объяснение` / `AI-объяснение · GigaChat` / `AI-объяснение · hackathon · <model>`
