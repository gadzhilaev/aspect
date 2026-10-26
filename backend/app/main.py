from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler, http_error_handler, validation_error_handler
from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401 — register models


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Local SQLite DX only. Schema changes must go through Alembic
    # (`alembic upgrade head`). Do not silently ALTER columns here.
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Backend MVP «Контур»: Digital Twin → Event Intelligence → Impact Graph → "
            "Solution Engine → Scenario Simulator. Объяснимые правила, демо-данные СеверПром."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/health", tags=["system"])
    def health() -> dict:
        news = bool((settings.telegram_bot_token or "").strip())
        support = bool((settings.telegram_support_bot_token or "").strip()) or news
        return {
            "status": "ok",
            "service": "kontur",
            "version": __version__,
            "env": settings.app_env,
            "telegram_configured": news or support,
            "telegram_news_configured": news,
            "telegram_support_configured": support,
        }

    @application.get("/", tags=["system"])
    def root() -> dict:
        return {
            "name": "Контур API",
            "docs": "/docs",
            "health": "/health",
            "principle": "Сначала честная и объяснимая цепочка на одной компании",
        }

    return application


app = create_app()
