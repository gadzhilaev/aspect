"""Telegram Bot HTTP webhooks — secret check + shared update handler.

News bot:   POST /telegram/webhook
Support bot: POST /telegram/support-webhook  (optional second bot)

Never log tokens or /start payloads. Business logic lives in
``app.services.telegram_updates`` (shared with long-polling).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.services.telegram_updates import handle_telegram_update

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _check_secret(provided: str | None, expected: str | None) -> None:
    secret = (expected or "").strip()
    if secret and (provided or "") != secret:
        raise AppError("FORBIDDEN", "Неверный webhook secret", 403)


@router.post("/webhook")
def telegram_webhook(
    update: dict,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    """Ingress for the news / user-link bot."""
    settings = get_settings()
    _check_secret(x_telegram_bot_api_secret_token, settings.telegram_webhook_secret)
    return handle_telegram_update(db, update)


@router.post("/support-webhook")
def telegram_support_webhook(
    update: dict,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    """Ingress for the optional support bot (operator replies /support_here)."""
    settings = get_settings()
    expected = (settings.telegram_support_webhook_secret or "").strip() or (
        settings.telegram_webhook_secret or ""
    )
    _check_secret(x_telegram_bot_api_secret_token, expected)
    if not (settings.telegram_support_bot_token or "").strip() and not (
        settings.telegram_bot_token or ""
    ).strip():
        raise AppError("PROVIDER_UNAVAILABLE", "Telegram support bot не настроен", 503)
    return handle_telegram_update(db, update)
