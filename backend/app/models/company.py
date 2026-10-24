from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_band: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hq_region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    digital_twin_status: Mapped[str] = mapped_column(String(32), default="not_built", nullable=False)
    digital_twin_coverage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    memberships = relationship("CompanyMembership", back_populates="company")
    nodes = relationship("CompanyNode", back_populates="company", cascade="all, delete-orphan")
    edges = relationship("CompanyEdge", back_populates="company", cascade="all, delete-orphan")
    settings = relationship(
        "CompanyProfileSettings", back_populates="company", uselist=False, cascade="all, delete-orphan"
    )


class CompanyMembership(Base):
    __tablename__ = "company_memberships"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_membership"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="owner", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="memberships")
    company = relationship("Company", back_populates="memberships")


class CompanyNode(Base):
    __tablename__ = "company_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    # Typed critical fields (avoid sole JSON copy for business-critical values)
    output_share_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)

    company = relationship("Company", back_populates="nodes")


class CompanyEdge(Base):
    __tablename__ = "company_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    from_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("company_nodes.id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    to_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("company_nodes.id"), nullable=False)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="user", nullable=False)

    company = relationship("Company", back_populates="edges")


class CompanyProfileSettings(Base):
    __tablename__ = "company_profile_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), unique=True, nullable=False
    )
    purchase_currencies_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    optional_finance_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    preferences_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    warnings_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    company = relationship("Company", back_populates="settings")
