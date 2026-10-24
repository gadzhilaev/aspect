from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # None = significance not established (do not treat as 0).
    severity: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100 when known
    urgency_default: Mapped[str] = mapped_column(String(32), default="watch", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Structured matching signals — not just title keywords
    match_countries_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    match_categories_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    match_currencies_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    match_materials_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sources = relationship("EventSource", back_populates="event", cascade="all, delete-orphan")
    impacts = relationship("EventImpact", back_populates="event", cascade="all, delete-orphan")


class EventSource(Base):
    __tablename__ = "event_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("events.id"), nullable=False)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_quality: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)  # 0-1
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_stub: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    event = relationship("Event", back_populates="sources")


class EventImpact(Base):
    __tablename__ = "event_impacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("events.id"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, nullable=False)
    urgency: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason_summary: Mapped[str] = mapped_column(Text, nullable=False)
    exposure_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    exposure_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exposure_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    score_breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    claims_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="action_required", nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event = relationship("Event", back_populates="impacts")
    paths = relationship("ImpactPath", back_populates="impact", cascade="all, delete-orphan")
    solutions = relationship("SolutionCandidate", back_populates="impact", cascade="all, delete-orphan")


class ImpactPath(Base):
    __tablename__ = "impact_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_impact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("event_impacts.id"), nullable=False
    )
    path_nodes_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    path_edges_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    exposure_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    claim_type: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    impact = relationship("EventImpact", back_populates="paths")
