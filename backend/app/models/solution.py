from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SolutionCandidate(Base):
    __tablename__ = "solution_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_impact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("event_impacts.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_delta_percent: Mapped[float] = mapped_column(Float, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_percent: Mapped[float] = mapped_column(Float, nullable=False)
    compatibility: Mapped[float] = mapped_column(Float, nullable=False)  # 0-1
    availability_status: Mapped[str] = mapped_column(String(64), default="demo_estimate", nullable=False)
    sort_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sort_breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    impact = relationship("EventImpact", back_populates="solutions")


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("events.id"), nullable=False)
    solution_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("solution_candidates.id"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    results_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
