from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.support import (
    SupportMessageIn,
    SupportMessageOut,
    SupportPostMessageOut,
    SupportThreadOut,
)
from app.services import support_chat as svc

router = APIRouter(prefix="/support", tags=["support"])


@router.get(
    "/thread",
    response_model=SupportThreadOut,
    summary="Get or create open support chat thread",
)
def get_thread(
    company_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SupportThreadOut:
    return svc.get_or_create_thread(db, user=user, company_id=company_id)


@router.get(
    "/thread/messages",
    response_model=list[SupportMessageOut],
    summary="List support messages (optional after_id for polling)",
)
def get_messages(
    after_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SupportMessageOut]:
    return svc.list_messages(db, user=user, after_id=after_id)


@router.post(
    "/thread/messages",
    response_model=SupportPostMessageOut,
    summary="Send a support message and receive auto-reply",
)
def post_message(
    body: SupportMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SupportPostMessageOut:
    user_msg, support_msg, reused = svc.post_message(
        db,
        user=user,
        content=body.content,
        client_message_id=body.client_message_id,
        company_id=body.company_id,
    )
    return SupportPostMessageOut(
        user_message=user_msg,
        support_message=support_msg,
        reused=reused,
    )


@router.post(
    "/thread/close",
    response_model=SupportThreadOut,
    summary="Close the current support thread",
)
def close_thread(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SupportThreadOut:
    return svc.close_thread(db, user=user)
