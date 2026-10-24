from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CompanyRegistryLookup(Base):
    """Server-trusted result of one external INN lookup.

    Holds the normalized public candidates so confirmation can trust the
    provenance without the client being able to forge ``source`` / fields.
    Short-lived and bound to the user who performed the lookup.
    """

    __tablename__ = "company_registry_lookups"
    __table_args__ = (
        Index("ix_company_registry_lookups_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    inn: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    candidates_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    source_actuality_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
