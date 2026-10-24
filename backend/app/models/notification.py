from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationSubscription(Base):
    __tablename__ = "notification_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False)  # telegram_private|telegram_group
    chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chat_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # pending | connected | disconnected | blocked
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    min_severity: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    event_categories_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    risks_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opportunities_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiet_hours_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)
    # When connected: is_active=False means notifications paused (still linked).
    # Unlink clears chat_id and sets status=disconnected.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    muted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Watermark for automatic news notifications (TG-4). Archive before this instant
    # is never backfilled; recomputed Impact alone does not advance novelty.
    auto_notify_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TelegramLinkToken(Base):
    __tablename__ = "telegram_link_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), default="private", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_outbox_dedupe"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("notification_subscriptions.id"), nullable=True, index=True
    )
    # impact | test
    kind: Mapped[str] = mapped_column(String(32), default="impact", nullable=False)
    event_impact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("event_impacts.id"), nullable=True
    )
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    # pending | retry | sent | failed | skipped | blocked | uncertain
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
