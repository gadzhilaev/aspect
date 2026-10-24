from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.assistant import (
    AssistantConversationListItem,
    AssistantConversationOut,
    AssistantMessageOut,
    CreateConversationIn,
    DraftDecisionIn,
    DraftDecisionOut,
    PostMessageIn,
    PostMessageOut,
    UserCompareScenariosIn,
    UserCompareScenariosOut,
)
from app.services.assistant import orchestrator as orch
from app.services.user_triggered_scenarios import run_user_compare_scenarios

router = APIRouter(tags=["assistant"])


@router.post(
    "/events/{event_id}/assistant/conversations",
    response_model=AssistantConversationOut,
)
def create_conversation(
    event_id: str,
    body: CreateConversationIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantConversationOut:
    conv, _created = orch.get_or_create_conversation(
        db, user=user, company_id=body.company_id, event_id=event_id
    )
    return orch.conversation_to_out(db, conv)


@router.get(
    "/assistant/conversations",
    response_model=list[AssistantConversationListItem],
)
def list_conversations(
    company_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AssistantConversationListItem]:
    return orch.list_conversations_for_company(db, user=user, company_id=company_id)


@router.get("/assistant/conversations/{conversation_id}", response_model=AssistantConversationOut)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssistantConversationOut:
    conv = orch.get_conversation_for_user(db, conversation_id=conversation_id, user=user)
    return orch.conversation_to_out(db, conv)


@router.get(
    "/assistant/conversations/{conversation_id}/messages",
    response_model=list[AssistantMessageOut],
)
def get_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AssistantMessageOut]:
    return orch.list_messages(db, conversation_id=conversation_id, user=user)


@router.post(
    "/assistant/conversations/{conversation_id}/messages",
    response_model=PostMessageOut,
    summary="Post Message",
    description=(
        "Отправка сообщения в обсуждение. "
        "При ASSISTANT_AGENT_LOOP=false — legacy-путь. "
        "При ASSISTANT_AGENT_LOOP=true и ASSISTANT_PROVIDER=hackathon — "
        "многошаговый read-only цикл (AgentLoopRunner). "
        "Неподдерживаемое сочетание провайдера и режима → "
        "ASSISTANT_AGENT_LOOP_UNSUPPORTED_PROVIDER (без fallback). "
        "Незавершённый цикл не возвращает successful final: "
        "ASSISTANT_LOOP_TIMEOUT (504), ASSISTANT_LOOP_BUDGET_EXHAUSTED (429), "
        "ASSISTANT_LOOP_NO_PROGRESS / ASSISTANT_LOOP_INVALID_ACTION / "
        "ASSISTANT_LOOP_INCOMPLETE (409), плюс ACL/provider ошибки. "
        "Повтор того же client_message_id + того же текста после успеха — "
        "200 reused без HTTP; после остановки — тот же ASSISTANT_LOOP_* "
        "(details.reused, not_ai_final), не successful final. "
        "Тот же id + другой текст — ASSISTANT_MESSAGE_ID_CONFLICT. "
        "Подробности: docs/ASSISTANT_AGENT_API_INTEGRATION.md, "
        "docs/ASSISTANT_AGENT_REPLAY_FIX.md."
    ),
    responses={
        409: {
            "description": (
                "Loop incomplete / in progress / "
                "ASSISTANT_MESSAGE_ID_CONFLICT (same id, different text)"
            )
        },
        429: {"description": "Loop budget exhausted"},
        504: {"description": "Loop model timeout"},
    },
)
def post_message(
    conversation_id: str,
    body: PostMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PostMessageOut:
    return orch.post_message(
        db,
        conversation_id=conversation_id,
        user=user,
        content=body.content,
        client_message_id=body.client_message_id,
    )


@router.post(
    "/assistant/conversations/{conversation_id}/draft-decision",
    response_model=DraftDecisionOut,
)
def draft_decision(
    conversation_id: str,
    body: DraftDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DraftDecisionOut:
    return orch.draft_decision(
        db,
        conversation_id=conversation_id,
        user=user,
        scenario_id=body.scenario_id,
        solution_id=body.solution_id,
        note=body.note,
        confirm=body.confirm,
        client_request_id=body.client_request_id,
    )


@router.post(
    "/assistant/conversations/{conversation_id}/compare-scenarios",
    response_model=UserCompareScenariosOut,
    summary="User-triggered scenario calculation",
    description=(
        "Явный пользовательский запуск сравнения сценариев (finance и/или supply-chain) "
        "без LLM и без write-tools agent loop. "
        "Тот же client_request_id + те же параметры → reused; "
        "тот же id + другие параметры → 409 USER_COMPARE_REQUEST_CONFLICT. "
        "Decision не создаётся. См. docs/USER_TRIGGERED_FINANCE_SCENARIOS.md."
    ),
    responses={
        409: {
            "description": (
                "USER_COMPARE_REQUEST_CONFLICT or CALCULATION_UNAVAILABLE path "
                "surfaced in result payload"
            )
        },
    },
)
def user_compare_scenarios(
    conversation_id: str,
    body: UserCompareScenariosIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserCompareScenariosOut:
    out = run_user_compare_scenarios(
        db,
        conversation_id=conversation_id,
        user=user,
        client_request_id=body.client_request_id,
        assumed_rate_change_pp=body.assumed_rate_change_pp,
        assumed_fx_change_percent=body.assumed_fx_change_percent,
        inventory_days=body.inventory_days,
        delay_days=body.delay_days,
    )
    return UserCompareScenariosOut(
        status=out["status"],  # type: ignore[arg-type]
        reused=bool(out.get("reused")),
        result=dict(out.get("result") or {}),
        message=out.get("message"),
        scenario_ids=list(out.get("scenario_ids") or []),
        decision_created=False,
        next_step=out.get("next_step"),
    )
