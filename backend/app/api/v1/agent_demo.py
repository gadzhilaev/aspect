"""Optional agent-demo stand entry — gated by AGENT_DEMO_STAND (stage 4.8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user, require_company_member
from app.core.errors import AppError
from app.db.session import get_db
from app.models import AssistantConversation, Company, CompanyMembership, Event, User
from app.schemas.agent_demo import AgentDemoEntryOut

router = APIRouter(prefix="/agent-demo", tags=["agent-demo"])

_SYNTH_TITLE_MARK = "СИНТЕТИЧЕСКИЙ ТЕСТ"
_SYNTH_NOTICE = (
    "Компания, событие и история чата — синтетические тестовые фикстуры. "
    "Это не конкурсные данные."
)
_PRIOR_NOTICE = (
    "Сохранённый ответ в истории — ранее полученный результат, "
    "не новая генерация при открытии страницы."
)


def _resolve_demo_event(db: Session, settings: Settings) -> Event:
    eid = (settings.agent_demo_event_id or "").strip() or None
    if eid:
        event = db.get(Event, eid)
        if event is None or event.status != "active":
            raise AppError("NOT_FOUND", "Демо-событие не найдено или не опубликовано", 404)
        return event

    rows = (
        db.query(Event)
        .filter(Event.status == "active")
        .order_by(Event.occurred_at.desc())
        .all()
    )
    for event in rows:
        title = event.title or ""
        if _SYNTH_TITLE_MARK in title:
            return event
        attrs = event.attributes_json or {}
        if isinstance(attrs, dict) and (
            attrs.get("synthetic_test") or attrs.get("agent_demo") or attrs.get("stage") == "4.6.2"
        ):
            return event
    raise AppError(
        "NOT_FOUND",
        "Синтетическое демо-событие не найдено (задайте AGENT_DEMO_EVENT_ID)",
        404,
    )


def _company_for_user(db: Session, user: User, event_id: str) -> Company:
    memberships = (
        db.query(CompanyMembership)
        .filter(CompanyMembership.user_id == user.id)
        .all()
    )
    if not memberships:
        raise AppError("FORBIDDEN", "Нет компании в профиле", 403)

    company_ids = [m.company_id for m in memberships]
    conv = (
        db.query(AssistantConversation)
        .filter(
            AssistantConversation.user_id == user.id,
            AssistantConversation.event_id == event_id,
            AssistantConversation.company_id.in_(company_ids),
            AssistantConversation.status == "active",
        )
        .order_by(AssistantConversation.updated_at.desc())
        .first()
    )
    preferred_id = conv.company_id if conv else memberships[0].company_id
    company = db.get(Company, preferred_id)
    if company is None:
        raise AppError("NOT_FOUND", "Компания не найдена", 404)
    require_company_member(preferred_id, db, user)
    return company


@router.get("/entry", response_model=AgentDemoEntryOut)
def agent_demo_entry(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AgentDemoEntryOut:
    if not settings.agent_demo_stand:
        raise AppError("NOT_FOUND", "Демостенд не включён", 404)

    event = _resolve_demo_event(db, settings)
    company = _company_for_user(db, user, event.id)
    conv = (
        db.query(AssistantConversation)
        .filter(
            AssistantConversation.user_id == user.id,
            AssistantConversation.company_id == company.id,
            AssistantConversation.event_id == event.id,
            AssistantConversation.status == "active",
        )
        .order_by(AssistantConversation.updated_at.desc())
        .first()
    )
    news_path = f"/news/{event.id}"
    assistant_path = f"/events/{event.id}/assistant"
    scenarios_path = (
        f"/scenarios?event={event.id}"
        if not conv
        else f"/scenarios?id={conv.id}"
    )
    return AgentDemoEntryOut(
        enabled=True,
        synthetic_notice=_SYNTH_NOTICE,
        prior_answer_notice=_PRIOR_NOTICE,
        event_id=event.id,
        event_title=event.title,
        is_demo=bool(event.is_demo),
        company_id=company.id,
        company_name=company.name,
        conversation_id=conv.id if conv else None,
        news_path=news_path,
        assistant_path=assistant_path,
        scenarios_path=scenarios_path,
        public_news_path="/news",
    )
