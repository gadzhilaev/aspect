"""Internal ops endpoints — not for public UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.services.ingestion import run_ingestion

router = APIRouter(prefix="/internal", tags=["internal"])


class IngestionRunOut(BaseModel):
    fetched: int
    inserted: int
    duplicates: int
    clusters: int
    published: int
    rejected: int
    event_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def _require_ingestion_token(x_ingestion_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = (settings.ingestion_run_token or "").strip()
    if not expected:
        raise AppError(
            "FORBIDDEN",
            "Ingestion run disabled (INGESTION_RUN_TOKEN not configured)",
            403,
        )
    if not x_ingestion_token or x_ingestion_token != expected:
        raise AppError("FORBIDDEN", "Неверный ingestion token", 403)


@router.post(
    "/ingestion/run",
    response_model=IngestionRunOut,
    include_in_schema=False,
)
def run_ingestion_endpoint(
    _: None = Depends(_require_ingestion_token),
    db: Session = Depends(get_db),
    heuristic_enrich: bool = False,
) -> IngestionRunOut:
    """Manual refresh before a demo/defense. Not exposed in public UI."""
    result = run_ingestion(db, prefer_live_enrich=not heuristic_enrich)
    return IngestionRunOut(
        fetched=result.fetched,
        inserted=result.inserted,
        duplicates=result.duplicates,
        clusters=result.clusters,
        published=result.published,
        rejected=result.rejected,
        event_ids=result.event_ids,
        errors=result.errors,
    )
