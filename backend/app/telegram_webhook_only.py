"""Minimal ASGI app: only Telegram webhook (+ tiny health).

For temporary public tunnels so docs/OpenAPI/full API/site stay off the internet.
Shares DB and TELEGRAM_* settings with the main stand process via env.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1 import telegram
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler, http_error_handler, validation_error_handler
from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    yield


def create_webhook_only_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Kontur Telegram Webhook",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.include_router(telegram.router, prefix=settings.api_v1_prefix)

    @application.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "service": "kontur-telegram-webhook-only",
            "telegram_configured": bool(settings.telegram_bot_token),
        }

    return application


app = create_webhook_only_app()
