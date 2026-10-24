"""Register Telegram webhook for the TG-3 stand only when explicitly invoked.

Usage:
  python -m scripts.telegram_set_webhook --url https://HOST/api/v1/telegram/webhook

Refuses to overwrite a different existing webhook unless --force.
Does not drop pending updates (drop_pending_updates=false).
Never prints the bot token.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.telegram_live_env import load_telegram_live_env  # noqa: E402


def _valid_public_https(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return "url must be https"
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local"):
        return "localhost/public-loopback hosts are not valid for Telegram webhook"
    if not parsed.path.rstrip("/").endswith("/api/v1/telegram/webhook"):
        return "path must end with /api/v1/telegram/webhook"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Full https webhook URL")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite a different existing webhook URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report conflict / validity; do not call setWebhook",
    )
    args = parser.parse_args()

    err = _valid_public_https(args.url)
    if err:
        print(f"invalid_url={err}")
        return 2

    flags = load_telegram_live_env()
    if not flags["telegram_bot_token"]:
        print("token_present=false")
        return 2
    if not flags["telegram_webhook_secret"]:
        print("webhook_secret_present=false")
        return 2

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    secret = os.environ["TELEGRAM_WEBHOOK_SECRET"]

    with httpx.Client(timeout=20.0) as client:
        info_resp = client.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
        info_resp.raise_for_status()
        info = (info_resp.json().get("result") or {})
        current = (info.get("url") or "").strip()
        print(f"current_webhook={current or '(empty)'}")
        print(f"pending_update_count={info.get('pending_update_count', 0)}")
        print(f"target_webhook={args.url}")

        if current and current != args.url and not args.force:
            print("conflict=true")
            print(
                "message=Bot already has another webhook. "
                "Re-run with --force only if you intentionally replace it."
            )
            return 3

        if args.dry_run:
            print("dry_run=true")
            print("would_set=true")
            return 0

        resp = client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={
                "url": args.url,
                "secret_token": secret,
                "drop_pending_updates": False,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        body = resp.json()
        print(f"http_status={resp.status_code}")
        print(f"ok={str(bool(body.get('ok'))).lower()}")
        desc = (body.get("description") or "")[:160].replace(token, "[redacted]")
        if desc:
            print(f"description={desc}")
        return 0 if body.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
