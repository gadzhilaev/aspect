"""Fire-and-forget Telegram Bot API send helpers (no secrets in logs)."""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from app.core.config import get_settings
from app.services.notifications import sanitize_telegram_error

logger = logging.getLogger(__name__)

BotKind = Literal["news", "support"]


def _token_for(kind: BotKind) -> str:
    settings = get_settings()
    news = (settings.telegram_bot_token or "").strip()
    if kind == "news":
        return news
    support = (settings.telegram_support_bot_token or "").strip()
    # Single-bot fallback: support reuses news token when support token unset.
    return support or news


def send_telegram_text(
    chat_id: str | int,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    timeout: float = 12.0,
    bot: BotKind = "news",
) -> bool:
    """POST sendMessage. Returns True on HTTP 2xx. Never logs token/text."""
    token = _token_for(bot)
    if not token:
        logger.info("telegram_send_skipped reason=no_token bot=%s", bot)
        return False
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": (text or "")[:3900],
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
            )
        if resp.status_code >= 400:
            logger.warning(
                "telegram_send_failed bot=%s status=%s err=%s",
                bot,
                resp.status_code,
                sanitize_telegram_error(resp.text),
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "telegram_send_error bot=%s type=%s err=%s",
            bot,
            type(exc).__name__,
            sanitize_telegram_error(str(exc)),
        )
        return False
