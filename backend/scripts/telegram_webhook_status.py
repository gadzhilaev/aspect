"""Report current Bot API webhook (flags only — never prints token or secret)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.telegram_live_env import load_telegram_live_env  # noqa: E402


def main() -> int:
    flags = load_telegram_live_env()
    if not flags["telegram_bot_token"]:
        print("token_present=false")
        print("action=fill data/telegram_live/.env.secrets")
        return 2
    import os

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    # Avoid logging request URL (contains token).
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(url)
    if resp.status_code != 200:
        print(f"http_status={resp.status_code}")
        print("ok=false")
        return 1
    data = resp.json()
    if not data.get("ok"):
        print("ok=false")
        print(f"description={data.get('description', '')[:120]}")
        return 1
    info = data.get("result") or {}
    wh = (info.get("url") or "").strip()
    print("ok=true")
    print(f"webhook_configured={str(bool(wh)).lower()}")
    print(f"webhook_url={wh or '(empty)'}")
    print(f"has_custom_certificate={str(bool(info.get('has_custom_certificate'))).lower()}")
    print(f"pending_update_count={info.get('pending_update_count', 0)}")
    print(f"max_connections={info.get('max_connections', '')}")
    ip = info.get("ip_address") or ""
    print(f"ip_address_set={str(bool(ip)).lower()}")
    last_err = (info.get("last_error_message") or "").strip()
    if last_err:
        # Sanitize accidental token echoes
        safe = last_err.replace(token, "[redacted]")
        print(f"last_error_message={safe[:200]}")
        print(f"last_error_date={info.get('last_error_date', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
