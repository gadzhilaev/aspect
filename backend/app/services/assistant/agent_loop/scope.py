"""Verified server scope for the agent loop (never from model arguments)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.deps import require_company_member
from app.core.errors import AppError
from app.models import Company, CompanyMembership, Event, User


@dataclass(frozen=True, slots=True)
class ServerScope:
    """ACL-checked binding for one loop turn."""

    user_id: str
    company_id: str
    event_id: str
    conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedScope:
    scope: ServerScope
    user: User
    company: Company
    event: Event
    membership: CompanyMembership


def resolve_server_scope(db: Session, scope: ServerScope) -> ResolvedScope:
    """Load entities and enforce membership + event existence.

    Raises ``AppError`` FORBIDDEN / NOT_FOUND — same codes as orchestrator ACL.
    """
    user = db.get(User, scope.user_id)
    if user is None:
        raise AppError("UNAUTHORIZED", "Пользователь не найден", 401)

    membership = require_company_member(scope.company_id, db, user)
    company = db.get(Company, scope.company_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)

    event = db.get(Event, scope.event_id)
    if event is None:
        raise AppError("NOT_FOUND", "Событие не найдено", 404)

    return ResolvedScope(
        scope=scope,
        user=user,
        company=company,
        event=event,
        membership=membership,
    )
