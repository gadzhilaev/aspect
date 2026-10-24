"""Telegram Bot HTTP webhook — secret check + shared update handler.

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


@router.post("/webhook")
def telegram_webhook(
    update: dict,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    settings = get_settings()
    if settings.telegram_webhook_secret and (
        x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise AppError("FORBIDDEN", "Неверный webhook secret", 403)

    return handle_telegram_update(db, update)
